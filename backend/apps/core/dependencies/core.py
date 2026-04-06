"""Module for core."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from apps.core.protocols import (
        IBaoquanTokenService,
        IBusinessConfigService,
        ICauseCourtQueryService,
        IConversationHistoryService,
        ILLMService,
        ISystemConfigService,
    )


def build_system_config_service() -> ISystemConfigService:
    from apps.core.services import SystemConfigService

    return SystemConfigService()


def build_business_config_service() -> IBusinessConfigService:
    from apps.core.services import BusinessConfigService

    return BusinessConfigService()


def build_llm_service() -> ILLMService:
    from apps.core.llm.config import LLMConfig
    from apps.core.llm.service import LLMService
    from apps.core.protocols import ILLMService

    return cast(
        ILLMService,
        LLMService(
            backend_configs=LLMConfig.get_backend_configs(),
            default_backend=LLMConfig.get_default_backend(),
        ),
    )


def build_conversation_history_service() -> IConversationHistoryService:
    from apps.core.services.conversation_history_service import ConversationHistoryService

    return ConversationHistoryService()


def build_cause_court_query_service() -> ICauseCourtQueryService:
    from apps.core.protocols import ICauseCourtQueryService
    from apps.core.services.cause_court_query_service import CauseCourtQueryService

    return cast(ICauseCourtQueryService, CauseCourtQueryService())


def build_baoquan_token_service() -> IBaoquanTokenService:
    from apps.core.services.court_tokens.baoquan_token_service import BaoquanTokenService

    return BaoquanTokenService()


def build_task_submission_service() -> Any:
    from apps.core.tasking import TaskSubmissionService

    return TaskSubmissionService()


def build_task_scheduler() -> Any:
    from apps.core.tasking import DjangoQTaskScheduler

    return DjangoQTaskScheduler()


def build_system_update_service() -> Any:
    from apps.core.services.system_update_service import SystemUpdateService

    return SystemUpdateService(task_submission_service=build_task_submission_service())
