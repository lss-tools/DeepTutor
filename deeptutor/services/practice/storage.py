"""Transactional review history and import staging in the user's notebook DB."""

from __future__ import annotations

from contextlib import contextmanager
import json
import math
from pathlib import Path
import random
import re
import sqlite3
import time
import uuid

from .scheduler import DAY, Rating, day_bounds, schedule

# Legacy correct or manually mastered questions start with a three-day interval.
# Once reviewed, the saved adaptive schedule is authoritative.
_DUE_AT_SQL = """(CASE WHEN n.resolved=1 THEN n.updated_at + 259200
    WHEN r.entry_id IS NULL AND n.is_correct=1 THEN n.updated_at + 259200
    ELSE COALESCE(r.due_at, n.created_at) END)"""


class ReviewConflict(ValueError):
    """A different tab or source changed this question since it was opened."""


class IncompleteExamVariant(ValueError):
    """The verified bank does not contain every position for a full variant."""

    def __init__(self, missing_positions: list[str]):
        self.missing_positions = missing_positions
        super().__init__("Verified questions are missing for one or more exam positions")


_EXAM_POSITION_COUNTS = {"math": 25, "russian": 13, "physics": 22, "informatics": 16}

_REFERENCE_STATUSES = {"verified", "confirmed", "unchecked"}
_CHECKING_MODES = {"auto", "model", "manual"}
# Where a card's KIM position comes from, as recorded by the bank pipeline.
# Only the navigator value means a person compared the card against the
# official FIPI position list.
_POSITION_SOURCES = {
    "navigator_fipi_2026",
    "derived_fipi_navigator_2026",
    "sdamgia_task_type",
    "not_determined",
}
_PROVENANCE_RE = re.compile(
    r"\s*;?\s*kim_position_source=[^;]*(?:;\s*kim_position_checked_by_human=[^;]*)?"
)


def _with_position_provenance(
    question_source: str, position_source: str, checked_by_human: bool
) -> str:
    """Keep the card's own text and restate where its KIM position came from.

    A confirmed card has to answer "who decided this is position 9?" by
    itself: the bank has no column for it, and the source pipeline that knows
    is a separate database.
    """
    if not position_source:
        return question_source
    base = _PROVENANCE_RE.sub("", question_source).strip().strip(";").strip()
    marker = (
        f"kim_position_source={position_source}; "
        f"kim_position_checked_by_human={'yes' if checked_by_human else 'no'}"
    )
    return f"{base}; {marker}" if base else marker


def _exam_eligibility(entry: dict, has_criteria: bool) -> tuple[bool, str]:
    """Whether the exam variant can draw this card, and what stops it."""
    from .answers import check_answer

    if entry["reference_status"] not in {"verified", "confirmed"}:
        return False, "The reference answer is not verified"
    if entry["checking_mode"] not in {"auto", "model"}:
        return False, "Manual grading stays outside the exam variant"
    if not str(entry.get("exam_subject") or "").strip():
        return False, "The card carries no exam subject"
    if not str(entry.get("kim_position") or "").strip():
        return False, "The card carries no KIM position"
    if not entry.get("max_score") or float(entry["max_score"]) <= 0:
        return False, "The card carries no maximum score"
    if not str(entry.get("question") or "").strip():
        return False, "The question text is empty"
    if not str(entry.get("explanation") or "").strip():
        return False, "The worked solution is empty"
    if entry["checking_mode"] == "model" and not has_criteria:
        return False, "Scoring criteria are missing"
    if entry["checking_mode"] == "auto" and check_answer(
        entry, str(entry.get("correct_answer") or "")
    ) is not True:
        return False, "The answer does not pass automatic checking"
    return True, ""


