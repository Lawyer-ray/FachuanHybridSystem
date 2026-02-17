"""
服务定位器和事件总线
提供跨模块服务的统一获取入口和事件通知机制
"""

from __future__ import annotations

import logging
from typing import Any
from collections.abc import Callable

logger = logging.getLogger(__name__)

# 案件扩展协议
# 文档生成相关协议
# 跨模块依赖所需的通用协议
from apps.core.protocols import (
    IBusinessConfigService,
    ICaseAssignmentService,
    ICaseMaterialService,
    ICauseCourtQueryService,
    IContractGenerationService,
    IConversationHistoryService,
    IDocumentService,
    IDocumentTemplateBindingService,
    IEvidenceListPlaceholderService,
    IEvidenceQueryService,
    IGenerationTaskService,
    ILLMService,
    IPromptVersionService,
    IReminderService,
    ISupplementaryAgreementGenerationService,
    ISystemConfigService,
)

from .automation_protocols import (
    IAccountSelectionStrategy,
    IAutoLoginService,
    IAutomationService,
    IAutoTokenAcquisitionService,
    IBaoquanTokenService,
    IBrowserService,
    ICaptchaService,
    ICourtPleadingSignalsService,
    ICourtSMSService,
    ICourtTokenStoreService,
    IMonitorService,
    IOcrService,
    IPerformanceMonitorService,
    IPreservationQuoteService,
    ISecurityService,
    ITokenService,
    IValidatorService,
)

# 导入所有协议接口以支持类型提示
from .case_protocols import (
    ICaseChatService,
    ICaseFilingNumberService,
    ICaseLogService,
    ICaseNumberService,
    ICaseSearchService,
    ICaseService,
    ILitigationFeeCalculatorService,
)
from .contract_protocols import (
    IContractAssignmentQueryService,
    IContractFolderBindingService,
    IContractPaymentService,
    IContractService,
)
from .document_protocols import (
    IAutoNamerService,
    ICourtDocumentRecognitionService,
    ICourtDocumentService,
    IDocumentProcessingService,
)
from .organization_protocols import (
    IClientService,
    ILawFirmService,
    ILawyerService,
    IOrganizationService,
    IPermissionService,
)


