"""File storage behind a small interface so S3/MinIO can replace the local backend.

Storage keys are generated server-side; user-supplied filenames are never used as paths.
"""

import uuid
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings


class Storage(Protocol):
    def put(self, data: bytes) -> str: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # Keys are UUID hex strings; reject anything else outright.
        uuid.UUID(hex=key)
        p = (self.root / key[:2] / key).resolve()
        if self.root not in p.parents:
            raise ValueError("invalid storage key")
        return p

    def put(self, data: bytes) -> str:
        key = uuid.uuid4().hex
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return key

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


def get_storage() -> Storage:
    return LocalStorage(get_settings().storage_dir)
