"""Blob contract and atomic local implementation. R2 arrives with publication."""

import os
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile
from typing import Protocol


class BlobStore(Protocol):
    def exists(self, key: str) -> bool: ...
    def read(self, key: str) -> bytes: ...
    def write(self, key: str, payload: bytes) -> None: ...


class LocalBlobStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        parts = PurePosixPath(key)
        if not key or parts.is_absolute() or ".." in parts.parts or "\\" in key:
            raise ValueError("Blob key must be a relative POSIX path without traversal.")
        target = (self.root / key).resolve()
        if not target.is_relative_to(self.root) or target == self.root:
            raise ValueError("Blob key escapes storage root.")
        return target

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def write(self, key: str, payload: bytes) -> None:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with NamedTemporaryFile(dir=target.parent, delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
