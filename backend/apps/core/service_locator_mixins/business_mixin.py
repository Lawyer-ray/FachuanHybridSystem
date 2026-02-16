"""Module for business mixin."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .automation_mixin import _ServiceLocatorStub

if TYPE_CHECKING:
    from apps.core.protocols import (
        ICaseAssignmentService,
        ICaseChatService,
        ICaseFilingNumberService,
        ICaseLogService,
        ICaseMaterialService,
        ICaseNumberService,
        ICaseSearchService,
        ICaseService,
        IClientService,
        IContractAssignmentQueryService,
        IContractFolderBindingService,
        IContractPaymentService,
        IContractService,
        ILawFirmService,
        ILawyerService,
        ILitigationFeeCalculatorService,
        IOrganizationService,
        IReminderService,
    )


class BusinessServiceLocatorMixin(_ServiceLocatorStub):
    @classmethod
    def get_lawyer_service(cls) -> ILawyerService:
        from apps.core.dependencies import build_lawyer_service

        return cls.get_or_create("lawyer_service", build_lawyer_service)

    @classmethod
    def get_client_service(cls) -> IClientService:
        from apps.core.dependencies import build_client_service

        return cls.get_or_create("client_service", build_client_service)

    @classmethod
    def get_contract_service(cls) -> IContractService:
        from apps.core.dependencies import build_contract_service_with_deps

        return cls.get_or_create(
            "contract_service",
            lambda: build_contract_service_with_deps(
                case_service=cls.get_case_service(),
                lawyer_service=cls.get_lawyer_service(),
            ),
        )

    @classmethod
    def get_contract_query_service(cls) -> IContractService:
        from apps.core.dependencies import build_contract_query_service

        return cls.get_or_create("contract_query_service", build_contract_query_service)

    @classmethod
    def get_contract_assignment_query_service(cls) -> IContractAssignmentQueryService:
        from apps.core.dependencies import build_contract_assignment_query_service

        return cls.get_or_create("contract_assignment_query_service", build_contract_assignment_query_service)

    @classmethod
    def get_case_service(cls) -> ICaseService:
        from apps.core.dependencies import build_case_service_with_deps

        return cls.get_or_create(
            "case_service",
            lambda: build_case_service_with_deps(
                contract_service=cls.get_contract_query_service(),
                client_service=cls.get_client_service(),
            ),
        )

    @classmethod
    def get_case_assignment_service(cls) -> ICaseAssignmentService:
        from apps.core.dependencies import build_case_assignment_service_with_deps

        return cls.get_or_create(
            "case_assignment_service",
            lambda: build_case_assignment_service_with_deps(
                case_service=cls.get_case_service(),
                contract_assignment_query_service=cls.get_contract_assignment_query_service(),
            ),
        )

    @classmethod
    def get_case_material_service(cls) -> ICaseMaterialService:
        from apps.core.dependencies import build_case_material_service

        return cls.get_or_create("case_material_service", build_case_material_service)

    @classmethod
    def get_lawfirm_service(cls) -> ILawFirmService:
        from apps.core.dependencies import build_lawfirm_service

        return cls.get_or_create("lawfirm_service", build_lawfirm_service)

    @classmethod
    def get_contract_payment_service(cls) -> IContractPaymentService:
        from apps.core.dependencies import build_contract_payment_service

        return cls.get_or_create("contract_payment_service", build_contract_payment_service)

    @classmethod
    def get_contract_folder_binding_service(cls) -> IContractFolderBindingService:
        from apps.core.dependencies import build_contract_folder_binding_service

        return cls.get_or_create("contract_folder_binding_service", build_contract_folder_binding_service)

    @classmethod
    def get_litigation_fee_calculator_service(cls) -> ILitigationFeeCalculatorService:
        from apps.core.dependencies import build_litigation_fee_calculator_service

        return cls.get_or_create("litigation_fee_calculator_service", build_litigation_fee_calculator_service)

    @classmethod
    def get_caselog_service(cls) -> ICaseLogService:
        from apps.core.dependencies import build_case_log_service

        return cls.get_or_create("caselog_service", build_case_log_service)

    @classmethod
    def get_case_filing_number_service(cls) -> ICaseFilingNumberService:
        from apps.core.dependencies import build_case_filing_number_service

        return cls.get_or_create("case_filing_number_service", build_case_filing_number_service)

    @classmethod
    def get_case_chat_service(cls) -> ICaseChatService:
        from apps.core.dependencies import build_case_chat_service

        return cls.get_or_create("case_chat_service", build_case_chat_service)

    @classmethod
    def get_organization_service(cls) -> IOrganizationService:
        from apps.core.dependencies import build_organization_service

        return cls.get_or_create("organization_service", build_organization_service)

    @classmethod
    def get_case_number_service(cls) -> ICaseNumberService:
        from apps.core.dependencies import build_case_number_service

        return cls.get_or_create("case_number_service", build_case_number_service)

    @classmethod
    def get_case_search_service(cls) -> ICaseSearchService:
        from apps.core.dependencies import build_case_search_service

        return cls.get_or_create("case_search_service", build_case_search_service)

    @classmethod
    def get_case_log_service(cls) -> ICaseLogService:
        from apps.core.dependencies import build_case_log_service

        return cls.get_or_create("case_log_service", build_case_log_service)

    @classmethod
    def get_reminder_service(cls) -> IReminderService:
        from apps.core.dependencies import build_reminder_service

        return cls.get_or_create("reminder_service", build_reminder_service)
