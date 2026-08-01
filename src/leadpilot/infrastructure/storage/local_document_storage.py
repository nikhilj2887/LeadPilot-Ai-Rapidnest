from __future__ import annotations

from pathlib import Path, PurePosixPath


class LocalDocumentStorage:
    provider_name = "local"

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def _path(self, key: str) -> Path:
        value = PurePosixPath(key)
        if value.is_absolute() or ".." in value.parts or not value.parts:
            raise ValueError("Invalid document storage key.")
        target = self._root.joinpath(*value.parts).resolve()
        if not target.is_relative_to(self._root):
            raise ValueError("Invalid document storage key.")
        return target

    def save(self, key: str, content: bytes) -> None:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete(self, key: str) -> None:
        target = self._path(key)
        if target.exists():
            target.unlink()

    def get_size(self, key: str) -> int:
        return self._path(key).stat().st_size
