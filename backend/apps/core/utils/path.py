"""Module for path."""

from __future__ import annotations

import contextlib
import os
import pathlib
from collections.abc import Iterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # mypy 视角下基类取 pathlib.Path，保证 / 等操作返回完整类型；
    # 运行时按平台动态取 PosixPath/WindowsPath（pathlib.Path 不可直接子类化）
    _BasePath = pathlib.Path
else:
    _BasePath = pathlib.WindowsPath if os.name == "nt" else pathlib.PosixPath


class Path(_BasePath):
    def abspath(self) -> str:
        return str(self.resolve())

    @property
    def ext(self) -> str:
        return str(self.suffix)

    def dirname(self) -> Path:
        return Path(str(self.parent))

    def isdir(self) -> bool:
        return bool(self.is_dir())

    def makedirs_p(self) -> Path:
        self.mkdir(parents=True, exist_ok=True)
        return self

    def remove_p(self) -> Path:
        with contextlib.suppress(FileNotFoundError):
            self.unlink()
        return self

    def text(self, encoding: str = "utf-8") -> str:
        return str(self.read_text(encoding=encoding))

    def write_text(self, data: str, encoding: str = "utf-8") -> Path:  # type: ignore[override]
        super().write_text(data, encoding=encoding)
        return self

    def write_bytes(self, data: bytes) -> Path:  # type: ignore[override]
        super().write_bytes(data)
        return self

    def bytes(self) -> bytes:
        return bytes(self.read_bytes())

    def walkfiles(self, pattern: str = "*") -> Iterator[Path]:
        for p in self.rglob(pattern):
            pp = Path(str(p))
            if pp.is_file():
                yield pp

    def files(self, pattern: str = "*") -> list[Path]:
        return [Path(str(p)) for p in self.glob(pattern) if Path(str(p)).is_file()]

    def dirs(self, pattern: str = "*") -> list[Path]:
        return [Path(str(p)) for p in self.glob(pattern) if Path(str(p)).is_dir()]


__all__: list[str] = ["Path"]
