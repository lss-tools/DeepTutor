"""Full OGE attempts require a verified, answerable question at every position."""

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from deeptutor.api.routers import practice, question_notebook
from deeptutor.services.practice.storage import PracticeStore
from deeptutor.services.session.sqlite_store import SQLiteSessionStore


@pytest.fixture
def exam_client(tmp_path, monkeypatch):
    store = SQLiteSessionStore(tmp_path / "exam.db")
    for module in (practice, question_notebook):
        monkeypatch.setattr(module, "get_sqlite_session_store", lambda: store)
    app = FastAPI()
    app.include_router(question_notebook.router, prefix="/bank")
    app.include_router(practice.router, prefix="/practice")
    with TestClient(app) as client:
        yield store, client


def add_math_question(
    store,
    position: int,
    *,
    reference_status="verified",
    checking_mode="auto",
    max_score=1,
    answer_format="",
):
    async def save():
        await store.ensure_notebook_session("exam-fixture", "Exam fixture")
        item = {
            "question_id": f"math-{position}",
            "question": f"Position {position}: choose 4",
            "question_type": "free_response" if checking_mode == "model" else "single_choice",
            "options": {} if checking_mode == "model" else {"A": "3", "B": "4"},
            "correct_answer": "B",
            "user_answer": "",
            "is_correct": True,
            "explanation": "4 is the correct answer.",
        }
        await store.upsert_notebook_entries("exam-fixture", [item])
        return await store.find_notebook_entry("exam-fixture", item["question_id"])

    entry = asyncio.run(save())
    with store._connect() as conn:
        conn.execute(
            """UPDATE notebook_entries SET exam_subject='math', kim_year='2027',
                kim_position=?, max_score=?, checking_mode=?, answer_format=?,
                reference_status=? WHERE id=?""",
            (str(position), max_score, checking_mode, answer_format, reference_status, entry["id"]),
        )
        if checking_mode == "model":
            conn.execute(
                """INSERT INTO practice_question_criteria(entry_id, score, text, source, scope)
                VALUES(?, ?, 'Correct reasoning', 'test', 'whole answer')""",
                (entry["id"], max_score),
            )
    return entry["id"]


def test_exam_readiness_lists_missing_positions_and_starts_partial_variant(exam_client):
    store, client = exam_client
    add_math_question(store, 1)

    readiness = client.get("/practice/exam/math/readiness").json()
    assert readiness["ready"] is False
    assert readiness["available_positions"] == ["1"]
    assert readiness["missing_positions"] == [str(position) for position in range(2, 26)]
    response = client.post("/practice/exam/math/attempts")
    assert response.status_code == 201
    attempt = response.json()
    assert attempt["is_partial"] is True
    assert attempt["missing_positions"] == readiness["missing_positions"]
    assert len(attempt["items"]) == 1
    assert attempt["maximum_score"] == 1
    # Bank changes do not rewrite the stored composition of a running attempt.
    add_math_question(store, 2)
    resumed = client.get(f"/practice/exam/attempts/{attempt['attempt_id']}").json()
    assert resumed["missing_positions"] == readiness["missing_positions"]


def test_exam_attempt_resumes_scores_and_routes_zero_score_to_review(exam_client):
    store, client = exam_client
    for position in range(1, 26):
        add_math_question(store, position)

    created = client.post("/practice/exam/math/attempts").json()
    attempt_id = created["attempt_id"]
    assert created["status"] == "in_progress"
    assert len(created["items"]) == 25
    assert "correct_answer" not in created["items"][0]["question"]
    assert "explanation" not in created["items"][0]["question"]
    assert client.post(f"/practice/exam/attempts/{attempt_id}/complete").status_code == 422

    wrong = client.put(
        f"/practice/exam/attempts/{attempt_id}/positions/1", json={"answer": "A"}
    ).json()
    assert wrong["items"][0]["earned_score"] == 0
    assert wrong["items"][0]["answered"] is True

    for position in range(2, 26):
        client.put(
            f"/practice/exam/attempts/{attempt_id}/positions/{position}",
            json={"answer": "B"},
        ).raise_for_status()

    resumed = client.get(f"/practice/exam/attempts/{attempt_id}").json()
    assert resumed["items"][0]["answer"] == "A"
    completed = client.post(f"/practice/exam/attempts/{attempt_id}/complete").json()
    assert completed["status"] == "completed"
    assert completed["total_score"] == 24
    assert completed["maximum_score"] == 25
    assert completed["grade"] is None
    assert completed["scale_message"] == "Шкала не опубликована"
    assert completed["items"][0]["question"]["correct_answer"] == "B"

    queued = client.get("/practice/queue?timezone=UTC&limit=100").json()
    assert any(item["entry"]["id"] == completed["items"][0]["entry_id"] for item in queued)
    repeated = client.post(f"/practice/exam/attempts/{attempt_id}/complete").json()
    assert repeated["total_score"] == completed["total_score"]


