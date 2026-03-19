"""Dependency injection wiring."""

from __future__ import annotations

from typing import TYPE_CHECKING

from apps.core.interfaces import ServiceLocator

from .coordinator.document_delivery_coordinator import DocumentDeliveryCoordinator

if TYPE_CHECKING:
    from apps.automation.services.sms.case_matcher import CaseMatcher
    from apps.automation.services.sms.document_renamer import DocumentRenamer
    from apps.automation.services.sms.sms_notification_service import SMSNotificationService

    from .court_document_api_client import CourtDocumentApiClient
    from .repo.document_history_repo import DocumentHistoryRepo
    from .token.document_delivery_token_service import DocumentDeliveryTokenService


def build_document_delivery_coordinator(
    *,
    case_matcher: CaseMatcher | None = None,
    document_renamer: DocumentRenamer | None = None,
    notification_service: SMSNotificationService | None = None,
    api_client: CourtDocumentApiClient | None = None,
    token_service: DocumentDeliveryTokenService | None = None,
    history_repo: DocumentHistoryRepo | None = None,
) -> DocumentDeliveryCoordinator:
    from apps.automation.integrations.chat.message_sender import ChatProviderMessageSender
    from apps.automation.services.sms.case_matcher import CaseMatcher
    from apps.automation.services.sms.document_renamer import DocumentRenamer
    from apps.automation.services.sms.matching import DocumentParserService, PartyMatchingService
    from apps.automation.services.sms.sms_notification_service import SMSNotificationService
    from apps.automation.services.token.cache_manager import cache_manager
    from apps.fee_notice.services import FeeNoticeCheckService

    from .api.document_delivery_api_service import DocumentDeliveryApiService
    from .court_document_api_client import CourtDocumentApiClient
    from .playwright.document_delivery_playwright_service import DocumentDeliveryPlaywrightService
    from .processor.document_delivery_processor import DocumentDeliveryProcessor
    from .repo.document_history_repo import DocumentHistoryRepo
    from .token.document_delivery_token_service import DocumentDeliveryTokenService

    case_service = ServiceLocator.get_case_service()
    client_service = ServiceLocator.get_client_service()
    lawyer_service = ServiceLocator.get_lawyer_service()
    case_chat_service = ServiceLocator.get_case_chat_service()
    case_log_service = ServiceLocator.get_caselog_service()
    case_number_service = ServiceLocator.get_case_number_service()
    organization_service = ServiceLocator.get_organization_service()
    browser_service = ServiceLocator.get_browser_service()
    auto_token_service = ServiceLocator.get_auto_token_acquisition_service()

    history_repo = history_repo or DocumentHistoryRepo()
    api_client = api_client or CourtDocumentApiClient()
    token_service = token_service or DocumentDeliveryTokenService(
        cache_manager=cache_manager,
        auto_token_service=auto_token_service,
    )

    if case_matcher is None:
        party_matching_service = PartyMatchingService(
            client_service=client_service,
            lawyer_service=lawyer_service,
        )
        document_parser_service = DocumentParserService(
            client_service=client_service,
            lawyer_service=lawyer_service,
        )
        case_matcher = CaseMatcher(
            case_service=case_service,
            document_parser_service=document_parser_service,
            party_matching_service=party_matching_service,
        )

    if document_renamer is None:
        document_renamer = DocumentRenamer()

    if notification_service is None:
        notification_service = SMSNotificationService(
            case_chat_service=case_chat_service,
            fee_check_service=FeeNoticeCheckService(),
            chat_message_sender=ChatProviderMessageSender(),
        )

    processor = DocumentDeliveryProcessor(
        case_matcher=case_matcher,
        document_renamer=document_renamer,
        notification_service=notification_service,
        case_log_service=case_log_service,
        case_number_service=case_number_service,
        history_repo=history_repo,
    )

    api_service = DocumentDeliveryApiService(
        api_client=api_client,
        processor=processor,
        history_repo=history_repo,
    )

    playwright_service = DocumentDeliveryPlaywrightService(
        browser_service=browser_service,
        case_matcher=case_matcher,
        document_renamer=document_renamer,
        notification_service=notification_service,
        organization_service=organization_service,
        processor=processor,
        history_repo=history_repo,
    )

    return DocumentDeliveryCoordinator(
        token_service=token_service,
        api_service=api_service,
        playwright_service=playwright_service,
        processor=processor,
    )
