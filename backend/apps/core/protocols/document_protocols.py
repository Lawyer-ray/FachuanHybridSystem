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

    def find_matching_folder_templates(self, template_type: str, case_type: str | None = None) -> list[dict[str, Any]]:
        """
        查找匹配的文件夹模板

        根据模板类型和案件类型查找适用的文件夹模板.

        Args:
            template_type: 模板类型('contract' 或 'case')
            case_type: 案件类型(可选,如 'civil', 'criminal')

        Returns:
            模板信息列表,每个元素包含:
            - id: 模板 ID
            - name: 模板名称

        Raises:
            ValidationException: 模板类型无效
        """
        ...

    def check_has_matching_templates(self, case_type: str) -> dict[str, bool]:
        """
        检查是否有匹配的模板

        检查指定案件类型是否同时有文件夹模板和文书模板.

        Args:
            case_type: 案件类型(如 'civil', 'criminal', 'administrative')

        Returns:
            包含检查结果的字典:
            - has_folder: 是否有匹配的文件夹模板
            - has_document: 是否有匹配的文书模板

        Raises:
            ValidationException: 案件类型无效
        """
        ...

    def get_matched_document_templates(self, case_type: str) -> str:
        """
        获取匹配的文书模板名称

        根据案件类型查找适用的文书模板,返回模板名称字符串.

        Args:
            case_type: 案件类型(如 'civil', 'criminal', 'administrative')

        Returns:
            模板名称字符串,多个模板用"、"分隔.
            如果没有匹配返回 "无匹配模板"

        Requirements: 5.1
        """
        ...

    def get_matched_folder_templates(self, case_type: str) -> str:
        """
        获取匹配的文件夹模板名称

        根据案件类型查找适用的文件夹模板,返回模板名称字符串.

        Args:
            case_type: 案件类型(如 'civil', 'criminal', 'administrative')

        Returns:
            模板名称字符串,多个模板用"、"分隔.
            如果没有匹配返回 "无匹配模板"

        Requirements: 5.2
        """
        ...

    def get_matched_folder_templates_with_legal_status(self, case_type: str, legal_statuses: list[str]) -> str:
        """
        获取匹配的文件夹模板名称(支持诉讼地位匹配)

        根据案件类型和诉讼地位查找适用的文件夹模板,返回模板名称字符串.

        Args:
            case_type: 案件类型(如 'civil', 'criminal', 'administrative')
            legal_statuses: 案件的诉讼地位列表(我方当事人的诉讼地位)

        Returns:
            模板名称字符串,多个模板用"、"分隔.
            如果没有匹配返回 "无匹配模板"

        Requirements: 5.2
        """
        ...

    def get_folder_binding_path(self, case_type: str, subdir_key: str) -> str | None:
        """
        获取文书模板绑定配置的文件夹路径

        根据案件类型和子目录键名查找配置的文件夹路径.

        Args:
            case_type: 案件类型(如 'civil', 'criminal', 'administrative')
            subdir_key: 子目录键名(如 'case_documents')

        Returns:
            配置的子目录路径,如 "1-律师资料/2-案件文书"
            如果没有配置则返回 None

        Requirements: 5.4
        """
        ...

    def list_case_templates_internal(self, is_active: bool = True) -> list["DocumentTemplateDTO"]:
        """
        内部方法:获取案件类型的所有模板列表

        Args:
            is_active: 是否只查询活跃模板

        Returns:
            DocumentTemplateDTO 列表
        """
        ...

    def get_templates_by_ids_internal(self, template_ids: list[int]) -> list["DocumentTemplateDTO"]:
        """
        内部方法:批量根据 ID 获取文档模板

        Args:
            template_ids: 模板 ID 列表

        Returns:
            DocumentTemplateDTO 列表(不存在的 ID 会被忽略)
        """
        ...

    def get_template_by_id_internal(self, template_id: int) -> DocumentTemplateDTO | None:
        """
        内部方法:根据 ID 获取文档模板

        Args:
            template_id: 模板 ID

        Returns:
            DocumentTemplateDTO,不存在返回 None

        Requirements: 7.1, 4.4
        """
        ...

    def get_template_by_function_code_internal(
        self, function_code: str, case_type: str | None = None, is_active: bool = True
    ) -> DocumentTemplateDTO | None:
        """
        内部方法:根据功能代码获取文档模板

        Args:
            function_code: 功能代码
            case_type: 案件类型(可选)
            is_active: 是否只查询活跃模板

        Returns:
            DocumentTemplateDTO,不存在返回 None

        Requirements: 7.1, 4.4
        """
        ...

    def list_templates_by_function_code_internal(
        self, function_code: str, case_type: str | None = None, is_active: bool = True
    ) -> list[DocumentTemplateDTO]:
        """
        内部方法:根据功能代码获取模板列表

        Args:
            function_code: 功能代码
            case_type: 案件类型(可选)
            is_active: 是否只查询活跃模板

        Returns:
            DocumentTemplateDTO 列表

        Requirements: 7.1, 4.4
        """
        ...

    def get_templates_by_case_type_internal(self, case_type: str, is_active: bool = True) -> list[DocumentTemplateDTO]:
        """
        内部方法:根据案件类型获取模板列表

        Args:
            case_type: 案件类型
            is_active: 是否只查询活跃模板

        Returns:
            DocumentTemplateDTO 列表
        """
        ...


class IContractGenerationService(Protocol):
    def generate_contract_document(self, contract_id: int) -> tuple[bytes, str, str | None]: ...


class ISupplementaryAgreementGenerationService(Protocol):
    def generate_supplementary_agreement(
        self, contract_id: int, agreement_id: int
    ) -> tuple[bytes, str, str | None]: ...
