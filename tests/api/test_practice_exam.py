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
                kim_position=?, max_score=?, checking_mode=?,
                reference_status=? WHERE id=?""",
            (str(position), max_score, checking_mode, reference_status, entry["id"]),
        )
        if checking_mode == "model":
            conn.execute(
                """INSERT INTO practice_question_criteria(entry_id, score, text, source, scope)
                VALUES(?, ?, 'Correct reasoning', 'test', 'whole answer')""",
                (entry["id"], max_score),
            )
    return entry["id"]


def test_exam_readiness_lists_missing_positions_and_rejects_partial_variant(exam_client):
    store, client = exam_client
    add_math_question(store, 1)

    readiness = client.get("/practice/exam/math/readiness").json()
    assert readiness["ready"] is False
    assert readiness["available_positions"] == ["1"]
    assert readiness["missing_positions"] == [str(position) for position in range(2, 26)]
    response = client.post("/practice/exam/math/attempts")
    assert response.status_code == 409
    assert response.json()["detail"]["missing_positions"] == readiness["missing_positions"]


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
