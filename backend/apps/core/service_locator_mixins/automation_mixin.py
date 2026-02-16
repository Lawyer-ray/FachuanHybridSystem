"""Module for automation mixin."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar

_T = TypeVar("_T")


class _ServiceLocatorStub:
    """Stub base so mypy knows mixins have get_or_create / get_*_service at class level."""

    _services: ClassVar[dict[str, Any]]

    @classmethod
    def get_or_create(cls, name: str, factory: Callable[[], _T]) -> _T:
        raise NotImplementedError

    @classmethod
    def get(cls, name: str) -> Any | None: ...

    @classmethod
    def register(cls, name: str, service: Any) -> None: ...

    # Cross-mixin references (business_mixin methods used by automation_mixin)
    @classmethod
    def get_case_service(cls) -> Any: ...
    @classmethod
    def get_client_service(cls) -> Any: ...
    @classmethod
    def get_lawyer_service(cls) -> Any: ...
    @classmethod
    def get_case_number_service(cls) -> Any: ...
    @classmethod
    def get_case_chat_service(cls) -> Any: ...
    @classmethod
    def get_caselog_service(cls) -> Any: ...
    @classmethod
    def get_reminder_service(cls) -> Any: ...
    @classmethod
    def get_llm_service(cls) -> Any: ...
    @classmethod
    def get_contract_service(cls) -> Any: ...
    @classmethod
    def get_contract_query_service(cls) -> Any: ...
    @classmethod
    def get_contract_folder_binding_service(cls) -> Any: ...
    @classmethod
    def get_document_processing_service(cls) -> Any: ...


if TYPE_CHECKING:
    from apps.core.protocols import (
        IAccountSelectionStrategy,
        IAutoLoginService,
        IAutomationService,
        IAutoNamerService,
        IAutoTokenAcquisitionService,
        IBrowserService,
        ICaptchaService,
        ICourtDocumentRecognitionService,
        ICourtDocumentService,
        ICourtPleadingSignalsService,
        ICourtSMSService,
        ICourtTokenStoreService,
        IDocumentProcessingService,
        IMonitorService,
        IOcrService,
        IPerformanceMonitorService,
        IPreservationQuoteService,
        ISecurityService,
        ITokenService,
        IValidatorService,
    )


class AutomationServiceLocatorMixin(_ServiceLocatorStub):
    @classmethod
    def get_ai_service(cls) -> Any:
        from apps.automation.services.ai.ai_service import AIService

        return cls.get_or_create("ai_service", lambda: AIService(llm_service=cls.get_llm_service()))

    @classmethod
    def get_config_service(cls) -> Any:
        from apps.automation.services.config_service import AutomationConfigService

        return cls.get_or_create("config_service", AutomationConfigService)

    @classmethod
    def get_auto_token_acquisition_service(cls) -> IAutoTokenAcquisitionService:
        from apps.core.dependencies import build_auto_token_acquisition_service

        return cls.get_or_create("auto_token_acquisition_service", build_auto_token_acquisition_service)

    @classmethod
    def get_account_selection_strategy(cls) -> IAccountSelectionStrategy:
        from apps.core.dependencies import build_account_selection_strategy

        return cls.get_or_create("account_selection_strategy", build_account_selection_strategy)

    @classmethod
    def get_auto_login_service(cls) -> IAutoLoginService:
        from apps.core.dependencies import build_auto_login_service

        return cls.get_or_create("auto_login_service", build_auto_login_service)

    @classmethod
    def get_token_service(cls) -> ITokenService:
        from apps.core.dependencies import build_token_service

        return cls.get_or_create("token_service", build_token_service)

    @classmethod
    def get_court_token_store_service(cls) -> ICourtTokenStoreService:
        from apps.core.dependencies import build_court_token_store_service

        return cls.get_or_create("court_token_store_service", build_court_token_store_service)

    @classmethod
    def get_browser_service(cls) -> IBrowserService:
        from apps.core.dependencies import build_browser_service

        return cls.get_or_create("browser_service", build_browser_service)

    @classmethod
    def get_captcha_service(cls) -> ICaptchaService:
        from apps.core.dependencies import build_captcha_service

        return cls.get_or_create("captcha_service", build_captcha_service)

    @classmethod
    def get_ocr_service(cls) -> IOcrService:
        from apps.core.dependencies import build_ocr_service

        return cls.get_or_create("ocr_service", build_ocr_service)

    @classmethod
    def get_court_document_service(cls) -> ICourtDocumentService:
        from apps.core.dependencies import build_court_document_service

        return cls.get_or_create("court_document_service", build_court_document_service)

    @classmethod
    def get_monitor_service(cls) -> IMonitorService:
        from apps.core.dependencies import build_monitor_service

        return cls.get_or_create("monitor_service", build_monitor_service)

    @classmethod
    def get_security_service(cls) -> ISecurityService:
        from apps.core.dependencies import build_security_service

        return cls.get_or_create("security_service", build_security_service)

    @classmethod
    def get_validator_service(cls) -> IValidatorService:
        from apps.core.dependencies import build_validator_service

        return cls.get_or_create("validator_service", build_validator_service)

    @classmethod
    def get_preservation_quote_service(cls) -> IPreservationQuoteService:
        from apps.core.dependencies import build_preservation_quote_service

        return cls.get_or_create("preservation_quote_service", build_preservation_quote_service)

    @classmethod
    def get_document_processing_service(cls) -> IDocumentProcessingService:
        from apps.core.dependencies import build_document_processing_service

        return cls.get_or_create("document_processing_service", build_document_processing_service)

    @classmethod
    def get_document_processor_service(cls) -> IDocumentProcessingService:
        return cls.get_document_processing_service()

    @classmethod
    def get_auto_namer_service(cls) -> IAutoNamerService:
        from apps.core.dependencies import build_auto_namer_service

        return cls.get_or_create("auto_namer_service", build_auto_namer_service)

    @classmethod
    def get_automation_service(cls) -> IAutomationService:
        from apps.core.dependencies import build_automation_service

        return cls.get_or_create("automation_service", build_automation_service)

    @classmethod
    def get_performance_monitor_service(cls) -> IPerformanceMonitorService:
        from apps.core.dependencies import build_performance_monitor_service

        return cls.get_or_create("performance_monitor_service", build_performance_monitor_service)

    @classmethod
    def get_court_sms_service(cls) -> ICourtSMSService:
        from apps.core.dependencies import build_court_sms_service_with_deps

        return cls.get_or_create(
            "court_sms_service",
            lambda: build_court_sms_service_with_deps(
                case_service=cls.get_case_service(),
                document_processing_service=cls.get_document_processing_service(),
                case_number_service=cls.get_case_number_service(),
                client_service=cls.get_client_service(),
                lawyer_service=cls.get_lawyer_service(),
                case_chat_service=cls.get_case_chat_service(),
                caselog_service=cls.get_caselog_service(),
                reminder_service=cls.get_reminder_service(),
            ),
        )

    @classmethod
    def get_court_document_recognition_service(cls) -> ICourtDocumentRecognitionService:
        from apps.core.dependencies import build_court_document_recognition_service

        return cls.get_or_create(
            "court_document_recognition_service",
            build_court_document_recognition_service,
        )

    @classmethod
    def get_court_pleading_signals_service(cls) -> ICourtPleadingSignalsService:
        from apps.core.dependencies import build_court_pleading_signals_service

        return cls.get_or_create("court_pleading_signals_service", build_court_pleading_signals_service)

    @classmethod
    def get_task_service(cls) -> Any:
        from apps.automation.models import ScraperTask

        return cls.get_or_create("task_service", lambda: ScraperTask)