class ServiceLocator:
    """
    服务定位器
    用于获取跨模块服务实例,实现依赖注入
    """

    _services: dict[str, Any] = {}

    @classmethod
    def register(cls, name: str, service: Any) -> None:
        """注册服务"""
        cls._services[name] = service

    @classmethod
    def get(cls, name: str) -> Any | None:
        """获取服务"""
        return cls._services.get(name)

    @classmethod
    def clear(cls, name: str | None = None) -> None:
        """
        清除服务(用于测试)

        Args:
            name: 服务名称,如果为 None 则清除所有服务
        """
        if name is not None:
            cls._services.pop(name, None)
        else:
            cls._services.clear()

    @classmethod
    def get_lawyer_service(cls) -> ILawyerService:
        """获取律师服务"""
        service = cls.get("lawyer_service")
        if service is None:
            # 延迟导入,避免循环依赖
            from apps.organization.services import LawyerServiceAdapter

            service = LawyerServiceAdapter()  # type: ignore
            cls.register("lawyer_service", service)
        return service

    @classmethod
    def get_client_service(cls) -> IClientService:
        """获取客户服务"""
        service = cls.get("client_service")
        if service is None:
            from apps.client.services import ClientServiceAdapter

            service = ClientServiceAdapter()  # type: ignore
            cls.register("client_service", service)
        return service

    @classmethod
    def get_contract_service(cls) -> IContractService:
        """获取合同服务"""
        service = cls.get("contract_service")
        if service is None:
            from apps.contracts.services import ContractServiceAdapter

            service = ContractServiceAdapter()
            cls.register("contract_service", service)
        return service  # type: ignore[return-value]

    @classmethod
    def get_case_service(cls) -> ICaseService:
        """
        获取案件服务

        Returns:
            ICaseService 实例
        """
        service = cls.get("case_service")
        if service is None:
            # 延迟导入,避免循环依赖
            from apps.cases.services import CaseServiceAdapter

            service = CaseServiceAdapter()
            cls.register("case_service", service)
        return service  # type: ignore[return-value]

    @classmethod
    def get_lawfirm_service(cls) -> ILawFirmService:
        """
        获取律所服务

        Returns:
            ILawFirmService 实例
        """
        service = cls.get("lawfirm_service")
        if service is None:
            # 延迟导入,避免循环依赖
            from apps.organization.services import LawFirmServiceAdapter

            service = LawFirmServiceAdapter()
            cls.register("lawfirm_service", service)
        return service

    @classmethod
    def get_auto_token_acquisition_service(cls) -> IAutoTokenAcquisitionService:
        """
        获取自动Token获取服务

        Returns:
            IAutoTokenAcquisitionService 实例
        """
        service = cls.get("auto_token_acquisition_service")
        if service is None:
            # 延迟导入,避免循环依赖
            from apps.automation.services.token.auto_token_acquisition_service import AutoTokenAcquisitionService

            service = AutoTokenAcquisitionService()
            cls.register("auto_token_acquisition_service", service)
        return service

    @classmethod
    def get_account_selection_strategy(cls) -> IAccountSelectionStrategy:
        """
        获取账号选择策略服务

        Returns:
            IAccountSelectionStrategy 实例
        """
        service = cls.get("account_selection_strategy")
        if service is None:
            # 延迟导入,避免循环依赖
            from apps.automation.services.token.account_selection_strategy import AccountSelectionStrategy

            service = AccountSelectionStrategy()
            cls.register("account_selection_strategy", service)
        return service

    @classmethod
    def get_auto_login_service(cls) -> IAutoLoginService:
        """
        获取自动登录服务

        Returns:
            IAutoLoginService 实例
        """
        service = cls.get("auto_login_service")
        if service is None:
            # 延迟导入,避免循环依赖
            from apps.automation.services.token.auto_login_service import AutoLoginService

            service = AutoLoginService()
            cls.register("auto_login_service", service)
        return service

    @classmethod
    def get_token_service(cls) -> ITokenService:
        """
        获取 Token 服务

        Returns:
            ITokenService 实例
        """
        service = cls.get("token_service")
        if service is None:
            # 延迟导入,避免循环依赖
            from apps.automation.services.scraper.core.token_service import TokenServiceAdapter

            service = TokenServiceAdapter()
            cls.register("token_service", service)
        return service

    @classmethod
    def get_browser_service(cls) -> IBrowserService:
        """
        获取浏览器服务

        Returns:
            IBrowserService 实例
        """
        service = cls.get("browser_service")
        if service is None:
            # 延迟导入,避免循环依赖
            from apps.automation.services.scraper.core.browser_service import BrowserServiceAdapter

            service = BrowserServiceAdapter()
            cls.register("browser_service", service)
        return service

    @classmethod
    def get_captcha_service(cls) -> ICaptchaService:
        """
        获取验证码服务

        Returns:
            ICaptchaService 实例
        """
        service = cls.get("captcha_service")
        if service is None:
            # 延迟导入,避免循环依赖
            from apps.automation.services.captcha.captcha_recognition_service import CaptchaServiceAdapter

            service = CaptchaServiceAdapter()
            cls.register("captcha_service", service)
        return service

    @classmethod
    def get_court_document_service(cls) -> ICourtDocumentService:
        """
        获取法院文书服务

        Returns:
            ICourtDocumentService 实例
        """
        service = cls.get("court_document_service")
        if service is None:
            # 延迟导入,避免循环依赖
            from apps.automation.services.scraper.court_document_service import CourtDocumentServiceAdapter

            service = CourtDocumentServiceAdapter()
            cls.register("court_document_service", service)
        return service

    @classmethod
    def get_monitor_service(cls) -> IMonitorService:
        """
        获取监控服务

        Returns:
            IMonitorService 实例
        """
        service = cls.get("monitor_service")
        if service is None:
            # 延迟导入,避免循环依赖
            from apps.automation.services.scraper.core.monitor_service import MonitorServiceAdapter

            service = MonitorServiceAdapter()
            cls.register("monitor_service", service)
        return service

    @classmethod
    def get_security_service(cls) -> ISecurityService:
        """
        获取安全服务

        Returns:
            ISecurityService 实例
        """
        service = cls.get("security_service")
        if service is None:
            # 延迟导入,避免循环依赖
            from apps.automation.services.scraper.core.security_service import SecurityServiceAdapter

            service = SecurityServiceAdapter()
            cls.register("security_service", service)
        return service

    @classmethod
    def get_validator_service(cls) -> IValidatorService:
        """
        获取验证服务

        Returns:
            IValidatorService 实例
        """
        service = cls.get("validator_service")
        if service is None:
            # 延迟导入,避免循环依赖
            from apps.automation.services.scraper.core.validator_service import ValidatorServiceAdapter

            service = ValidatorServiceAdapter()
            cls.register("validator_service", service)
        return service

    @classmethod
    def get_contract_payment_service(cls) -> IContractPaymentService:
        """
        获取合同收款服务

        Returns:
            IContractPaymentService 实例
        """
        service = cls.get("contract_payment_service")
        if service is None:
            # 延迟导入,避免循环依赖
            from apps.contracts.services.contract_payment_service import ContractPaymentService

            service = ContractPaymentService()
            cls.register("contract_payment_service", service)
        return service

    @classmethod
    def get_caselog_service(cls) -> ICaseLogService:
        """
        获取案件日志服务

        Returns:
            ICaseLogService 实例
        """
        service = cls.get("caselog_service")
        if service is None:
            # 延迟导入,避免循环依赖
            from apps.cases.services.caselog_service import CaseLogService

            service = CaseLogService()
            cls.register("caselog_service", service)
        return service

    @classmethod
    def get_preservation_quote_service(cls) -> IPreservationQuoteService:
        """
        获取财产保全询价服务

        Returns:
            IPreservationQuoteService 实例
        """
        service = cls.get("preservation_quote_service")
        if service is None:
            # 延迟导入,避免循环依赖
            from apps.automation.services.insurance.preservation_quote_service_adapter import (
                PreservationQuoteServiceAdapter,
            )

            service = PreservationQuoteServiceAdapter()
            cls.register("preservation_quote_service", service)
        return service

    @classmethod
    def get_document_processing_service(cls) -> IDocumentProcessingService:
        """
        获取文档处理服务

        Returns:
            IDocumentProcessingService 实例
        """
        service = cls.get("document_processing_service")
        if service is None:
            # 延迟导入,避免循环依赖
            from apps.automation.services.document.document_processing_service_adapter import (
                DocumentProcessingServiceAdapter,
            )

            service = DocumentProcessingServiceAdapter()
            cls.register("document_processing_service", service)
        return service

    @classmethod
    def get_auto_namer_service(cls) -> IAutoNamerService:
        """
        获取自动命名服务

        Returns:
            IAutoNamerService 实例
        """
        service = cls.get("auto_namer_service")
        if service is None:
            # 延迟导入,避免循环依赖
            from apps.automation.services.ai.auto_namer_service_adapter import AutoNamerServiceAdapter

            service = AutoNamerServiceAdapter()
            cls.register("auto_namer_service", service)
        return service

    @classmethod
    def get_automation_service(cls) -> IAutomationService:
        """
        获取自动化服务

        Returns:
            IAutomationService 实例
        """
        service = cls.get("automation_service")
        if service is None:
            # 延迟导入,避免循环依赖
            from apps.automation.services.automation_service_adapter import AutomationServiceAdapter

            service = AutomationServiceAdapter()
            cls.register("automation_service", service)
        return service

    @classmethod
    def get_performance_monitor_service(cls) -> IPerformanceMonitorService:
        """
        获取性能监控服务

        Returns:
            IPerformanceMonitorService 实例
        """
        service = cls.get("performance_monitor_service")
        if service is None:
            # 延迟导入,避免循环依赖
            from apps.automation.services.token.performance_monitor_service_adapter import (
                PerformanceMonitorServiceAdapter,
            )

            service = PerformanceMonitorServiceAdapter()
            cls.register("performance_monitor_service", service)
        return service

    @classmethod
    def get_court_sms_service(cls) -> ICourtSMSService:
        """
        获取法院短信处理服务

        Returns:
            ICourtSMSService 实例
        """
        service = cls.get("court_sms_service")
        if service is None:
            # 延迟导入,避免循环依赖
            from apps.automation.services.sms.court_sms_service import CourtSMSService

            service = CourtSMSService()
            cls.register("court_sms_service", service)
        return service  # type: ignore[return-value]

    @classmethod
    def get_case_chat_service(cls) -> ICaseChatService:
        """
        获取案件群聊服务

        Returns:
            ICaseChatService 实例
        """
        service = cls.get("case_chat_service")
        if service is None:
            # 延迟导入,避免循环依赖
            from apps.cases.services.case_chat_service import CaseChatService

            service = CaseChatService()
            cls.register("case_chat_service", service)
        return service  # type: ignore[return-value]

    @classmethod
    def get_organization_service(cls) -> IOrganizationService:
        """
        获取组织服务

        Returns:
            IOrganizationService 实例
        """
        service = cls.get("organization_service")
        if service is None:
            # 延迟导入,避免循环依赖
            from apps.organization.services import OrganizationServiceAdapter

            service = OrganizationServiceAdapter()  # type: ignore
            cls.register("organization_service", service)
        return service

    @classmethod
    def get_case_number_service(cls) -> ICaseNumberService:
        """
        获取案号服务

        Returns:
            ICaseNumberService 实例
        """
        service = cls.get("case_number_service")
        if service is None:
            # 延迟导入,避免循环依赖
            from apps.cases.services.case_number_service_adapter import CaseNumberServiceAdapter

            service = CaseNumberServiceAdapter()
            cls.register("case_number_service", service)
        return service

    @classmethod
    def get_court_document_recognition_service(cls) -> ICourtDocumentRecognitionService:
        """
        获取法院文书智能识别服务

        Returns:
            ICourtDocumentRecognitionService 实例
        """
        service = cls.get("court_document_recognition_service")
        if service is None:
            # 延迟导入,避免循环依赖
            from apps.automation.services.court_document_recognition.adapter import (
                CourtDocumentRecognitionServiceAdapter,
            )

            service = CourtDocumentRecognitionServiceAdapter()
            cls.register("court_document_recognition_service", service)
        return service

    # ============================================================
    # 跨模块依赖所需的通用服务
    # ============================================================

    @classmethod
    def get_system_config_service(cls) -> ISystemConfigService:
        """获取系统配置服务"""
        service = cls.get("system_config_service")
        if service is None:
            from apps.core.services.system_config_service import SystemConfigService

            service = SystemConfigService()
            cls.register("system_config_service", service)
        return service

    @classmethod
    def get_cause_court_query_service(cls) -> ICauseCourtQueryService:
        """获取案由法院查询服务"""
        service = cls.get("cause_court_query_service")
        if service is None:
            from apps.core.services.cause_court_query_service import CauseCourtQueryService

            service = CauseCourtQueryService()
            cls.register("cause_court_query_service", service)
        return service  # type: ignore[return-value]

    @classmethod
    def get_business_config_service(cls) -> IBusinessConfigService:
        """获取业务配置服务"""
        service = cls.get("business_config_service")
        if service is None:
            from apps.core.services.business_config_service import BusinessConfigService

            service = BusinessConfigService()
            cls.register("business_config_service", service)
        return service

    @classmethod
    def get_reminder_service(cls) -> IReminderService:
        """获取提醒服务"""
        service = cls.get("reminder_service")
        if service is None:
            from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter

            service = ReminderServiceAdapter()
            cls.register("reminder_service", service)
        return service

    @classmethod
    def get_llm_service(cls) -> ILLMService:
        """获取 LLM 服务"""
        service = cls.get("llm_service")
        if service is None:
            from apps.core.llm.service import LLMService

            service = LLMService()
            cls.register("llm_service", service)
        return service  # type: ignore[return-value]

    @classmethod
    def get_prompt_version_service(cls) -> IPromptVersionService:
        """获取 Prompt 版本服务"""
        service = cls.get("prompt_version_service")
        if service is None:
            from apps.documents.services.prompt_version_service_adapter import PromptVersionServiceAdapter

            service = PromptVersionServiceAdapter()
            cls.register("prompt_version_service", service)
        return service

    @classmethod
    def get_conversation_history_service(cls) -> IConversationHistoryService:
        """获取对话历史服务"""
        service = cls.get("conversation_history_service")
        if service is None:
            from apps.core.services.conversation_history_service import ConversationHistoryService

            service = ConversationHistoryService()
            cls.register("conversation_history_service", service)
        return service

    @classmethod
    def get_evidence_list_placeholder_service(cls) -> IEvidenceListPlaceholderService:
        """获取证据清单占位符服务"""
        service = cls.get("evidence_list_placeholder_service")
        if service is None:
            from apps.documents.services.evidence_list_placeholder_service import EvidenceListPlaceholderService

            service = EvidenceListPlaceholderService()
            cls.register("evidence_list_placeholder_service", service)
        return service

    @classmethod
    def get_permission_service(cls) -> IPermissionService:
        """获取权限服务"""
        service = cls.get("permission_service")
        if service is None:
            raise RuntimeError("权限服务未注册.请先调用 ServiceLocator.register('permission_service', instance) 注册.")
        return service  # type: ignore[no-any-return]

    # ============================================================
    # 文档相关服务
    # ============================================================

    @classmethod
    def get_document_service(cls) -> IDocumentService:
        """获取文档服务"""
        service = cls.get("document_service")
        if service is None:
            from apps.documents.services.document_service_adapter import DocumentServiceAdapter

            service = DocumentServiceAdapter()
            cls.register("document_service", service)
        return service

    @classmethod
    def get_document_template_binding_service(cls) -> IDocumentTemplateBindingService:
        """获取文档模板绑定服务"""
        service = cls.get("document_template_binding_service")
        if service is None:
            from apps.documents.services.contract_template_binding_service import DocumentTemplateBindingService

            service = DocumentTemplateBindingService()
            cls.register("document_template_binding_service", service)
        return service

    @classmethod
    def get_evidence_query_service(cls) -> IEvidenceQueryService:
        """获取证据查询服务"""
        service = cls.get("evidence_query_service")
        if service is None:
            from apps.documents.services.evidence_query_service import EvidenceQueryService

            service = EvidenceQueryService()
            cls.register("evidence_query_service", service)
        return service

    @classmethod
    def get_evidence_service(cls) -> Any:
        """获取证据服务"""
        service = cls.get("evidence_service")
        if service is None:
            from apps.core.dependencies import (
                build_case_service_with_deps,
                build_client_service,
                build_contract_query_service,
            )
            from apps.documents.services.evidence_service import EvidenceService

            contract_service = build_contract_query_service()
            service = EvidenceService(
                case_service=build_case_service_with_deps(
                    contract_service=contract_service, client_service=build_client_service()
                )
            )
            cls.register("evidence_service", service)
        return service

    @classmethod
    def get_generation_task_service(cls) -> IGenerationTaskService:
        """获取文档生成任务服务"""
        service = cls.get("generation_task_service")
        if service is None:
            from apps.documents.services.generation.generation_task_service import GenerationTaskService

            service = GenerationTaskService()
            cls.register("generation_task_service", service)
        return service  # type: ignore[return-value]

    @classmethod
    def get_contract_generation_service(cls) -> IContractGenerationService:
        """获取合同文书生成服务"""
        service = cls.get("contract_generation_service")
        if service is None:
            from apps.documents.services.generation.contract_generation_service import ContractGenerationService

            service = ContractGenerationService()
            cls.register("contract_generation_service", service)
        return service  # type: ignore[return-value]

    @classmethod
    def get_supplementary_agreement_generation_service(cls) -> ISupplementaryAgreementGenerationService:
        """获取补充协议生成服务"""
        service = cls.get("supplementary_agreement_generation_service")
        if service is None:
            from apps.documents.services.generation.supplementary_agreement_generation_service import (
                SupplementaryAgreementGenerationService,
            )

            service = SupplementaryAgreementGenerationService()
            cls.register("supplementary_agreement_generation_service", service)
        return service  # type: ignore[return-value]

    # ============================================================
    # 案件扩展服务
    # ============================================================

    @classmethod
    def get_case_search_service(cls) -> ICaseSearchService:
        """获取案件搜索服务"""
        service = cls.get("case_search_service")
        if service is None:
            from apps.cases.services.case.case_search_service_adapter import CaseSearchServiceAdapter

            service = CaseSearchServiceAdapter()
            cls.register("case_search_service", service)
        return service

    @classmethod
    def get_case_filing_number_service(cls) -> ICaseFilingNumberService:
        """获取案件归档编号服务"""
        service = cls.get("case_filing_number_service")
        if service is None:
            from apps.cases.services.number.case_filing_number_service_adapter import CaseFilingNumberServiceAdapter

            service = CaseFilingNumberServiceAdapter()
            cls.register("case_filing_number_service", service)
        return service

    @classmethod
    def get_litigation_fee_calculator_service(cls) -> ILitigationFeeCalculatorService:
        """获取诉讼费计算服务"""
        service = cls.get("litigation_fee_calculator_service")
        if service is None:
            from apps.cases.services.data.litigation_fee_calculator_service import LitigationFeeCalculatorService

            service = LitigationFeeCalculatorService()
            cls.register("litigation_fee_calculator_service", service)
        return service

    @classmethod
    def get_case_assignment_service(cls) -> ICaseAssignmentService:
        """获取案件指派服务"""
        service = cls.get("case_assignment_service")
        if service is None:
            from apps.cases.services.party.case_assignment_service import CaseAssignmentService

            service = CaseAssignmentService()
            cls.register("case_assignment_service", service)
        return service  # type: ignore[return-value]

    @classmethod
    def get_case_material_service(cls) -> ICaseMaterialService:
        """获取案件材料服务"""
        service = cls.get("case_material_service")
        if service is None:
            from apps.cases.services.material.case_material_service import CaseMaterialService

            service = CaseMaterialService()
            cls.register("case_material_service", service)
        return service

    # ============================================================
    # 合同扩展服务
    # ============================================================

    @classmethod
    def get_contract_assignment_query_service(cls) -> IContractAssignmentQueryService:
        """获取合同指派查询服务"""
        service = cls.get("contract_assignment_query_service")
        if service is None:
            from apps.contracts.services.assignment.contract_assignment_query_service import (
                ContractAssignmentQueryService,
            )

            service = ContractAssignmentQueryService()
            cls.register("contract_assignment_query_service", service)
        return service

    @classmethod
    def get_contract_folder_binding_service(cls) -> IContractFolderBindingService:
        """获取合同文件夹绑定服务"""
        service = cls.get("contract_folder_binding_service")
        if service is None:
            from apps.contracts.services.folder.folder_binding_service import FolderBindingService

            service = FolderBindingService()
            cls.register("contract_folder_binding_service", service)
        return service  # type: ignore[return-value]

    # ============================================================
    # 自动化扩展服务
    # ============================================================

    @classmethod
    def get_court_token_store_service(cls) -> ICourtTokenStoreService:
        """获取法院 Token 存储服务"""
        service = cls.get("court_token_store_service")
        if service is None:
            from apps.automation.services.token.court_token_store_service import CourtTokenStoreService

            service = CourtTokenStoreService()
            cls.register("court_token_store_service", service)
        return service  # type: ignore[return-value]

    @classmethod
    def get_baoquan_token_service(cls) -> IBaoquanTokenService:
        """获取保全 Token 服务"""
        service = cls.get("baoquan_token_service")
        if service is None:
            from apps.core.services.court_tokens.baoquan_token_service import BaoquanTokenService

            service = BaoquanTokenService()
            cls.register("baoquan_token_service", service)
        return service

    @classmethod
    def get_ocr_service(cls) -> IOcrService:
        """获取 OCR 服务"""
        service = cls.get("ocr_service")
        if service is None:
            from apps.automation.services.ocr.adapter import OCRServiceAdapter

            service = OCRServiceAdapter()
            cls.register("ocr_service", service)
        return service

    @classmethod
    def get_court_pleading_signals_service(cls) -> ICourtPleadingSignalsService:
        """获取法院诉状信号服务"""
        service = cls.get("court_pleading_signals_service")
        if service is None:
            from apps.automation.services.litigation.court_pleading_signals_service_adapter import (
                CourtPleadingSignalsServiceAdapter,
            )

            service = CourtPleadingSignalsServiceAdapter()
            cls.register("court_pleading_signals_service", service)
        return service


