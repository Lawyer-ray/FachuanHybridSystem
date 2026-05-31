"""Module for workbench mixin."""

from __future__ import annotations

from typing import Any

from .automation_mixin import _ServiceLocatorStub

class WorkbenchServiceLocatorMixin(_ServiceLocatorStub):
    @classmethod
    def get_workbench_session_service(cls) -> Any:
        from apps.workbench.services.session_service import WorkbenchSessionService

        return cls.get_or_create("workbench_session_service", WorkbenchSessionService)

    @classmethod
    def get_workbench_message_service(cls) -> Any:
        from apps.workbench.services.message_service import WorkbenchMessageService

        return cls.get_or_create("workbench_message_service", WorkbenchMessageService)

    @classmethod
    def get_workbench_batch_service(cls) -> Any:
        from apps.workbench.services.batch_service import BatchAnalysisService

        return cls.get_or_create("workbench_batch_service", BatchAnalysisService)

    @classmethod
    def get_workbench_chat_service(cls) -> Any:
        from apps.workbench.services.chat_service import WorkbenchChatService

        return cls.get_or_create("workbench_chat_service", WorkbenchChatService)
