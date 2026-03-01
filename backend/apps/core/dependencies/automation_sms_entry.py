"""Module for automation sms entry."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.core.protocols import ICourtSMSService


def build_court_sms_service() -> ICourtSMSService:
    raise RuntimeError(
        "build_court_sms_service 已改为显式注入依赖."
        "请在 ServiceLocator 的组合根处调用 build_court_sms_service_with_deps."
    )


def build_court_sms_service_ctx() -> ICourtSMSService:
    from apps.core.interfaces import ServiceLocator

    from .automation_adapters import build_document_processing_service
    from .automation_sms_wiring import build_court_sms_service_with_deps
    from .business_case import (
        build_case_chat_service,
        build_case_log_service,
        build_case_number_service,
    )
    from .business_organization import build_reminder_service

    return build_court_sms_service_with_deps(
        case_service=ServiceLocator.get_case_service(),
        document_processing_service=build_document_processing_service(),
        case_number_service=build_case_number_service(),
        client_service=ServiceLocator.get_client_service(),
        lawyer_service=ServiceLocator.get_lawyer_service(),
        case_chat_service=build_case_chat_service(),
        caselog_service=build_case_log_service(),
        reminder_service=build_reminder_service(),
    )
