"""Null provider — raised when storage account is missing or misconfigured."""

from __future__ import annotations

from collections.abc import Iterator
from typing import NoReturn

from .protocols import CloudFileInfo


class NullProvider:
    """Placeholder provider that raises on every operation.

    Returned by the factory when a binding references a missing or
    disabled storage account, preventing silent fallback to the
    local filesystem.
    """

    def __init__(self, reason: str = "存储账号未配置或已禁用") -> None:
        self._reason = reason

    def _fail(self) -> NoReturn:
        raise RuntimeError(self._reason)

    def list_directory(self, path: str) -> list[CloudFileInfo]:
        self._fail()

    def read_file(self, path: str) -> bytes:
        self._fail()

    def write_file(self, path: str, content: bytes) -> None:
        self._fail()

    def mkdir(self, path: str) -> None:
        self._fail()

    def exists(self, path: str) -> bool:
        self._fail()

    def is_dir(self, path: str) -> bool:
        self._fail()

    def delete_file(self, path: str) -> None:
        self._fail()

    def get_file_info(self, path: str) -> CloudFileInfo | None:
        self._fail()

    def walk(self, path: str) -> Iterator[tuple[str, list[str], list[CloudFileInfo]]]:
        self._fail()