def test_unconfirmed_candidate_is_never_used_for_exam_variant(exam_client):
    store, client = exam_client
    add_math_question(store, 1, reference_status="unchecked")
    readiness = client.get("/practice/exam/math/readiness").json()
    assert readiness["candidate_counts"]["1"] == 0
    assert "1" in readiness["missing_positions"]


def test_attempt_snapshot_survives_question_deletion(exam_client):
    store, client = exam_client
    ids = [add_math_question(store, position) for position in range(1, 26)]
    created = client.post("/practice/exam/math/attempts").json()
    attempt_id = created["attempt_id"]
    with store._connect() as conn:
        conn.execute("DELETE FROM notebook_entries WHERE id=?", (ids[0],))

    for position in range(1, 26):
        response = client.put(
            f"/practice/exam/attempts/{attempt_id}/positions/{position}",
            json={"answer": "A" if position == 1 else "B"},
        )
        response.raise_for_status()
    completed = client.post(f"/practice/exam/attempts/{attempt_id}/complete").json()
    assert completed["status"] == "completed"
    assert completed["items"][0]["entry_id"] == ids[0]
    assert completed["items"][0]["earned_score"] == 0


def test_model_checked_position_accepts_partial_score_from_chat_event(exam_client):
    store, client = exam_client
    entry_ids = [
        add_math_question(
            store,
            position,
            checking_mode="model" if position == 1 else "auto",
            max_score=2 if position == 1 else 1,
        )
        for position in range(1, 26)
    ]
    created = client.post("/practice/exam/math/attempts").json()
    attempt_id = created["attempt_id"]
    first = client.put(
        f"/practice/exam/attempts/{attempt_id}/positions/1",
        json={"answer": "A derivation with a correct first step"},
    ).json()
    assert first["items"][0]["answered"] is True
    assert first["items"][0]["earned_score"] is None

    for position in range(2, 26):
        client.put(
            f"/practice/exam/attempts/{attempt_id}/positions/{position}",
            json={"answer": "B"},
        ).raise_for_status()
    assert client.post(f"/practice/exam/attempts/{attempt_id}/complete").status_code == 422

    grade = PracticeStore(store.db_path).record_model_score(
        entry_ids[0], "chat_turn_123456", 0.5, 2, "chat-session"
    )
    scored = client.post(
        f"/practice/exam/attempts/{attempt_id}/positions/1/model-score",
        json={"grading_attempt_id": grade["attempt_id"]},
    ).json()
    assert scored["items"][0]["earned_score"] == 0.5
    revised = client.put(
        f"/practice/exam/attempts/{attempt_id}/positions/1",
        json={"answer": "Revised derivation with a stronger second step"},
    ).json()
    assert revised["items"][0]["earned_score"] is None
    assert client.post(f"/practice/exam/attempts/{attempt_id}/complete").status_code == 422
    revised_grade = PracticeStore(store.db_path).record_model_score(
        entry_ids[0], "chat_turn_654321", 0.75, 2, "chat-session"
    )
    rescored = client.post(
        f"/practice/exam/attempts/{attempt_id}/positions/1/model-score",
        json={"grading_attempt_id": revised_grade["attempt_id"]},
    ).json()
    assert rescored["items"][0]["earned_score"] == 0.75
    completed = client.post(f"/practice/exam/attempts/{attempt_id}/complete").json()
    assert completed["status"] == "completed"
    assert completed["total_score"] == 24.75


def test_empty_bank_cannot_start_an_attempt(exam_client):
    _, client = exam_client
    assert client.post("/practice/exam/math/attempts").status_code == 409


