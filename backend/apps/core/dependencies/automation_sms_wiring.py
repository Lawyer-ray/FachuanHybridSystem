"""Dependency injection wiring."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from apps.core.protocols import ICourtSMSService


def build_court_sms_service_with_deps(
    *,
    case_service: Any,
    document_processing_service: Any,
    case_number_service: Any,
    client_service: Any,
    lawyer_service: Any,
    case_chat_service: Any,
    caselog_service: Any,
    reminder_service: Any,
) -> ICourtSMSService:
    from apps.automation.services.sms.case_matcher import CaseMatcher
    from apps.automation.services.sms.case_number_extractor_service import CaseNumberExtractorService
    from apps.automation.services.sms.court_sms_service import CourtSMSService
    from apps.automation.services.sms.document_attachment_service import DocumentAttachmentService
    from apps.automation.services.sms.matching import DocumentParserService, PartyMatchingService
    from apps.automation.services.sms.sms_notification_service import SMSNotificationService
    from apps.automation.services.sms.sms_parser_service import SMSParserService

    party_matching_service = PartyMatchingService(
        client_service=client_service,
        lawyer_service=lawyer_service,
    )
    
    document_parser_service = DocumentParserService(
        client_service=client_service,
        lawyer_service=lawyer_service,
    )
    
    parser = SMSParserService(
        client_service=client_service,
        party_matching_service=party_matching_service,
    )
    
    matcher = CaseMatcher(
        case_service=case_service,
        document_parser_service=document_parser_service,
        party_matching_service=party_matching_service,
    )
    
    case_number_extractor = CaseNumberExtractorService(
        document_processing_service=document_processing_service,
        case_service=case_service,
        case_number_service=case_number_service,
    )

    document_attachment = DocumentAttachmentService(case_service=case_service)
    
    notification = SMSNotificationService(
        case_chat_service=case_chat_service,
    )

    return CourtSMSService(  # type: ignore[return-value]
        parser=parser,
        matcher=matcher,
        case_number_extractor=case_number_extractor,
        document_attachment=document_attachment,
        notification=notification,
        case_service=case_service,
        client_service=client_service,
        lawyer_service=lawyer_service,
        case_chat_service=case_chat_service,
        document_processing_service=document_processing_service,
        case_number_service=case_number_service,
    )


def build_sms_case_service() -> Any:
    from apps.core.service_locator import ServiceLocator

    return ServiceLocator.get_case_service()


def build_sms_client_service() -> Any:
    from apps.core.service_locator import ServiceLocator

    return ServiceLocator.get_client_service()


def build_sms_lawyer_service() -> Any:
    from apps.core.service_locator import ServiceLocator

    return ServiceLocator.get_lawyer_service()


def build_sms_case_chat_service() -> Any:
    from apps.core.service_locator import ServiceLocator

    return ServiceLocator.get_case_chat_service()


def build_sms_case_log_service() -> Any:
    from apps.core.service_locator import ServiceLocator

    return ServiceLocator.get_caselog_service()


def build_sms_document_processing_service() -> Any:
    from apps.core.service_locator import ServiceLocator

    return ServiceLocator.get_document_processing_service()


def build_sms_case_number_service() -> Any:
    from apps.core.service_locator import ServiceLocator

    return ServiceLocator.get_case_number_service()
