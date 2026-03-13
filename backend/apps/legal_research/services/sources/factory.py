from __future__ import annotations

from collections.abc import Callable
from typing import cast

from .base import CaseSourceClient
from .weike import WeikeCaseClient


class UnsupportedCaseSourceError(ValueError):
    """未注册或不支持的数据源。"""


class SourceClientFactory:
    _builders: dict[str, Callable[[], CaseSourceClient]] = {
        "weike": cast(Callable[[], CaseSourceClient], WeikeCaseClient),
    }

    @classmethod
    def register(cls, *, source: str, builder: Callable[[], CaseSourceClient]) -> None:
        key = source.strip().lower()
        if not key:
            raise ValueError("source 不能为空")
        cls._builders[key] = builder

    @classmethod
    def create(cls, source: str | None) -> CaseSourceClient:
        key = (source or "weike").strip().lower()
        builder = cls._builders.get(key)
        if builder is None:
            raise UnsupportedCaseSourceError(f"不支持的数据源: {source or '<empty>'}")
        return builder()


def get_case_source_client(source: str | None) -> CaseSourceClient:
    return SourceClientFactory.create(source)
