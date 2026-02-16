"""Module for core mixin."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from .automation_mixin import _ServiceLocatorStub

if TYPE_CHECKING:
    from apps.core.protocols import (
        IBaoquanTokenService,
        IBusinessConfigService,
        ICauseCourtQueryService,
        IConversationHistoryService,
        ILLMService,
        ISystemConfigService,
    )
    from apps.core.tasking import TaskSubmissionService


class CoreServiceLocatorMixin(_ServiceLocatorStub):
    @classmethod
    def get_system_config_service(cls) -> ISystemConfigService:
        from apps.core.dependencies import build_system_config_service

        return cls.get_or_create("system_config_service", build_system_config_service)

    @classmethod
    def get_business_config_service(cls) -> IBusinessConfigService:
        from apps.core.dependencies import build_business_config_service

        return cls.get_or_create("business_config_service", build_business_config_service)

    @classmethod
    def get_llm_service(cls) -> ILLMService:
        from apps.core.dependencies import build_llm_service

        return cls.get_or_create("llm_service", build_llm_service)

    @classmethod
    def get_prompt_template_service(cls) -> Any:
        from apps.core.dependencies import build_prompt_template_service

        return cls.get_or_create("prompt_template_service", build_prompt_template_service)

    @classmethod
    def get_conversation_service(cls, session_id: str | None = None, user_id: str | None = None) -> Any:
        from apps.core.services.conversation_service import ConversationService

        return ConversationService(session_id=session_id, user_id=user_id)

    @classmethod
    def get_conversation_history_service(cls) -> IConversationHistoryService:
        from apps.core.dependencies import build_conversation_history_service

        return cls.get_or_create("conversation_history_service", build_conversation_history_service)

    @classmethod
    def get_cause_court_query_service(cls) -> ICauseCourtQueryService:
        from apps.core.dependencies import build_cause_court_query_service

        return cls.get_or_create("cause_court_query_service", build_cause_court_query_service)

    @classmethod
    def get_baoquan_token_service(cls) -> IBaoquanTokenService:
        from apps.core.dependencies import build_baoquan_token_service

        return cls.get_or_create("baoquan_token_service", build_baoquan_token_service)

    @classmethod
    def get_task_submission_service(cls) -> TaskSubmissionService:
        from apps.core.dependencies import build_task_submission_service

        return cast(
            "TaskSubmissionService", cls.get_or_create("task_submission_service", build_task_submission_service)
        )