# ============================================================
# 事件总线
# 用于模块间的事件通知,实现松耦合
# ============================================================


class EventBus:
    """
    简单的事件总线
    用于模块间的事件发布和订阅
    """

    _handlers: dict[str, list[Callable[..., Any]]] = {}

    @classmethod
    def subscribe(cls, event_type: str, handler: Callable[..., Any]) -> None:
        """订阅事件"""
        if event_type not in cls._handlers:
            cls._handlers[event_type] = []
        cls._handlers[event_type].append(handler)

    @classmethod
    def publish(cls, event_type: str, data: Any | None = None) -> None:
        """发布事件"""
        handlers = cls._handlers.get(event_type, [])
        for handler in handlers:
            try:
                handler(data)
            except Exception as e:
                logger.exception("操作失败")
                logging.getLogger("apps").error(f"Event handler error: {e}")

    @classmethod
    def clear(cls, event_type: str | None = None) -> None:
        """清除事件处理器"""
        if event_type:
            cls._handlers.pop(event_type, None)
        else:
            cls._handlers.clear()


# 预定义事件类型
class Events:
    """事件类型常量"""

    CASE_CREATED = "case.created"
    CASE_UPDATED = "case.updated"
    CASE_DELETED = "case.deleted"

    CONTRACT_CREATED = "contract.created"
    CONTRACT_UPDATED = "contract.updated"

    PAYMENT_CREATED = "payment.created"
    PAYMENT_UPDATED = "payment.updated"

    USER_TEAM_CHANGED = "user.team_changed"
    CASE_ACCESS_GRANTED = "case.access_granted"
    CASE_ACCESS_REVOKED = "case.access_revoked"
