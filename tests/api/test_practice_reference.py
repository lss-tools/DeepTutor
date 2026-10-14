"""Verifying a reference answer by hand is a guarded write, not a free field.

A card confirmed in a state the exam variant skips would leave its position
reading as missing, so the endpoint refuses those confirmations instead.
"""

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from deeptutor.api.routers import practice, question_notebook
from deeptutor.services.session.sqlite_store import SQLiteSessionStore


@pytest.fixture
def reference_client(tmp_path, monkeypatch):
    store = SQLiteSessionStore(tmp_path / "reference.db")
    for module in (practice, question_notebook):
        monkeypatch.setattr(module, "get_sqlite_session_store", lambda: store)
    app = FastAPI()
    app.include_router(question_notebook.router, prefix="/bank")
    app.include_router(practice.router, prefix="/practice")
    with TestClient(app) as client:
        yield store, client


def add_card(
    store,
    position: int,
    *,
    answer="12",
    answer_format="number_or_sequence",
    max_score=1,
    with_criteria=True,
    question_source="sdamgia:101; task_type=9 (позиция-кандидат)",
):
    """One exported practice card as the exporter leaves it: unchecked, manual."""

    async def save():
        await store.ensure_notebook_session("reference-fixture", "Reference fixture")
        item = {
            "question_id": f"math-{position}-{answer_format}",
            "question": f"Position {position}: compute the value",
            "question_type": "short_answer",
            "correct_answer": answer,
            "user_answer": "",
            "explanation": "Worked solution.",
        }
        await store.upsert_notebook_entries("reference-fixture", [item])
        return await store.find_notebook_entry("reference-fixture", item["question_id"])

    entry = asyncio.run(save())
    with store._connect() as conn:
        conn.execute(
            """UPDATE notebook_entries SET exam_subject='math', kim_year='2027',
                kim_position=?, kim_part='1', answer_format=?, max_score=?,
                checking_mode='manual', reference_status='unchecked',
                question_source=?, is_analogue=1 WHERE id=?""",
            (str(position), answer_format, max_score, question_source, entry["id"]),
        )
        if with_criteria:
            conn.execute(
                """INSERT INTO practice_question_criteria(entry_id, score, text, source, scope)
                VALUES(?, ?, 'Correct answer', 'FIPI', 'whole answer')""",
                (entry["id"], max_score),
            )
    return entry["id"]


def test_confirmation_opens_the_position_and_records_position_origin(reference_client):
    store, client = reference_client
    entry_id = add_card(store, 9)

    assert client.get("/practice/exam/math/readiness").json()["available_positions"] == []

    response = client.post(
        f"/practice/questions/{entry_id}/reference",
        json={
            "reference_status": "verified",
            "checking_mode": "auto",
            "position_source": "navigator_fipi_2026",
            "position_checked_by_human": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["exam_ready"] is True
    assert body["reason"] == ""
    assert body["question_source"] == (
        "sdamgia:101; task_type=9 (позиция-кандидат); "
        "kim_position_source=navigator_fipi_2026; kim_position_checked_by_human=yes"
    )

    readiness = client.get("/practice/exam/math/readiness").json()
    assert readiness["available_positions"] == ["9"]
    assert readiness["candidate_counts"]["9"] == 1

    entry = client.get(f"/bank/entries/{entry_id}").json()
    assert entry["reference_status"] == "verified"
    assert entry["checking_mode"] == "auto"


def test_second_confirmation_restates_origin_without_stacking_markers(reference_client):
    store, client = reference_client
    entry_id = add_card(store, 9)
    payload = {
        "reference_status": "verified",
        "checking_mode": "auto",
        "position_source": "sdamgia_task_type",
    }
    client.post(f"/practice/questions/{entry_id}/reference", json=payload)
    body = client.post(
        f"/practice/questions/{entry_id}/reference",
        json={**payload, "position_source": "navigator_fipi_2026", "position_checked_by_human": True},
    ).json()

    assert body["question_source"].count("kim_position_source=") == 1
    assert "kim_position_source=navigator_fipi_2026" in body["question_source"]
    assert "kim_position_checked_by_human=yes" in body["question_source"]


def test_automatic_mode_is_refused_when_the_variant_would_skip_the_card(reference_client):
    store, client = reference_client
    entry_id = add_card(store, 10, answer="от 3 до 5", answer_format="interval")

    response = client.post(
        f"/practice/questions/{entry_id}/reference",
        json={"reference_status": "verified", "checking_mode": "auto"},
    )
    assert response.status_code == 422
    assert "model grading" in response.json()["detail"]
    assert client.get(f"/bank/entries/{entry_id}").json()["reference_status"] == "unchecked"

    accepted = client.post(
        f"/practice/questions/{entry_id}/reference",
        json={"reference_status": "verified", "checking_mode": "model"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["exam_ready"] is True
    assert client.get("/practice/exam/math/readiness").json()["available_positions"] == ["10"]


def test_model_mode_without_criteria_is_refused(reference_client):
    store, client = reference_client
    entry_id = add_card(store, 12, with_criteria=False)

    response = client.post(
        f"/practice/questions/{entry_id}/reference",
        json={"reference_status": "verified", "checking_mode": "model"},
    )
    assert response.status_code == 422
    assert "criteria" in response.json()["detail"]


def test_manual_grading_is_stored_but_reported_as_outside_the_variant(reference_client):
    store, client = reference_client
    entry_id = add_card(store, 13)

    body = client.post(
        f"/practice/questions/{entry_id}/reference",
        json={"reference_status": "verified", "checking_mode": "manual"},
    ).json()

    assert body["exam_ready"] is False
    assert "Manual grading" in body["reason"]
    assert client.get("/practice/exam/math/readiness").json()["available_positions"] == []


def test_confirmation_can_be_taken_back(reference_client):
    store, client = reference_client
    entry_id = add_card(store, 14)
    client.post(
        f"/practice/questions/{entry_id}/reference",
        json={"reference_status": "verified", "checking_mode": "auto"},
    )

    body = client.post(
        f"/practice/questions/{entry_id}/reference",
        json={"reference_status": "unchecked", "checking_mode": "manual"},
    ).json()

    assert body["exam_ready"] is False
    assert client.get("/practice/exam/math/readiness").json()["available_positions"] == []
