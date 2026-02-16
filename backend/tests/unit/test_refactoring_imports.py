"""
验证重构后的导入路径是否正常工作
"""

import pytest


@pytest.mark.django_db
class TestRefactoringImports:
    """测试重构后的导入路径"""

    def test_cases_models_imports(self):
        """测试 Cases 模块模型导入"""
        from apps.cases.models import (
            BindingSource,
            Case,
            CaseAccessGrant,
            CaseAssignment,
            CaseChat,
            CaseFolderBinding,
            CaseLog,
            CaseLogAttachment,
            CaseLogVersion,
            CaseMaterial,
            CaseMaterialCategory,
            CaseMaterialGroupOrder,
            CaseMaterialSide,
            CaseMaterialType,
            CaseNumber,
            CaseParty,
            CaseTemplateBinding,
            ChatAuditLog,
            SupervisingAuthority,
        )

        # 验证导入成功
        assert Case is not None
        assert CaseNumber is not None
        assert CaseParty is not None
        assert CaseLog is not None
        assert CaseMaterial is not None
        assert CaseTemplateBinding is not None

    def test_cases_services_imports(self):
        """测试 Cases 模块服务导入"""
        from apps.cases.services import (
            CaseAccessService,
            CaseAdminService,
            CaseAssignmentService,
            CaseChatService,
            CaseLogService,
            CaseMaterialService,
            CaseNumberService,
            CasePartyService,
            CaseService,
            CaseTemplateBindingService,
            CauseCourtDataService,
        )

        # 验证导入成功
        assert CaseService is not None
        assert CaseAdminService is not None
        assert CasePartyService is not None
        assert CaseLogService is not None

    def test_contracts_models_imports(self):
        """测试 Contracts 模块模型导入"""
        from apps.contracts.models import (
            Contract,
            ContractAssignment,
            ContractFinanceLog,
            ContractFolderBinding,
            ContractParty,
            ContractPayment,
            FeeMode,
            InvoiceStatus,
            LogLevel,
            PartyRole,
            SupplementaryAgreement,
            SupplementaryAgreementParty,
        )

        # 验证导入成功
        assert Contract is not None
        assert FeeMode is not None
        assert ContractParty is not None
        assert ContractPayment is not None
        assert SupplementaryAgreement is not None

    def test_client_models_imports(self):
        """测试 Client 模块模型导入"""
        from apps.client.models import (
            Client,
            ClientIdentityDoc,
            PropertyClue,
            PropertyClueAttachment,
            client_identity_doc_upload_path,
        )

        # 验证导入成功
        assert Client is not None
        assert ClientIdentityDoc is not None
        assert client_identity_doc_upload_path is not None
        assert PropertyClue is not None

    def test_organization_models_imports(self):
        """测试 Organization 模块模型导入"""
        from apps.organization.models import (
            AccountCredential,
            KeepOriginalNameStorage,
            LawFirm,
            Lawyer,
            Team,
            TeamType,
            lawyer_license_upload_path,
        )

        # 验证导入成功
        assert KeepOriginalNameStorage is not None
        assert LawFirm is not None
        assert Team is not None
        assert TeamType is not None
        assert Lawyer is not None
        assert AccountCredential is not None

    def test_core_infrastructure_imports(self):
        """测试 Core 模块 infrastructure 导入"""
        from apps.core.infrastructure import (
            CacheKeys,
            CacheTimeout,
            HealthChecker,
            PerformanceMonitor,
            RateLimiter,
            ResourceMonitor,
        )

        # 验证导入成功
        assert CacheKeys is not None
        assert CacheTimeout is not None
        assert HealthChecker is not None
        assert PerformanceMonitor is not None
        assert ResourceMonitor is not None
        assert RateLimiter is not None

    def test_core_legacy_imports_still_work(self):
        """测试 Core 模块旧导入路径仍然有效（向后兼容）"""
        import warnings

        # 捕获 deprecation warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")

            from apps.core.cache import CacheKeys as CacheKeysLegacy
            from apps.core.health import HealthChecker as HealthCheckerLegacy
            from apps.core.monitoring import PerformanceMonitor as PerformanceMonitorLegacy
            from apps.core.resource_monitor import ResourceMonitor as ResourceMonitorLegacy
            from apps.core.throttling import RateLimiter as RateLimiterLegacy

            # 验证导入成功
            assert CacheKeysLegacy is not None
            assert HealthCheckerLegacy is not None
            assert PerformanceMonitorLegacy is not None
            assert ResourceMonitorLegacy is not None
            assert RateLimiterLegacy is not None

            # 验证产生了 deprecation warnings
            assert len(w) >= 5
            for warning in w:
                assert issubclass(warning.category, DeprecationWarning)
