"""Dependency injection wiring.

仅保留生产消费的转发函数；其余转发由各业务域自身的 wiring 模块或
`ServiceLocator` 直接提供。
"""

from __future__ import annotations

from typing import Any

from apps.core.interfaces import ServiceLocator


def get_case_service() -> Any:
    return ServiceLocator.get_case_service()


def get_llm_service() -> Any:  # pragma: no cover
    return ServiceLocator.get_llm_service()


def get_baoquan_token_service() -> Any:
    return ServiceLocator.get_baoquan_token_service()
