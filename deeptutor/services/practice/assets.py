"""Files referenced by practice questions in the current user's data store."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import sqlite3
import uuid

from deeptutor.partners.helpers import safe_filename

MAX_ASSET_BYTES = 32 * 1024 * 1024
_HASH = re.compile(r"^[0-9a-f]{64}$")


class PracticeAssetStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.root = db_path.parent / "practice" / "attachments"

    @staticmethod
    def _name(name: str) -> str:
        if not name or name in {".", ".."} or "/" in name or "\\" in name:
            raise ValueError("Use a plain attachment filename")
        cleaned = safe_filename(name)
        if not cleaned or cleaned in {".", ".."}:
            raise ValueError("Invalid attachment filename")
        return cleaned

    def _target(self, digest: str, name: str) -> Path:
        if not _HASH.fullmatch(digest):
            raise ValueError("Invalid attachment hash")
        clean = self._name(name)
        root = self.root.resolve()
        if self.root.parent.is_symlink() or self.root.is_symlink() or (self.root / digest).is_symlink():
            raise ValueError("Attachment directory is a symbolic link")
        target = self.root / digest / clean
        if target.is_symlink() or not target.resolve().is_relative_to(root):
            raise ValueError("Attachment path escapes the user's data directory")
        return target

    def put(self, name: str, data: bytes) -> dict:
        if not data or len(data) > MAX_ASSET_BYTES:
            raise ValueError("Choose an attachment up to 32 MB")
        digest = hashlib.sha256(data).hexdigest()
        target = self._target(digest, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file():
            temporary = target.with_name(uuid.uuid4().hex + ".tmp")
            try:
                temporary.write_bytes(data)
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        kind = "image" if mime.startswith("image/") else "audio" if mime.startswith("audio/") else "file"
        return {
            "kind": kind,
            "name": name,
            "path": f"{digest}/{target.name}",
            "sha256": digest,
            "mime": mime,
            "bytes": len(data),
        }

    def resolve(self, attachment: dict) -> Path | None:
        try:
            digest = attachment["sha256"]
            target = self._target(digest, attachment["name"])
            if attachment["path"] != f"{digest}/{target.name}" or not target.is_file():
                return None
            return target
        except (KeyError, TypeError, ValueError, OSError):
            return None

    def for_question(self, entry_id: int, digest: str) -> tuple[dict, Path] | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """SELECT n.attachments_json FROM notebook_entries n
                LEFT JOIN sessions s ON s.id=n.session_id
                WHERE n.id=? AND (n.session_id IS NULL OR s.deleted_at IS NULL)""",
                (entry_id,),
            ).fetchone()
        if row is None:
            return None
        for attachment in json.loads(row[0] or "[]"):
            if attachment.get("sha256") == digest:
                path = self.resolve(attachment)
                return (attachment, path) if path else None
        return None

    def add_to_question(self, entry_id: int, attachment: dict) -> None:
        with sqlite3.connect(self.db_path, timeout=30) as conn:
            row = conn.execute("SELECT attachments_json FROM notebook_entries WHERE id=?", (entry_id,)).fetchone()
            if row is None:
                raise LookupError("Question not found")
            existing = json.loads(row[0] or "[]")
            if not any(item["sha256"] == attachment["sha256"] for item in existing):
                existing.append(attachment)
                conn.execute(
                    "UPDATE notebook_entries SET attachments_json=? WHERE id=?",
                    (json.dumps(existing, ensure_ascii=False), entry_id),
                )