def initialize_practice(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(notebook_entries)")}
    if "attachments_json" not in columns:
        conn.execute("ALTER TABLE notebook_entries ADD COLUMN attachments_json TEXT NOT NULL DEFAULT '[]'")
    existing = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name='practice_review_state'"
    ).fetchone()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS practice_review_state (
            entry_id INTEGER PRIMARY KEY REFERENCES notebook_entries(id) ON DELETE CASCADE,
            is_mistake INTEGER NOT NULL DEFAULT 1,
            first_wrong_at REAL NOT NULL,
            due_at REAL NOT NULL,
            interval_days REAL NOT NULL DEFAULT 1,
            ease REAL NOT NULL DEFAULT 2.5,
            streak INTEGER NOT NULL DEFAULT 0,
            lapses INTEGER NOT NULL DEFAULT 0,
            review_count INTEGER NOT NULL DEFAULT 0,
            last_review_at REAL,
            version INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_practice_due ON practice_review_state(due_at, entry_id);
        CREATE TABLE IF NOT EXISTS practice_review_events (
            request_id TEXT PRIMARY KEY,
            entry_id INTEGER NOT NULL REFERENCES notebook_entries(id) ON DELETE CASCADE,
            rating TEXT NOT NULL,
            answer TEXT NOT NULL,
            reviewed_at REAL NOT NULL,
            outcome_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_practice_history ON practice_review_events(entry_id, reviewed_at);
        CREATE TABLE IF NOT EXISTS practice_score_events (
            attempt_id TEXT PRIMARY KEY,
            entry_id INTEGER NOT NULL REFERENCES notebook_entries(id) ON DELETE CASCADE,
            model_score REAL,
            final_score REAL NOT NULL,
            max_score REAL NOT NULL,
            grading_source TEXT NOT NULL,
            chat_session_id TEXT NOT NULL DEFAULT '',
            manually_corrected INTEGER NOT NULL DEFAULT 0,
            edited_by TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_practice_scores_entry
            ON practice_score_events(entry_id, created_at DESC);
        CREATE TABLE IF NOT EXISTS practice_question_criteria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER NOT NULL REFERENCES notebook_entries(id) ON DELETE CASCADE,
            score REAL NOT NULL,
            text TEXT NOT NULL,
            source TEXT NOT NULL,
            scope TEXT NOT NULL,
            UNIQUE(entry_id, score)
        );
        CREATE INDEX IF NOT EXISTS idx_practice_criteria_entry
            ON practice_question_criteria(entry_id, score);
        CREATE TABLE IF NOT EXISTS practice_exam_attempts (
            attempt_id TEXT PRIMARY KEY,
            exam_subject TEXT NOT NULL,
            kim_year INTEGER NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('in_progress', 'completed')),
            total_score REAL,
            maximum_score REAL NOT NULL,
            grade INTEGER,
            grade_status TEXT NOT NULL DEFAULT 'unpublished',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            completed_at REAL
        );
        CREATE INDEX IF NOT EXISTS idx_practice_exam_attempts_recent
            ON practice_exam_attempts(created_at DESC);
        CREATE TABLE IF NOT EXISTS practice_exam_items (
            attempt_id TEXT NOT NULL REFERENCES practice_exam_attempts(attempt_id) ON DELETE CASCADE,
            position TEXT NOT NULL,
            entry_id INTEGER NOT NULL,
            question_snapshot TEXT NOT NULL,
            max_score REAL NOT NULL,
            answer TEXT,
            earned_score REAL,
            answered_at REAL,
            grading_attempt_id TEXT,
            PRIMARY KEY(attempt_id, position),
            UNIQUE(attempt_id, entry_id)
        );
        CREATE TABLE IF NOT EXISTS practice_imports (
            token TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            target TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at REAL NOT NULL,
            result_json TEXT
        );
        CREATE TRIGGER IF NOT EXISTS practice_capture_insert
        AFTER INSERT ON notebook_entries
        WHEN NEW.is_correct = 0 AND COALESCE(NEW.result, '') != 'ungraded'
        BEGIN
            INSERT INTO practice_review_state(entry_id, first_wrong_at, due_at)
            SELECT NEW.id, NEW.created_at, NEW.created_at + 86400
            WHERE NOT EXISTS(SELECT 1 FROM practice_review_state WHERE entry_id=NEW.id);
        END;
        CREATE TRIGGER IF NOT EXISTS practice_invalidate_question
        AFTER UPDATE OF question, options_json, correct_answer ON notebook_entries
        WHEN OLD.question != NEW.question OR OLD.options_json != NEW.options_json OR OLD.correct_answer != NEW.correct_answer
        BEGIN
            UPDATE practice_review_state SET version=version+1 WHERE entry_id=NEW.id;
        END;
        DROP TRIGGER IF EXISTS practice_capture_update;
        CREATE TRIGGER practice_capture_update
        AFTER UPDATE OF is_correct, result ON notebook_entries
        WHEN NEW.is_correct = 0 AND COALESCE(NEW.result, '') != 'ungraded'
        BEGIN
            INSERT INTO practice_review_state(entry_id, first_wrong_at, due_at)
            SELECT NEW.id, NEW.updated_at, NEW.updated_at + 86400
            WHERE NOT EXISTS(SELECT 1 FROM practice_review_state WHERE entry_id=NEW.id);
            UPDATE practice_review_state SET
                first_wrong_at = CASE WHEN is_mistake=0 THEN NEW.updated_at ELSE first_wrong_at END,
                is_mistake = 1,
                due_at = NEW.updated_at + 86400, interval_days = 1, streak = 0,
                version = version + 1
            WHERE entry_id = NEW.id AND (OLD.is_correct = 1 OR OLD.result = 'ungraded');
        END;
    """)
    exam_item_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(practice_exam_items)")
    }
    if "grading_attempt_id" not in exam_item_columns:
        conn.execute("ALTER TABLE practice_exam_items ADD COLUMN grading_attempt_id TEXT")
    if not existing:
        # Additive migration: original IDs, answers, timestamps and categories stay intact.
        conn.execute("""
            INSERT OR IGNORE INTO practice_review_state(entry_id, first_wrong_at, due_at)
            SELECT id, created_at, created_at + 86400 FROM notebook_entries
            WHERE is_correct = 0 AND COALESCE(result, '') != 'ungraded'
        """)


class PracticeStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def _scope(session_ids: list[str] | None) -> tuple[str, list]:
        # Independent imports/document questions have no chat to delete. They
        # stay visible in the global bank, while an explicit course/session
        # scope continues to select conversation-backed entries only.
        sql = "(n.session_id IS NULL OR s.deleted_at IS NULL)"
        params: list = []
        if session_ids is not None:
            sql += " AND n.session_id IN (" + (",".join("?" for _ in session_ids) or "NULL") + ")"
            params.extend(session_ids)
        return sql, params

    def overview(
        self, timezone: str, session_ids: list[str] | None = None, now: float | None = None
    ) -> dict:
        now = time.time() if now is None else now
        start, end = day_bounds(timezone, now)
        scope, params = self._scope(session_ids)
        with self.connect() as conn:
            row = conn.execute(
                f"""
                SELECT COUNT(*) AS total,
                    COALESCE(SUM(r.is_mistake = 1), 0) AS mistakes,
                    COALESCE(SUM({_DUE_AT_SQL} <= ?), 0) AS due,
                    COALESCE(SUM({_DUE_AT_SQL} <= ?), 0) AS overdue,
                    MIN({_DUE_AT_SQL}) AS next_due_at
                FROM notebook_entries n LEFT JOIN sessions s ON s.id = n.session_id
                LEFT JOIN practice_review_state r ON r.entry_id = n.id WHERE {scope}
            """,  # nosec B608 - fixed scope SQL; values bound
                [now, start, *params],
            ).fetchone()  # nosec B608 - bound scope values
            completed = conn.execute(
                f"""
                SELECT COUNT(DISTINCT e.entry_id) FROM practice_review_events e
                JOIN notebook_entries n ON n.id = e.entry_id LEFT JOIN sessions s ON s.id = n.session_id
                WHERE e.reviewed_at >= ? AND e.reviewed_at < ? AND {scope}
            """,  # nosec B608 - fixed scope SQL; values bound
                [start, end, *params],
            ).fetchone()[0]  # nosec B608
        return {**dict(row), "reviewed_today": completed, "day_end": end, "timezone": timezone}

    def analytics(
        self,
        timezone: str,
        days: int = 30,
        session_ids: list[str] | None = None,
        now: float | None = None,
    ) -> dict:
        from .analytics import analytics

        scope, params = self._scope(session_ids)
        with self.connect() as conn:
            return analytics(
                conn, timezone, days, time.time() if now is None else now, scope, params
            )

    def queue(
        self,
        timezone: str,
        session_ids: list[str] | None = None,
        category_id: int | None = None,
        limit: int = 20,
        now: float | None = None,
    ) -> list[int]:
        now = time.time() if now is None else now
        day_bounds(timezone, now)
        scope, params = self._scope(session_ids)
        if category_id is not None:
            scope += " AND EXISTS(SELECT 1 FROM notebook_entry_categories c WHERE c.entry_id=n.id AND c.category_id=?)"
            params.append(category_id)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT n.id FROM notebook_entries n LEFT JOIN sessions s ON s.id=n.session_id
                LEFT JOIN practice_review_state r ON r.entry_id=n.id
                WHERE {_DUE_AT_SQL} <= ? AND {scope}
                ORDER BY {_DUE_AT_SQL}, n.id LIMIT ?
            """,  # nosec B608 - fixed scope SQL; values bound
                [now, *params, limit],
            ).fetchall()  # nosec B608
        return [row["id"] for row in rows]

    def state(self, entry_id: int) -> dict:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM practice_review_state WHERE entry_id=?", (entry_id,)
            ).fetchone()
        return (
            dict(row)
            if row
            else {
                "entry_id": entry_id,
                "is_mistake": 0,
                "version": 0,
                "review_count": 0,
                "interval_days": 1,
                "due_at": None,
            }
        )

    def is_visible(self, entry_id: int) -> bool:
        with self.connect() as conn:
            return (
                conn.execute(
                    """SELECT 1 FROM notebook_entries n LEFT JOIN sessions s ON s.id=n.session_id
                WHERE n.id=? AND (n.session_id IS NULL OR s.deleted_at IS NULL)""",
                    (entry_id,),
                ).fetchone()
                is not None
            )

    def review(
        self,
        entry_id: int,
        request_id: str,
        version: int,
        rating: Rating,
        answer: str,
        now: float | None = None,
        *,
        self_report: bool = False,
    ) -> dict:
        now = time.time() if now is None else now
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            previous = conn.execute(
                "SELECT * FROM practice_review_events WHERE request_id=?", (request_id,)
            ).fetchone()
            if previous:
                if (
                    previous["entry_id"] != entry_id
                    or previous["rating"] != rating
                    or previous["answer"] != answer
                    or bool(json.loads(previous["outcome_json"]).get("self_report")) != self_report
                ):
                    raise ReviewConflict(
                        "This submission ID was already used for a different answer"
                    )
                return json.loads(previous["outcome_json"])
            entry = conn.execute(
                """SELECT n.* FROM notebook_entries n LEFT JOIN sessions s ON s.id=n.session_id
                WHERE n.id=? AND (n.session_id IS NULL OR s.deleted_at IS NULL)""",
                (entry_id,),
            ).fetchone()
            if not entry:
                raise LookupError("Question not found")
            row = conn.execute(
                "SELECT * FROM practice_review_state WHERE entry_id=?", (entry_id,)
            ).fetchone()
            state = dict(row) if row else {"version": 0}
            if state["version"] != version:
                raise ReviewConflict(
                    "This question changed in another tab. Reload it before reviewing again."
                )
            # Objective answers are checked again at the transaction boundary.
            from .answers import check_answer

            correct = None if self_report else check_answer(dict(entry), answer)
            if correct is False and rating != "again":
                raise ValueError("An incorrect answer must be reviewed again")
            next_state = schedule(state, rating, now)
            mistake = bool(state.get("is_mistake")) or rating == "again"
            conn.execute(
                """
                INSERT INTO practice_review_state(entry_id, is_mistake, first_wrong_at, due_at,
                    interval_days, ease, streak, lapses, review_count, last_review_at, version)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(entry_id) DO UPDATE SET is_mistake=excluded.is_mistake, due_at=excluded.due_at,
                    first_wrong_at=CASE WHEN practice_review_state.is_mistake=0 AND excluded.is_mistake=1
                        THEN excluded.first_wrong_at ELSE practice_review_state.first_wrong_at END,
                    interval_days=excluded.interval_days, ease=excluded.ease, streak=excluded.streak,
                    lapses=excluded.lapses, review_count=excluded.review_count,
                    last_review_at=excluded.last_review_at, version=excluded.version
            """,
                (
                    entry_id,
                    int(mistake),
                    now,
                    *(
                        next_state[key]
                        for key in (
                            "due_at",
                            "interval_days",
                            "ease",
                            "streak",
                            "lapses",
                            "review_count",
                            "last_review_at",
                            "version",
                        )
                    ),
                ),
            )
            if rating == "again":
                conn.execute("UPDATE notebook_entries SET resolved=0 WHERE id=?", (entry_id,))
            score_result = None
            maximum = entry["max_score"]
            if (
                correct is not None
                and maximum is not None
                and entry["checking_mode"] == "auto"
                and not self_report
            ):
                maximum = float(maximum)
                earned = maximum if correct else 0.0
                score_result = {
                    "earned_score": earned,
                    "max_score": maximum,
                    "grading_source": "automatic",
                }
                conn.execute(
                    """INSERT OR IGNORE INTO practice_score_events(
                        attempt_id, entry_id, model_score, final_score, max_score,
                        grading_source, created_at, updated_at)
                        VALUES(?, ?, NULL, ?, ?, 'automatic', ?, ?)""",
                    (request_id, entry_id, earned, maximum, now, now),
                )
            outcome = {
                **next_state,
                "entry_id": entry_id,
                "is_mistake": mistake,
                "correct": correct,
                "rating": rating,
                "self_report": self_report,
                "mastered": rating in {"good", "easy"},
                "score": score_result,
            }
            conn.execute(
                "INSERT INTO practice_review_events VALUES(?, ?, ?, ?, ?, ?)",
                (request_id, entry_id, rating, answer, now, json.dumps(outcome)),
            )
        return outcome

    def record_model_score(
        self,
        entry_id: int,
        attempt_id: str,
        score: float,
        max_score: float,
        chat_session_id: str,
        now: float | None = None,
    ) -> dict:
        """Record one model grade without overwriting an existing manual correction."""
        now = time.time() if now is None else now
        attempt_id = attempt_id.strip()
        if (
            not attempt_id
            or not math.isfinite(max_score)
            or not math.isfinite(score)
            or max_score <= 0
            or score < 0
            or score > max_score
        ):
            raise ValueError("A valid attempt ID and score within the maximum are required")
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            entry = conn.execute(
                "SELECT max_score, checking_mode, reference_status, correct_answer FROM notebook_entries WHERE id=?",
                (entry_id,),
            ).fetchone()
            if entry is None:
                raise LookupError("Question not found")
            if entry["checking_mode"] != "model":
                raise ValueError("This question is not configured for model grading")
            if entry["reference_status"] not in {"verified", "confirmed"}:
                raise ValueError("The reference answer needs manual verification")
            if not str(entry["correct_answer"] or "").strip():
                raise ValueError("The reference answer is missing; send this question for manual review")
            if entry["max_score"] is None or float(entry["max_score"]) != float(max_score):
                raise ValueError("The attempt maximum does not match the question")
            if not conn.execute(
                "SELECT 1 FROM practice_question_criteria WHERE entry_id=? LIMIT 1",
                (entry_id,),
            ).fetchone():
                raise ValueError("Scoring criteria are missing; send this question for manual review")
            previous = conn.execute(
                "SELECT * FROM practice_score_events WHERE attempt_id=?", (attempt_id,)
            ).fetchone()
            if previous:
                if (
                    previous["entry_id"] != entry_id
                    or float(previous["model_score"] or 0) != float(score)
                    or float(previous["max_score"]) != float(max_score)
                    or previous["chat_session_id"] != chat_session_id
                ):
                    raise ReviewConflict("This attempt already has a different model grade")
                return dict(previous)
            conn.execute(
                """INSERT INTO practice_score_events(
                    attempt_id, entry_id, model_score, final_score, max_score,
                    grading_source, chat_session_id, created_at, updated_at)
                    VALUES(?, ?, ?, ?, ?, 'model', ?, ?, ?)""",
                (attempt_id, entry_id, score, score, max_score, chat_session_id, now, now),
            )
            return dict(
                conn.execute(
                    "SELECT * FROM practice_score_events WHERE attempt_id=?", (attempt_id,)
                ).fetchone()
            )

    def correct_score(
        self,
        entry_id: int,
        attempt_id: str,
        score: float,
        edited_by: str,
        now: float | None = None,
    ) -> dict:
        """Keep the model score and record the adult's final score separately."""
        now = time.time() if now is None else now
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM practice_score_events WHERE attempt_id=? AND entry_id=?",
                (attempt_id, entry_id),
            ).fetchone()
            if row is None:
                raise LookupError("Scored attempt not found")
            if not math.isfinite(score) or score < 0 or score > float(row["max_score"]):
                raise ValueError("Score must be between zero and the attempt maximum")
            conn.execute(
                """UPDATE practice_score_events SET final_score=?, manually_corrected=1,
                    edited_by=?, updated_at=? WHERE attempt_id=? AND entry_id=?""",
                (score, edited_by, now, attempt_id, entry_id),
            )
            result = dict(
                conn.execute(
                    "SELECT * FROM practice_score_events WHERE attempt_id=? AND entry_id=?",
                    (attempt_id, entry_id),
                ).fetchone()
            )
            result["manually_corrected"] = bool(result["manually_corrected"])
            return result

    def score_history(self, entry_id: int) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM practice_score_events WHERE entry_id=? ORDER BY created_at DESC, attempt_id",
                (entry_id,),
            ).fetchall()
        return [
            {**dict(row), "manually_corrected": bool(row["manually_corrected"])}
            for row in rows
        ]

    def question_criteria(self, entry_id: int) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT score, text, source, scope FROM practice_question_criteria WHERE entry_id=? ORDER BY score",
                (entry_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def confirm_reference(
        self,
        entry_id: int,
        reference_status: str,
        checking_mode: str,
        position_source: str = "",
        position_checked_by_human: bool = False,
        now: float | None = None,
    ) -> dict:
        """Record a human's verdict on one card's reference answer and grading mode.

        The exam variant draws verified cards only, and it silently skips a
        verified card whose answer does not self-check or whose model grading
        has no criteria. Such a confirmation is worse than a refusal: the
        position keeps reading as missing while the human believes the work is
        done. So every gate the variant applies is checked here first, against
        the values the card is about to receive.
        """
        from .answers import check_answer

        now = time.time() if now is None else now
        if reference_status not in _REFERENCE_STATUSES:
            raise ValueError("Reference status must be verified, confirmed or unchecked")
        if checking_mode not in _CHECKING_MODES:
            raise ValueError("Checking mode must be auto, model or manual")
        if position_source and position_source not in _POSITION_SOURCES:
            raise ValueError("Unknown KIM position source")
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            entry = conn.execute(
                "SELECT * FROM notebook_entries WHERE id=?", (entry_id,)
            ).fetchone()
            if entry is None:
                raise LookupError("Question not found")
            has_criteria = bool(
                conn.execute(
                    "SELECT 1 FROM practice_question_criteria WHERE entry_id=? LIMIT 1",
                    (entry_id,),
                ).fetchone()
            )
            prospective = {
                **dict(entry),
                "reference_status": reference_status,
                "checking_mode": checking_mode,
            }
            if reference_status in {"verified", "confirmed"}:
                if not str(entry["correct_answer"] or "").strip():
                    raise ValueError("The reference answer is empty; nothing to verify")
                if checking_mode == "model" and not has_criteria:
                    raise ValueError("Model grading needs scoring criteria on this question")
                if (
                    checking_mode == "auto"
                    and check_answer(prospective, str(entry["correct_answer"])) is not True
                ):
                    raise ValueError(
                        "Automatic checking cannot confirm this answer format; use model grading"
                    )
            question_source = _with_position_provenance(
                str(entry["question_source"] or ""),
                position_source,
                position_checked_by_human,
            )
            conn.execute(
                """UPDATE notebook_entries SET reference_status=?, checking_mode=?,
                    question_source=?, updated_at=? WHERE id=?""",
                (reference_status, checking_mode, question_source, now, entry_id),
            )
            prospective["question_source"] = question_source
            ready, reason = _exam_eligibility(prospective, has_criteria)
            return {
                "entry_id": entry_id,
                "reference_status": reference_status,
                "checking_mode": checking_mode,
                "question_source": question_source,
                "exam_subject": str(entry["exam_subject"] or ""),
                "kim_position": str(entry["kim_position"] or ""),
                "exam_ready": ready,
                "reason": reason,
                "updated_at": now,
            }

    @staticmethod
    def _exam_positions(subject: str) -> list[str]:
        count = _EXAM_POSITION_COUNTS.get(subject)
        if count is None:
            raise ValueError("Unsupported OGE subject")
        return [str(position) for position in range(1, count + 1)]

    def exam_readiness(self, subject: str, kim_year: int = 2027) -> dict:
        positions = self._exam_positions(subject)
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT * FROM notebook_entries
                WHERE exam_subject=? AND kim_year=? AND reference_status IN ('verified','confirmed')
                  AND (checking_mode='auto' OR (checking_mode='model' AND EXISTS(
                      SELECT 1 FROM practice_question_criteria c
                      WHERE c.entry_id=notebook_entries.id)))
                  AND TRIM(COALESCE(correct_answer,''))!=''
                  AND max_score>0 AND TRIM(question)!='' AND TRIM(COALESCE(explanation,''))!=''
                  AND (session_id IS NULL OR EXISTS(
                      SELECT 1 FROM sessions s WHERE s.id=notebook_entries.session_id
                        AND s.deleted_at IS NULL))
                """ ,
                (subject, str(kim_year)),
            ).fetchall()
        from .answers import check_answer

        counts = {position: 0 for position in positions}
        for row in rows:
            mode = row["checking_mode"]
            if mode == "auto" and check_answer(dict(row), str(row["correct_answer"])) is not True:
                continue
            position = str(row["kim_position"])
            if position in counts:
                counts[position] += 1
        missing = [position for position in positions if counts.get(position, 0) == 0]
        return {
            "exam_subject": subject,
            "kim_year": kim_year,
            "positions": positions,
            "available_positions": [position for position in positions if counts.get(position, 0)],
            "missing_positions": missing,
            "ready": not missing,
            "candidate_counts": {position: counts.get(position, 0) for position in positions},
            "source_policy": "verified reference with automatic or criteria-based model grading",
        }

    @staticmethod
    def _exam_attempt_payload(conn: sqlite3.Connection, attempt_id: str) -> dict | None:
        attempt = conn.execute(
            "SELECT * FROM practice_exam_attempts WHERE attempt_id=?", (attempt_id,)
        ).fetchone()
        if attempt is None:
            return None
        items = conn.execute(
            "SELECT * FROM practice_exam_items WHERE attempt_id=? ORDER BY CAST(position AS INTEGER)",
            (attempt_id,),
        ).fetchall()
        completed = attempt["status"] == "completed"
        result_items = []
        for row in items:
            snapshot = json.loads(row["question_snapshot"])
            options = json.loads(snapshot.get("options_json") or "{}")
            question = {
                "id": snapshot["id"],
                "question": snapshot["question"],
                "question_type": snapshot["question_type"],
                "options": options,
                "checking_mode": snapshot.get("checking_mode", ""),
            }
            if snapshot.get("checking_mode") == "model":
                question["criteria"] = snapshot.get("criteria", [])
            if completed:
                question["correct_answer"] = snapshot["correct_answer"]
                question["explanation"] = snapshot["explanation"]
            result_items.append({
                "position": row["position"],
                "entry_id": row["entry_id"],
                "question": question,
                "max_score": row["max_score"],
                "answer": row["answer"],
                "earned_score": row["earned_score"],
                "answered": row["answered_at"] is not None,
            })
        return {
            **dict(attempt),
            "items": result_items,
            "scale_message": "Шкала не опубликована" if attempt["grade_status"] == "unpublished" else "",
        }

    def create_exam_attempt(self, subject: str, kim_year: int = 2027, now: float | None = None) -> dict:
        now = time.time() if now is None else now
        positions = self._exam_positions(subject)
        readiness = self.exam_readiness(subject, kim_year)
        if readiness["missing_positions"]:
            raise IncompleteExamVariant(readiness["missing_positions"])
        attempt_id = uuid.uuid4().hex
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            selected = []
            for position in positions:
                candidates = conn.execute(
                    """SELECT n.* FROM notebook_entries n
                    WHERE n.exam_subject=? AND n.kim_year=? AND n.kim_position=?
                      AND n.reference_status IN ('verified','confirmed')
                      AND n.checking_mode IN ('auto','model')
                      AND TRIM(COALESCE(n.correct_answer,''))!='' AND n.max_score>0
                      AND TRIM(n.question)!='' AND TRIM(COALESCE(n.explanation,''))!=''
                      AND (n.session_id IS NULL OR EXISTS(
                          SELECT 1 FROM sessions s WHERE s.id=n.session_id
                            AND s.deleted_at IS NULL))
                      AND (n.checking_mode='auto' OR EXISTS(
                          SELECT 1 FROM practice_question_criteria c WHERE c.entry_id=n.id))
                    ORDER BY n.id""",
                    (subject, str(kim_year), position),
                ).fetchall()
                from .answers import check_answer

                candidates = [
                    row for row in candidates
                    if row["checking_mode"] == "model"
                    or check_answer(dict(row), str(row["correct_answer"])) is True
                ]
                if not candidates:
                    raise IncompleteExamVariant([position])
                selected.append(random.choice(candidates))
            maximum = sum(float(row["max_score"]) for row in selected)
            conn.execute(
                """INSERT INTO practice_exam_attempts(
                    attempt_id, exam_subject, kim_year, status, maximum_score, grade_status,
                    created_at, updated_at) VALUES(?, ?, ?, 'in_progress', ?, 'unpublished', ?, ?)""",
                (attempt_id, subject, kim_year, maximum, now, now),
            )
            item_values = []
            for row in selected:
                snapshot = dict(row)
                snapshot["criteria"] = [
                    dict(criteria)
                    for criteria in conn.execute(
                        """SELECT score, text, source, scope FROM practice_question_criteria
                        WHERE entry_id=? ORDER BY score""",
                        (row["id"],),
                    ).fetchall()
                ]
                item_values.append((
                    attempt_id,
                    row["kim_position"],
                    row["id"],
                    json.dumps(snapshot, ensure_ascii=False),
                    float(row["max_score"]),
                ))
            conn.executemany(
                """INSERT INTO practice_exam_items(
                    attempt_id, position, entry_id, question_snapshot, max_score)
                    VALUES(?, ?, ?, ?, ?)""",
                item_values,
            )
            return self._exam_attempt_payload(conn, attempt_id)

    def get_exam_attempt(self, attempt_id: str) -> dict | None:
        with self.connect() as conn:
            return self._exam_attempt_payload(conn, attempt_id)

    def answer_exam_position(
        self, attempt_id: str, position: str, answer: str, now: float | None = None
    ) -> dict:
        now = time.time() if now is None else now
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            attempt = conn.execute(
                "SELECT status FROM practice_exam_attempts WHERE attempt_id=?", (attempt_id,)
            ).fetchone()
            if attempt is None:
                raise LookupError("Exam attempt not found")
            if attempt["status"] != "in_progress":
                raise ValueError("The exam attempt is already completed")
            row = conn.execute(
                "SELECT * FROM practice_exam_items WHERE attempt_id=? AND position=?",
                (attempt_id, str(position)),
            ).fetchone()
            if row is None:
                raise LookupError("Exam position not found")
            snapshot = json.loads(row["question_snapshot"])
            from .answers import check_answer

            if snapshot.get("checking_mode") == "model":
                if not answer.strip():
                    raise ValueError("Enter the solution before saving this position")
                earned = None
            else:
                correct = check_answer(snapshot, answer)
                if correct is None:
                    raise ValueError("This question cannot be checked automatically")
                earned = float(row["max_score"]) if correct else 0.0
            conn.execute(
                """UPDATE practice_exam_items SET answer=?, earned_score=?, answered_at=?,
                    grading_attempt_id=NULL
                WHERE attempt_id=? AND position=?""",
                (answer, earned, now, attempt_id, str(position)),
            )
            conn.execute(
                "UPDATE practice_exam_attempts SET updated_at=? WHERE attempt_id=?",
                (now, attempt_id),
            )
            return self._exam_attempt_payload(conn, attempt_id)

    def record_exam_model_score(
        self,
        attempt_id: str,
        position: str,
        grading_attempt_id: str,
    ) -> dict:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            attempt = conn.execute(
                "SELECT status FROM practice_exam_attempts WHERE attempt_id=?",
                (attempt_id,),
            ).fetchone()
            if attempt is None:
                raise LookupError("Exam attempt not found")
            if attempt["status"] != "in_progress":
                raise ValueError("The exam attempt is already completed")
            item = conn.execute(
                "SELECT * FROM practice_exam_items WHERE attempt_id=? AND position=?",
                (attempt_id, str(position)),
            ).fetchone()
            if item is None or item["answered_at"] is None:
                raise LookupError("Answered exam position not found")
            snapshot = json.loads(item["question_snapshot"])
            if snapshot.get("checking_mode") != "model":
                raise ValueError("This exam position does not use model grading")
            score = conn.execute(
                """SELECT * FROM practice_score_events
                WHERE attempt_id=? AND entry_id=? AND grading_source='model'""",
                (grading_attempt_id, item["entry_id"]),
            ).fetchone()
            if score is None:
                raise LookupError("Model grade not found for this question")
            if float(score["max_score"]) != float(item["max_score"]):
                raise ValueError("Model grade maximum does not match this exam position")
            if item["grading_attempt_id"]:
                if item["grading_attempt_id"] != grading_attempt_id:
                    raise ReviewConflict("This exam position already has another model grade")
                return self._exam_attempt_payload(conn, attempt_id)
            conn.execute(
                """UPDATE practice_exam_items SET earned_score=?, grading_attempt_id=?
                WHERE attempt_id=? AND position=?""",
                (float(score["final_score"]), grading_attempt_id, attempt_id, str(position)),
            )
            conn.execute(
                "UPDATE practice_exam_attempts SET updated_at=? WHERE attempt_id=?",
                (time.time(), attempt_id),
            )
            return self._exam_attempt_payload(conn, attempt_id)

    def complete_exam_attempt(self, attempt_id: str, now: float | None = None) -> dict:
        now = time.time() if now is None else now
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            attempt = conn.execute(
                "SELECT * FROM practice_exam_attempts WHERE attempt_id=?", (attempt_id,)
            ).fetchone()
            if attempt is None:
                raise LookupError("Exam attempt not found")
            if attempt["status"] == "completed":
                return self._exam_attempt_payload(conn, attempt_id)
            items = conn.execute(
                "SELECT earned_score, answered_at FROM practice_exam_items WHERE attempt_id=?",
                (attempt_id,),
            ).fetchall()
            if any(item["answered_at"] is None for item in items):
                raise ValueError("Answer every position before completing the exam")
            if any(item["earned_score"] is None for item in items):
                raise ValueError("Grade every model-checked position before completing the exam")
            total = sum(float(item["earned_score"]) for item in items)
            wrong_items = conn.execute(
                """SELECT i.entry_id FROM practice_exam_items i
                JOIN notebook_entries n ON n.id=i.entry_id
                WHERE i.attempt_id=? AND i.earned_score<i.max_score""",
                (attempt_id,),
            ).fetchall()
            for item in wrong_items:
                conn.execute(
                    "UPDATE notebook_entries SET resolved=0 WHERE id=?",
                    (item["entry_id"],),
                )
                conn.execute(
                    """INSERT INTO practice_review_state(entry_id, is_mistake, first_wrong_at,
                        due_at, interval_days, ease, streak, lapses, review_count, version)
                    VALUES(?, 1, ?, ?, 1, 2.5, 0, 1, 0, 0)
                    ON CONFLICT(entry_id) DO UPDATE SET is_mistake=1,
                        first_wrong_at=CASE WHEN practice_review_state.is_mistake=0 THEN excluded.first_wrong_at
                                            ELSE practice_review_state.first_wrong_at END,
                        due_at=MIN(practice_review_state.due_at, excluded.due_at),
                        interval_days=1, streak=0, lapses=practice_review_state.lapses+1,
                        version=practice_review_state.version+1""",
                    (item["entry_id"], now, now),
                )
            conn.execute(
                """UPDATE practice_exam_attempts SET status='completed', total_score=?,
                    updated_at=?, completed_at=? WHERE attempt_id=?""",
                (total, now, now, attempt_id),
            )
            return self._exam_attempt_payload(conn, attempt_id)

    def stage_import(
        self, filename: str, target: str, questions: list[dict], course_id: str = ""
    ) -> str:
        token, now = uuid.uuid4().hex, time.time()
        with self.connect() as conn:
            conn.execute(
                "DELETE FROM practice_imports WHERE created_at < ? AND result_json IS NULL",
                (now - DAY,),
            )
            conn.execute(
                "INSERT INTO practice_imports VALUES(?, ?, ?, ?, ?, NULL)",
                (
                    token,
                    filename[:200],
                    target,
                    json.dumps(
                        {"questions": questions, "course_id": course_id}, ensure_ascii=False
                    ),
                    now,
                ),
            )
        return token

    def commit_import(self, token: str) -> dict:
        now = time.time()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            staged = conn.execute(
                "SELECT * FROM practice_imports WHERE token=?", (token,)
            ).fetchone()
            if not staged:
                raise LookupError("Import preview not found. Select the file again.")
            if staged["result_json"]:
                return json.loads(staged["result_json"])
            if now - staged["created_at"] > DAY:
                raise ValueError("Import preview expired. Select the file again.")
            payload = json.loads(staged["payload_json"])
            questions = payload if isinstance(payload, list) else payload["questions"]
            # All practice-file imports share one durable origin namespace.
            # ``question_id`` is a content hash, so re-importing the same
            # question remains idempotent without tying ownership to an
            # ephemeral preview receipt or a synthetic chat session.
            origin_ref = "practice-import"
            created, skipped = 0, 0
            for question in questions:
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO notebook_entries(
                        session_id, origin_type, origin_ref, question_id, question, question_type,
                        options_json, correct_answer, explanation, difficulty, user_answer, source,
                        result, assessment_type, created_at, updated_at, material_title, material_id,
                        exam_subject, kim_year, kim_position, kim_part, answer_format, max_score,
                        checking_mode, question_source, is_analogue, reference_status, attachments_json)
                    VALUES(NULL, 'external_import', ?, ?, ?, ?, ?, ?, ?, ?, ?, 'import', ?, 'quiz', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        origin_ref,
                        question["question_id"],
                        question["question"],
                        question["question_type"],
                        json.dumps(question["options"], ensure_ascii=False),
                        question["correct_answer"],
                        question["explanation"],
                        question["difficulty"],
                        question["user_answer"],
                        "incorrect" if staged["target"] == "mistakes" else "ungraded",
                        now,
                        now,
                        staged["filename"],
                        "import:" + token,
                        question["exam_subject"],
                        question["kim_year"],
                        question["kim_position"],
                        question["kim_part"],
                        question["answer_format"],
                        question["max_score"],
                        question["checking_mode"],
                        question["question_source"],
                        int(question["is_analogue"]),
                        question["reference_status"],
                        json.dumps(question.get("attachments", []), ensure_ascii=False),
                    ),
                )
                created += cursor.rowcount
                skipped += 1 - cursor.rowcount
                entry_id = conn.execute(
                    """SELECT id FROM notebook_entries
                    WHERE origin_type='external_import' AND origin_ref=?
                      AND question_id=? AND turn_id=''""",
                    (origin_ref, question["question_id"]),
                ).fetchone()[0]
                if question["exam_subject"]:
                    fields = (
                        "exam_subject",
                        "kim_year",
                        "kim_position",
                        "kim_part",
                        "answer_format",
                        "max_score",
                        "checking_mode",
                        "question_source",
                        "is_analogue",
                        "reference_status",
                    )
                    current = conn.execute(
                        "SELECT " + ", ".join(fields) + " FROM notebook_entries WHERE id=?",
                        (entry_id,),
                    ).fetchone()
                    incoming = tuple(
                        int(question[name])
                        if name == "is_analogue"
                        else float(question[name])
                        if name == "max_score"
                        else question[name]
                        for name in fields
                    )
                    saved = tuple(current[name] for name in fields)
                    if current["exam_subject"] and saved != incoming:
                        raise ValueError("Existing question has different exam metadata")
                    if not current["exam_subject"]:
                        assignments = ", ".join(f"{name}=?" for name in fields)
                        conn.execute(
                            f"UPDATE notebook_entries SET {assignments} WHERE id=?",  # nosec B608
                            (*incoming, entry_id),
                        )
                for criterion in question["criteria"]:
                    saved_criterion = conn.execute(
                        "SELECT text, source, scope FROM practice_question_criteria WHERE entry_id=? AND score=?",
                        (entry_id, criterion["score"]),
                    ).fetchone()
                    criterion_values = (
                        criterion["text"],
                        criterion["source"],
                        criterion["scope"],
                    )
                    if saved_criterion and tuple(saved_criterion) != criterion_values:
                        raise ValueError("Existing question has different score criteria")
                    conn.execute(
                        """INSERT OR IGNORE INTO practice_question_criteria(
                            entry_id, score, text, source, scope) VALUES(?, ?, ?, ?, ?)""",
                        (
                            entry_id,
                            criterion["score"],
                            criterion["text"],
                            criterion["source"],
                            criterion["scope"],
                        ),
                    )
                if staged["target"] == "mistakes":
                    conn.execute(
                        "INSERT OR IGNORE INTO practice_review_state(entry_id, first_wrong_at, due_at) VALUES(?, ?, ?)",
                        (entry_id, now, now + DAY),
                    )
                    conn.execute(
                        """UPDATE practice_review_state SET is_mistake=1, first_wrong_at=?,
                            due_at=?, interval_days=1, version=version+1
                            WHERE entry_id=? AND is_mistake=0""",
                        (now, now + DAY, entry_id),
                    )
                for tag in question["tags"]:
                    conn.execute(
                        "INSERT OR IGNORE INTO notebook_categories(name, created_at) VALUES(?, ?)",
                        (tag, now),
                    )
                    conn.execute(
                        "INSERT OR IGNORE INTO notebook_entry_categories(entry_id, category_id) SELECT ?, id FROM notebook_categories WHERE name=?",
                        (entry_id, tag),
                    )
            result = {"created": created, "duplicates": skipped, "total": created + skipped}
            conn.execute(
                "UPDATE practice_imports SET result_json=?, payload_json='[]' WHERE token=?",
                (json.dumps(result), token),
            )
        return result
