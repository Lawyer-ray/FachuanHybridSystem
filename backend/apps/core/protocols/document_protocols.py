"""
文档相关 Protocol 接口定义

包含:IDocumentService
"""

from typing import Any, Protocol

from apps.core.dto import DocumentTemplateDTO, EvidenceItemDigestDTO, GenerationTaskDTO


class IDocumentService(Protocol):
    """
    文档服务接口

    定义文档模块对外提供的核心方法,供其他模块(如合同模块、案件模块)调用.
    主要用于查询匹配的文书模板和文件夹模板.

    Requirements: 2.1, 5.1, 7.1, 7.2, 8.1, 8.2
    """

    def find_matching_contract_templates(self, case_type: str) -> list[dict[str, Any]]:
        """
        查找匹配的合同文书模板

        根据案件类型查找适用的文书模板,返回模板的基本信息.

        Args:
            case_type: 案件类型(如 'civil', 'criminal', 'administrative')

        Returns:
            模板信息列表,每个元素包含:
            - id: 模板 ID
            - name: 模板名称
            - type_display: 模板类型显示名称(如 "委托代理合同")

        Raises:
            ValidationException: 案件类型无效
        """
        ...

    def find_matching_folder_templates(
        self, template_type: str, case_type: str | None = None
    ) -> list[dict[str, Any]]: ...

    def check_has_matching_templates(self, case_type: str) -> dict[str, bool]: ...

    def get_matched_folder_templates(self, case_type: str) -> str: ...

    def get_matched_folder_templates_with_legal_status(self, case_type: str, legal_statuses: list[str]) -> str: ...

    def get_folder_binding_path(self, case_type: str, subdir_key: str) -> str | None: ...

    def find_matching_case_file_templates(
        self,
        case_type: str,
        case_stage: str,
        applicable_institutions: list[str] | None = None,
    ) -> list[dict[str, Any]]: ...

    def get_template_by_id_internal(self, template_id: int) -> DocumentTemplateDTO | None: ...

    def get_template_by_function_code_internal(
        self, function_code: str, case_type: str | None = None, is_active: bool = True
    ) -> DocumentTemplateDTO | None: ...

    def list_templates_by_function_code_internal(
        self, function_code: str, case_type: str | None = None, is_active: bool = True
    ) -> list[DocumentTemplateDTO]: ...

    def list_case_templates_internal(self, is_active: bool = True) -> list[DocumentTemplateDTO]: ...

    def get_templates_by_ids_internal(self, template_ids: list[int]) -> list[DocumentTemplateDTO]: ...


class IDocumentTemplateBindingService(Protocol):
    def get_contract_subdir_path_internal(self, case_type: str, contract_sub_type: str) -> str | None: ...


class IEvidenceQueryService(Protocol):
    def list_evidence_items_for_digest_internal(
        self,
        evidence_list_ids: list[int],
        evidence_item_ids: list[int],
    ) -> list[EvidenceItemDigestDTO]: ...

    def list_evidence_item_ids_with_files_internal(
        self, evidence_item_ids: list[int]
    ) -> list[EvidenceItemDigestDTO]: ...

    def list_evidence_items_for_case_internal(self, case_id: int) -> list[EvidenceItemDigestDTO]: ...


class IGenerationTaskService(Protocol):
    def create_ai_task_internal(
        self,
        *,
        case_id: int,
        litigation_session_id: int,
        document_type: str,
        template_id: int | None,
        created_by_id: int | None,
        metadata: dict[str, Any],
    ) -> GenerationTaskDTO: ...

    def mark_task_completed_internal(
        self,
        *,
        task_id: int,
        result_file: str,
        metadata_updates: dict[str, Any],
    ) -> GenerationTaskDTO: ...

    def mark_task_failed_internal(
        self,
        *,
        task_id: int,
        error_message: str,
    ) -> GenerationTaskDTO: ...

    def get_task_internal(self, task_id: int) -> GenerationTaskDTO | None: ...


# 说明：模板匹配类方法（find_matching_folder_templates / get_matched_* / get_template*_internal 等）
# 由 IDocumentService（DocumentServiceAdapter）提供，不在本协议声明——GenerationTaskService 仅实现
# 生成任务的创建与状态流转，此前在本协议声明的模板方法从未有对应实现（cast 压制）。


class IContractGenerationService(Protocol):
    def generate_contract_document(self, contract_id: int) -> tuple[bytes, str, str | None]: ...


class ISupplementaryAgreementGenerationService(Protocol):
    def generate_supplementary_agreement(
        self, contract_id: int, agreement_id: int
    ) -> tuple[bytes, str, str | None]: ...
