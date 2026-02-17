"""Module for legacy service locator."""

from __future__ import annotations

from typing import Any, ClassVar

from apps.core.protocols import (
    IAccountSelectionStrategy,
    IAutoLoginService,
    IAutomationService,
    IAutoNamerService,
    IAutoTokenAcquisitionService,
    IBrowserService,
    ICaptchaService,
    ICaseChatService,
    ICaseLogService,
    ICaseNumberService,
    ICaseService,
    IClientService,
    IContractPaymentService,
    IContractService,
    ICourtDocumentRecognitionService,
    ICourtDocumentService,
    ICourtSMSService,
    IDocumentProcessingService,
    ILawFirmService,
    ILawyerService,
    IMonitorService,
    IOrganizationService,
    IPerformanceMonitorService,
    IPreservationQuoteService,
    ISecurityService,
    ITokenService,
    IValidatorService,
)


class LegacyServiceLocator:
    _services: ClassVar[dict[str, Any]] = {}

    @classmethod
    def register(cls, name: str, service: Any) -> None:
        cls._services[name] = service

    @classmethod
    def get(cls, name: str) -> Any | None:
        return cls._services.get(name)

    @classmethod
    def clear(cls, name: str | None = None) -> None:
        if name is not None:
            cls._services.pop(name, None)
        else:
            cls._services.clear()

    @classmethod
    def get_lawyer_service(cls) -> ILawyerService:
        service = cls.get("lawyer_service")
        if service is None:
            from apps.organization.services import LawyerServiceAdapter

            service = LawyerServiceAdapter()  # type: ignore
            cls.register("lawyer_service", service)
        return service

    @classmethod
    def get_client_service(cls) -> IClientService:
        service = cls.get("client_service")
        if service is None:
            from apps.client.services import ClientServiceAdapter

            service = ClientServiceAdapter()  # type: ignore
            cls.register("client_service", service)
        return service

    @classmethod
    def get_contract_service(cls) -> IContractService:
        service = cls.get("contract_service")
        if service is None:
            from apps.contracts.services import ContractServiceAdapter

            service = ContractServiceAdapter()
            cls.register("contract_service", service)
        return service  # type: ignore

    @classmethod
    def get_case_service(cls) -> ICaseService:
        service = cls.get("case_service")
        if service is None:
            from apps.cases.services import CaseServiceAdapter

            service = CaseServiceAdapter()
            cls.register("case_service", service)
        return service  # type: ignore[return-value]

    @classmethod
    def get_lawfirm_service(cls) -> ILawFirmService:
        service = cls.get("lawfirm_service")
        if service is None:
            from apps.organization.services import LawFirmServiceAdapter

            service = LawFirmServiceAdapter()
            cls.register("lawfirm_service", service)
        return service

    @classmethod
    def get_auto_token_acquisition_service(cls) -> IAutoTokenAcquisitionService:
        service = cls.get("auto_token_acquisition_service")
        if service is None:
            from apps.automation.services.token.auto_token_acquisition_service import AutoTokenAcquisitionService

            service = AutoTokenAcquisitionService()
            cls.register("auto_token_acquisition_service", service)
        return service

    @classmethod
    def get_account_selection_strategy(cls) -> IAccountSelectionStrategy:
        service = cls.get("account_selection_strategy")
        if service is None:
            from apps.automation.services.token.account_selection_strategy import AccountSelectionStrategy

            service = AccountSelectionStrategy()
            cls.register("account_selection_strategy", service)
        return service

    @classmethod
    def get_auto_login_service(cls) -> IAutoLoginService:
        service = cls.get("auto_login_service")
        if service is None:
            from apps.automation.services.token.auto_login_service import AutoLoginService

            service = AutoLoginService()
            cls.register("auto_login_service", service)
        return service

    @classmethod
    def get_token_service(cls) -> ITokenService:
        service = cls.get("token_service")
        if service is None:
            from apps.automation.services.scraper.core.token_service import TokenServiceAdapter

            service = TokenServiceAdapter()
            cls.register("token_service", service)
        return service

    @classmethod
    def get_browser_service(cls) -> IBrowserService:
        service = cls.get("browser_service")
        if service is None:
            from apps.automation.services.scraper.core.browser_service import BrowserServiceAdapter

            service = BrowserServiceAdapter()
            cls.register("browser_service", service)
        return service

    @classmethod
    def get_captcha_service(cls) -> ICaptchaService:
        service = cls.get("captcha_service")
        if service is None:
            from apps.automation.services.captcha.captcha_recognition_service import CaptchaServiceAdapter

            service = CaptchaServiceAdapter()
            cls.register("captcha_service", service)
        return service

    @classmethod
    def get_court_document_service(cls) -> ICourtDocumentService:
        service = cls.get("court_document_service")
        if service is None:
            from apps.automation.services.scraper.court_document_service import CourtDocumentServiceAdapter

            service = CourtDocumentServiceAdapter()
            cls.register("court_document_service", service)
        return service

    @classmethod
    def get_monitor_service(cls) -> IMonitorService:
        service = cls.get("monitor_service")
        if service is None:
            from apps.automation.services.scraper.core.monitor_service import MonitorServiceAdapter

            service = MonitorServiceAdapter()
            cls.register("monitor_service", service)
        return service

    @classmethod
    def get_security_service(cls) -> ISecurityService:
        service = cls.get("security_service")
        if service is None:
            from apps.automation.services.scraper.core.security_service import SecurityServiceAdapter

            service = SecurityServiceAdapter()
            cls.register("security_service", service)
        return service

    @classmethod
    def get_validator_service(cls) -> IValidatorService:
        service = cls.get("validator_service")
        if service is None:
            from apps.automation.services.scraper.core.validator_service import ValidatorServiceAdapter

            service = ValidatorServiceAdapter()
            cls.register("validator_service", service)
        return service

    @classmethod
    def get_contract_payment_service(cls) -> IContractPaymentService:
        service = cls.get("contract_payment_service")
        if service is None:
            from apps.contracts.services.contract_payment_service import ContractPaymentService

            service = ContractPaymentService()
            cls.register("contract_payment_service", service)
        return service

    @classmethod
    def get_caselog_service(cls) -> ICaseLogService:
        service = cls.get("caselog_service")
        if service is None:
            from apps.cases.services.caselog_service import CaseLogService

            service = CaseLogService()
            cls.register("caselog_service", service)
        return service

    @classmethod
    def get_preservation_quote_service(cls) -> IPreservationQuoteService:
        service = cls.get("preservation_quote_service")
        if service is None:
            from apps.automation.services.insurance.preservation_quote_service_adapter import (
                PreservationQuoteServiceAdapter,
            )

            service = PreservationQuoteServiceAdapter()
            cls.register("preservation_quote_service", service)
        return service

    @classmethod
    def get_document_processing_service(cls) -> IDocumentProcessingService:
        service = cls.get("document_processing_service")
        if service is None:
            from apps.automation.services.document.document_processing_service_adapter import (
                DocumentProcessingServiceAdapter,
            )

            service = DocumentProcessingServiceAdapter()
            cls.register("document_processing_service", service)
        return service

    @classmethod
    def get_auto_namer_service(cls) -> IAutoNamerService:
        service = cls.get("auto_namer_service")
        if service is None:
            from apps.automation.services.ai.auto_namer_service_adapter import AutoNamerServiceAdapter

            service = AutoNamerServiceAdapter()
            cls.register("auto_namer_service", service)
        return service

    @classmethod
    def get_automation_service(cls) -> IAutomationService:
        service = cls.get("automation_service")
        if service is None:
            from apps.automation.services.automation_service_adapter import AutomationServiceAdapter

            service = AutomationServiceAdapter()
            cls.register("automation_service", service)
        return service

    @classmethod
    def get_performance_monitor_service(cls) -> IPerformanceMonitorService:
        service = cls.get("performance_monitor_service")
        if service is None:
            from apps.automation.services.token.performance_monitor_service_adapter import (
                PerformanceMonitorServiceAdapter,
            )

            service = PerformanceMonitorServiceAdapter()
            cls.register("performance_monitor_service", service)
        return service

    @classmethod
    def get_court_sms_service(cls) -> ICourtSMSService:
        service = cls.get("court_sms_service")
        if service is None:
            from apps.automation.services.sms.court_sms_service import CourtSMSService

            service = CourtSMSService()
            cls.register("court_sms_service", service)
        return service

    @classmethod
    def get_case_chat_service(cls) -> ICaseChatService:
        service = cls.get("case_chat_service")
        if service is None:
            from apps.cases.services.case_chat_service import CaseChatService

            service = CaseChatService()
            cls.register("case_chat_service", service)
        return service

    @classmethod
    def get_organization_service(cls) -> IOrganizationService:
        service = cls.get("organization_service")
        if service is None:
            from apps.organization.services import OrganizationServiceAdapter

            service = OrganizationServiceAdapter()  # type: ignore
            cls.register("organization_service", service)
        return service

    @classmethod
    def get_case_number_service(cls) -> ICaseNumberService:
        service = cls.get("case_number_service")
        if service is None:
            from apps.cases.services.case_number_service_adapter import CaseNumberServiceAdapter

            service = CaseNumberServiceAdapter()
            cls.register("case_number_service", service)
        return service

    @classmethod
    def get_court_document_recognition_service(cls) -> ICourtDocumentRecognitionService:
        service = cls.get("court_document_recognition_service")
        if service is None:
            from apps.automation.services.court_document_recognition.adapter import (
                CourtDocumentRecognitionServiceAdapter,
            )

            service = CourtDocumentRecognitionServiceAdapter()
            cls.register("court_document_recognition_service", service)
        return service
