"""Module for automation sms."""

from __future__ import annotations

"""短信自动化依赖聚合入口 — 按功能域拆分为 entry / wiring 子模块,此文件保留为 re-export 入口."""


from .automation_sms_entry import build_court_sms_service, build_court_sms_service_ctx
from .automation_sms_wiring import build_court_sms_service_with_deps

__all__: list[str] = [
    "build_court_sms_service",
    "build_court_sms_service_ctx",
    "build_court_sms_service_with_deps",
]
