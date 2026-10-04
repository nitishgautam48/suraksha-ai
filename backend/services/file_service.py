"""Local file storage (prototype). Files are stored under random names outside any web root."""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from backend.config import settings
from backend.models import UploadedFile
from backend.security.file_validation import ValidatedFile


def _user_dir(user_id: uuid.UUID) -> Path:
    path = settings.UPLOAD_DIR / str(user_id)
    path.mkdir(parents=True, exist_ok=True, mode=0o750)
    return path


def save_upload(db: Session, user_id: uuid.UUID, vf: ValidatedFile) -> UploadedFile:
    file_id = uuid.uuid4()
    path = _user_dir(user_id) / f"{file_id.hex}{vf.ext}"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
    with os.fdopen(fd, "wb") as fh:
        fh.write(vf.data)
    original = (vf.original_name or "")[-255:] or None
    record = UploadedFile(
        id=file_id,
        user_id=user_id,
        file_path=str(path),
        file_type=vf.kind,
        original_name=original,
        mime_type=vf.mime,
        size_bytes=len(vf.data),
        sha256=hashlib.sha256(vf.data).hexdigest(),
    )
    db.add(record)
    db.flush()
    return record


def read_file(record: UploadedFile) -> bytes:
    path = Path(record.file_path).resolve()
    if not str(path).startswith(str(settings.UPLOAD_DIR.resolve())):
        raise PermissionError("File path escapes upload directory")
    return path.read_bytes()


def discard_file(db: Session, record: UploadedFile) -> None:
    """Delete the stored bytes of an upload but keep its metadata row (size, hash, type)."""
    path = Path(record.file_path).resolve()
    if str(path).startswith(str(settings.UPLOAD_DIR.resolve())):
        path.unlink(missing_ok=True)
    record.deleted_at = datetime.now(UTC)
    db.flush()


def delete_user_files(user_id: uuid.UUID) -> None:
    folder = settings.UPLOAD_DIR / str(user_id)
    if folder.is_dir():
        for f in folder.iterdir():
            f.unlink(missing_ok=True)
        folder.rmdir()