def test_criteria_only_card_is_confirmed_graded_and_completed_without_reference(exam_client):
    store, client = exam_client
    entry_id = add_math_question(store, 24, checking_mode="model", max_score=2)
    with store._connect() as conn:
        conn.execute("UPDATE notebook_entries SET correct_answer='', explanation='' WHERE id=?", (entry_id,))
    confirmed = client.post(
        f"/practice/questions/{entry_id}/reference",
        json={"reference_status": "verified", "checking_mode": "model"},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["exam_ready"] is True
    assert client.get("/practice/exam/math/readiness").json()["available_positions"] == ["24"]
    created = client.post("/practice/exam/math/attempts").json()
    attempt_id = created["attempt_id"]
    assert created["items"][0]["question"]["reference_basis"] == "criteria_only"
    assert "correct_answer" not in created["items"][0]["question"]
    saved = client.put(f"/practice/exam/attempts/{attempt_id}/positions/24", json={"answer": "A proof"})
    assert saved.status_code == 200
    score = PracticeStore(store.db_path).record_model_score(entry_id, "criteria_only_grade", 1, 2, "chat-session")
    graded = client.post(
        f"/practice/exam/attempts/{attempt_id}/positions/24/model-score",
        json={"grading_attempt_id": score["attempt_id"]},
    )
    assert graded.status_code == 200
    completed = client.post(f"/practice/exam/attempts/{attempt_id}/complete").json()
    assert completed["total_score"] == 1 and completed["maximum_score"] == 2
    assert completed["is_partial"] is True and "25" in completed["missing_positions"]
    assert completed["items"][0]["question"]["explanation"] == ""


def test_criteria_only_card_without_criteria_is_not_admitted(exam_client):
    store, client = exam_client
    entry_id = add_math_question(store, 25, checking_mode="model", max_score=2)
    with store._connect() as conn:
        conn.execute("UPDATE notebook_entries SET correct_answer='', explanation='' WHERE id=?", (entry_id,))
        conn.execute("DELETE FROM practice_question_criteria WHERE entry_id=?", (entry_id,))
    response = client.post(
        f"/practice/questions/{entry_id}/reference",
        json={"reference_status": "verified", "checking_mode": "model"},
    )
    assert response.status_code == 422
    assert client.get("/practice/exam/math/readiness").json()["available_positions"] == []


def test_exam_snapshot_carries_question_attachments_without_revealing_solution(exam_client):
    import json
    store, client = exam_client
    entry_id = add_math_question(store, 11)
    attachment = {"kind": "image", "name": "graph.svg", "sha256": "a" * 64,
                  "path": "practice/attachments/graph.svg", "mime": "image/svg+xml", "bytes": 10}
    with store._connect() as conn:
        conn.execute("UPDATE notebook_entries SET attachments_json=? WHERE id=?", (json.dumps([attachment]), entry_id))
    created = client.post("/practice/exam/math/attempts").json()
    question = created["items"][0]["question"]
    assert question["attachments"] == [attachment]
    assert "correct_answer" not in question and "explanation" not in question


def test_graph_position_exposes_its_answer_format_and_stores_coordinates(exam_client):
    """Position 22 takes a graph described by coordinates, graded by criteria later."""
    store, client = exam_client
    add_math_question(
        store, 22, checking_mode="model", max_score=2,
        answer_format="graph_and_parameter",
    )
    created = client.post("/practice/exam/math/attempts").json()
    item = next(item for item in created["items"] if item["position"] == "22")
    assert item["question"]["answer_format"] == "graph_and_parameter"
    answer = "\n".join([
        "График:",
        "1) парабола через (−4; 0), (−2,5; −2,25), (−1; 0)",
        "Выколотые точки: (−3; −2)",
        "Значения параметра: −2,25; −2",
    ])
    response = client.put(
        f"/practice/exam/attempts/{created['attempt_id']}/positions/22",
        json={"answer": answer},
    )
    assert response.status_code == 200
    stored = next(item for item in response.json()["items"] if item["position"] == "22")
    assert stored["answer"] == answer
    assert stored["answered"] is True
    assert stored["earned_score"] is None


def test_import_accepts_criteria_only_model_card_and_rejects_auto_without_answer():
    from deeptutor.services.practice.importing import normalize_question
    raw = {
        "question": "Prove the statement", "correct_answer": "", "explanation": "",
        "exam_subject": "math", "kim_year": "2027", "kim_position": "24", "kim_part": "2",
        "answer_format": "proof", "max_score": "2", "checking_mode": "model",
        "question_source": "sdamgia:123", "is_analogue": "true", "reference_status": "unchecked",
        "criteria": [{"score": 2, "text": "A complete proof", "source": "FIPI", "scope": "position24"}],
    }
    assert normalize_question(raw)["correct_answer"] == ""
    with pytest.raises(ValueError, match="correct answer"):
        normalize_question({**raw, "checking_mode": "auto"})
    with pytest.raises(ValueError, match="criteria"):
        normalize_question({**raw, "criteria": []})
