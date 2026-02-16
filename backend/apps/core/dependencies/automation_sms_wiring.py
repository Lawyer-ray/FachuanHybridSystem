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
    from apps.automation.integrations.chat.message_sender import ChatProviderMessageSender
    from apps.automation.services.fee_notice import FeeNoticeCheckService
    from apps.automation.services.sms.case_matcher import CaseMatcher
    from apps.automation.services.sms.case_number_extractor_service import CaseNumberExtractorService
    from apps.automation.services.sms.coordinator.court_sms_orchestrator import CourtSMSOrchestrator
    from apps.automation.services.sms.court_sms_repository import CourtSMSRepository
    from apps.automation.services.sms.court_sms_service import CourtSMSService
    from apps.automation.services.sms.document_attachment_service import DocumentAttachmentService
    from apps.automation.services.sms.matching import DocumentParserService, PartyMatchingService
    from apps.automation.services.sms.processing.stage_processor import CourtSMSStageProcessor
    from apps.automation.services.sms.sms_notification_service import SMSNotificationService
    from apps.automation.services.sms.sms_parser_service import SMSParserService
    from apps.automation.services.sms.sms_processing_workflow import CourtSMSProcessingWorkflow
    from apps.automation.services.sms.stages import (
        SMSDownloadingStage,
        SMSMatchingStage,
        SMSNotifyingStage,
        SMSParsingStage,
        SMSRenamingStage,
    )
    from apps.automation.services.sms.submission.sms_submission_service import SMSSubmissionService
    from apps.automation.services.sms.task_queue import DjangoQTaskQueue
    from apps.automation.tasks import execute_scraper_task

    task_queue = DjangoQTaskQueue()
    repo = CourtSMSRepository()

    party_matching_service = PartyMatchingService(
        client_service=client_service,
        lawyer_service=lawyer_service,
    )
    document_parser_service = DocumentParserService(  # type: ignore[call-arg]
        client_service=client_service,
        lawyer_service=lawyer_service,
        document_processing_service=document_processing_service,
    )
    parser = SMSParserService(party_matching_service=party_matching_service)  # type: ignore[call-arg]
    matcher = CaseMatcher(
        case_service=case_service,
        document_parser_service=document_parser_service,
        party_matching_service=party_matching_service,
    )
    case_number_extractor = CaseNumberExtractorService(  # type: ignore[call-arg]
        document_processing_service=document_processing_service,
        case_service=case_service,
        case_number_service=case_number_service,
    )

    document_attachment = DocumentAttachmentService(case_service=case_service)
    notification = SMSNotificationService(  # type: ignore[call-arg, call-arg]
        case_chat_service=case_chat_service,
        fee_check_service=FeeNoticeCheckService(),  # type: ignore[misc]
        chat_message_sender=ChatProviderMessageSender(),
    )

    parsing_stage = SMSParsingStage(parser=parser)
    downloading_stage = SMSDownloadingStage(task_queue=task_queue, execute_scraper_task=execute_scraper_task)  # type: ignore[call-arg, call-arg, no-untyped-call]
    matching_stage = SMSMatchingStage(  # type: ignore[call-arg]
        matcher=matcher,
        case_number_extractor=case_number_extractor,
        case_service=case_service,
        lawyer_service=lawyer_service,
        caselog_service=caselog_service,
    )
    renaming_stage = SMSRenamingStage(  # type: ignore[call-arg, call-arg]
        document_attachment=document_attachment,
        case_number_extractor=case_number_extractor,
        matcher=matcher,
        lawyer_service=lawyer_service,
        caselog_service=caselog_service,
        reminder_service=reminder_service,
    )
    notifying_stage = SMSNotifyingStage(
        notification_service=notification,
        document_attachment_service=document_attachment,
    )

    processor = CourtSMSStageProcessor(
        parsing_stage=parsing_stage,
        downloading_stage=downloading_stage,
        matching_stage=matching_stage,
        renaming_stage=renaming_stage,
        notifying_stage=notifying_stage,
    )
    workflow = CourtSMSProcessingWorkflow(repo=repo, processor=processor)
    orchestrator = CourtSMSOrchestrator(workflow=workflow, repo=repo)

    submission_service = SMSSubmissionService(  # type: ignore[call-arg, call-arg]
        case_service=case_service,
        lawyer_service=lawyer_service,
        caselog_service=caselog_service,
        task_queue=task_queue,
    )

    return CourtSMSService(  # type: ignore[return-value, call-arg, call-arg, call-arg, call-arg, call-arg, call-arg, call-arg, call-arg]
        parser=parser,
        matcher=matcher,
        case_number_extractor=case_number_extractor,
        document_attachment=document_attachment,
        notification=notification,
        case_service=case_service,
        document_processing_service=document_processing_service,
        case_number_service=case_number_service,
        client_service=client_service,
        lawyer_service=lawyer_service,
        case_chat_service=case_chat_service,
        caselog_service=caselog_service,
        reminder_service=reminder_service,
        task_queue=task_queue,
        repo=repo,
        orchestrator=orchestrator,
        submission_service=submission_service,
    )
