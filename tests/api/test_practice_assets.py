"""Practice assets are scoped to the question owner and safe disk paths."""

import asyncio
import csv
import io
import json
import sqlite3
import zipfile

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from deeptutor.api.routers import practice
from deeptutor.services.session.sqlite_store import SQLiteSessionStore


@pytest.fixture
def bank(tmp_path, monkeypatch):
    store = SQLiteSessionStore(tmp_path / "bank.db")
    monkeypatch.setattr(practice, "get_sqlite_session_store", lambda: store)
    app = FastAPI()
    app.include_router(practice.router, prefix="/practice")
    with TestClient(app) as client:
        yield store, client


def archive(asset_names, *, missing=False, unsafe=False):
    output = io.BytesIO()
    manifest = io.StringIO(newline="")
    writer = csv.writer(manifest)
    writer.writerow(["question", "answer", "asset"])
    writer.writerow(["Describe the files", "OK", json.dumps(asset_names)])
    with zipfile.ZipFile(output, "w") as bundle:
        bundle.writestr("questions.csv", manifest.getvalue())
        for name in asset_names:
            if not missing:
                bundle.writestr(("../" if unsafe else "assets/") + name, name.encode())
    return output.getvalue()


def test_zip_import_serves_three_file_types_and_is_idempotent(bank):
    store, client = bank
    names = ["graph.png", "speech.mp3", "worksheet.docx"]
    data = archive(names)
    first = client.post("/practice/import/preview", files={"file": ("questions.zip", data)})
    assert first.status_code == 200, first.text
    token = first.json()["token"]
    assert token
    assert len(first.json()["samples"][0].get("attachments", [])) == 3, first.json()
    assert client.post("/practice/import/commit", json={"token": token}).json()["created"] == 1
    second = client.post("/practice/import/preview", files={"file": ("questions.zip", data)})
    assert client.post("/practice/import/commit", json={"token": second.json()["token"]}).json()["duplicates"] == 1
    entry = asyncio.run(store.list_notebook_entries())["items"][0]
    assert [a["kind"] for a in entry["attachments"]] == ["image", "audio", "file"]
    assert len(entry["attachments"]) == 3
    for asset in entry["attachments"]:
        response = client.get(f"/practice/questions/{entry['id']}/attachments/{asset['sha256']}")
        assert response.status_code == 200
        assert response.content == asset["name"].encode()
        if asset["kind"] == "file":
            assert response.headers["content-disposition"].startswith("attachment;")


def test_upload_requires_entry_and_owner_and_rejects_changed_path(bank, tmp_path, monkeypatch):
    store, client = bank
    missing = client.post("/practice/questions/99/attachments", files={"file": ("x.png", b"abc")})
    assert missing.status_code == 404
    question = {"question_id": "q", "question": "Q", "correct_answer": "A"}
    asyncio.run(store.ensure_notebook_session("lesson", "Lesson"))
    asyncio.run(store.upsert_notebook_entries("lesson", [question]))
    entry = asyncio.run(store.find_notebook_entry("lesson", "q"))
    response = client.post(f"/practice/questions/{entry['id']}/attachments", files={"file": ("x.png", b"abc")})
    assert response.status_code == 200
    digest = response.json()["sha256"]
    url = f"/practice/questions/{entry['id']}/attachments/{digest}"
    assert client.get(url).content == b"abc"
    other = SQLiteSessionStore(tmp_path / "other.db")
    monkeypatch.setattr(practice, "get_sqlite_session_store", lambda: other)
    assert client.get(url).status_code == 404
    monkeypatch.setattr(practice, "get_sqlite_session_store", lambda: store)
    with sqlite3.connect(store.db_path) as conn:
        bad = [{**response.json(), "path": "../../other.db"}]
        conn.execute("UPDATE notebook_entries SET attachments_json=? WHERE id=?", (json.dumps(bad), entry["id"]))
    assert client.get(url).status_code == 404


@pytest.mark.parametrize("missing,unsafe", [(True, False), (False, True)])
def test_zip_rejects_missing_and_unsafe_assets(bank, missing, unsafe):
    _, client = bank
    response = client.post(
        "/practice/import/preview",
        files={"file": ("questions.zip", archive(["graph.png"], missing=missing, unsafe=unsafe))},
    )
    if unsafe:
        assert response.status_code == 422
    else:
        assert response.status_code == 200
        assert response.json()["token"] is None
        assert "Missing asset" in response.json()["errors"][0]["message"]
