"""
补充协议生成服务

负责查找补充协议模板、构建上下文、替换关键词、生成补充协议文件.

Requirements: 2.1, 2.2, 2.3, 8.1, 8.2, 8.3, 8.4, 8.5, 9.4
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from apps.core.interfaces import IContractService
from apps.core.path import Path

if TYPE_CHECKING:
    from apps.core.interfaces import IContractFolderBindingService
    from apps.documents.models import DocumentTemplate
logger = logging.getLogger(__name__)


class SupplementaryAgreementGenerationService:
    """
    补充协议生成服务

    负责查找补充协议模板、构建上下文、替换关键词、生成文件.
    """

    def __init__(
        self,
        contract_service: IContractService | None = None,
        folder_binding_service: "IContractFolderBindingService" | None = None,
    ) -> None:
        """
        初始化服务

        Args:
            contract_service: 合同服务接口(可选,用于依赖注入)
        """
        self._contract_service = contract_service
        self._folder_binding_service = folder_binding_service
        self._last_saved_path: str | None = None

    @property
    def contract_service(self) -> IContractService:
        """延迟加载合同服务"""
        if self._contract_service is None:
            from apps.documents.services.infrastructure.wiring import get_contract_service

            self._contract_service = get_contract_service()
        return self._contract_service

    @property
    def folder_binding_service(self) -> "IContractFolderBindingService" | None:
        return self._folder_binding_service

    def generate_supplementary_agreement(
        self, contract_id: int, agreement_id: int
    ) -> tuple[bytes | None, str | None, str | None]:
        """
        生成补充协议文档

        Args:
            contract_id: 合同 ID
            agreement_id: 补充协议 ID

        Returns:
            Tuple[文件内容, 文件名, 错误信息]
            - 成功: (bytes, filename, None)
            - 失败: (None, None, error_message)
        """
        contract_data = self.contract_service.get_contract_with_details_internal(contract_id)
        if not contract_data:
            return (None, None, "合同不存在")
        contract = self.contract_service.get_contract_model_internal(contract_id)
        if not contract:
            return (None, None, "合同不存在")
        agreement = self.contract_service.get_supplementary_agreement_model_internal(contract_id, agreement_id)
        if not agreement:
            return (None, None, "补充协议不存在")
        from .pipeline import TemplateMatcher

        template = TemplateMatcher().match_supplementary_agreement_template(contract_data.get("case_type") or "")
        if not template:
            return (None, None, "请先添加补充协议模板")
        file_location = template.get_file_location()
        if not file_location or not Path(file_location).exists():
            return (None, None, "模板文件不存在")
        context = self.build_context(contract, agreement)
        try:
            from .pipeline import DocxRenderer

            content = DocxRenderer().render(file_location, context)
        except Exception as e:
            logger.exception("渲染补充协议模板失败")
            return (None, None, f"生成补充协议失败: {e!s}")
        filename = self.generate_filename(contract, agreement, contract_id)
        self._last_saved_path = self._save_to_bound_folder_if_exists(
            contract_id, content, filename, "supplementary_agreements"
        )
        return (content, filename, None)

    def generate_supplementary_agreement_result(
        self, contract_id: int, agreement_id: int
    ) -> tuple[bytes | None, str | None, str | None, str | None]:
        content, filename, error = self.generate_supplementary_agreement(contract_id, agreement_id)
        return (content, filename, self._last_saved_path, error)

    def find_supplementary_agreement_template(self, case_type: str) -> "DocumentTemplate" | None:
        """
        查找补充协议模板

        Args:
            case_type: 合同类型

        Returns:
            匹配的 DocumentTemplate 或 None
        """
        from .pipeline import TemplateMatcher

        return cast("DocumentTemplate" | None, TemplateMatcher().match_supplementary_agreement_template(case_type))

    def build_context(self, contract: Any, agreement: Any) -> dict[str, Any]:
        """
        构建替换词上下文

        Args:
            contract: Contract 实例
            agreement: SupplementaryAgreement 实例

        Returns:
            包含所有替换词的字典
        """
        from .pipeline import PipelineContextBuilder

        return PipelineContextBuilder().build_supplementary_agreement_context(
            contract=contract,
            supplementary_agreement=agreement,
            agreement_principals=self._get_agreement_principals(agreement),
            contract_principals=self._get_contract_principals(contract),
            agreement_opposing=self._get_agreement_opposing(agreement),
        )

    def generate_filename(self, contract: Any, agreement: Any, contract_id: int | None = None) -> str:
        """
        生成输出文件名

        格式:补充协议name(合同name)V1_日期.docx
        例如:补充协议一(王小三、大小武案件)V1_20260102.docx

        如果文件已存在,自动递增版本号(V1 -> V2 -> V3)

        Args:
            contract: Contract 实例
            agreement: SupplementaryAgreement 实例
            contract_id: 合同 ID (用于检查绑定文件夹中的已有文件)

        Returns:
            格式化的文件名
        """
        from .pipeline.naming import supplementary_agreement_docx_filename

        agreement_name = agreement.name or "补充协议"
        contract_name = contract.name or "未命名合同"
        
        # 确定版本号
        version = self._get_next_version(contract_id, agreement_name, contract_name, "supplementary_agreements")
        
        filename = supplementary_agreement_docx_filename(
            agreement_name=agreement_name, contract_name=contract_name, version=version
        )
        logger.info(
            "生成补充协议文件名",
            extra={"agreement": agreement_name, "contract": contract_name, "version": version, "doc_filename": filename},
        )
        return filename

    def _get_next_version(
        self, contract_id: int | None, agreement_name: str, contract_name: str, subdir_key: str
    ) -> str:
        """
        获取下一个可用的版本号

        检查绑定文件夹中已存在的文件,返回下一个版本号

        Args:
            contract_id: 合同 ID
            agreement_name: 补充协议名称
            contract_name: 合同名称
            subdir_key: 子目录键名

        Returns:
            版本号字符串 (如 "V1", "V2", "V3")
        """
        import re
        from datetime import date

        if not contract_id or not self.folder_binding_service:
            return "V1"

        try:
            # 获取绑定信息
            binding = self.folder_binding_service.get_binding(owner_id=contract_id)
            if not binding or not binding.folder_path:
                return "V1"

            # 构建子目录路径
            subdir_path = self.folder_binding_service._resolve_subdir_path(
                owner_type=binding.contract.case_type if hasattr(binding, "contract") else "",
                subdir_key=subdir_key,
            )
            if not subdir_path:
                return "V1"

            folder_path = Path(binding.folder_path) / subdir_path
            if not folder_path.exists():
                return "V1"

            # 构建文件名模式（不包含版本号和日期）
            today_str = date.today().strftime("%Y%m%d")
            # 匹配格式: 补充协议名称(合同名称)V数字_日期.docx
            pattern = re.compile(
                rf"^{re.escape(agreement_name)}\({re.escape(contract_name)}\)V(\d+)_{today_str}\.docx$"
            )

            # 查找已存在的版本号
            max_version = 0
            for file_path in folder_path.iterdir():
                if file_path.is_file():
                    match = pattern.match(file_path.name)
                    if match:
                        version_num = int(match.group(1))
                        max_version = max(max_version, version_num)

            return f"V{max_version + 1}"

        except Exception as e:
            logger.warning("获取版本号失败,使用默认版本 V1: %s", e)
            return "V1"

    def _get_agreement_principals(self, agreement: Any) -> Any:
        """
        获取补充协议中的委托人列表

        Args: agreement: SupplementaryAgreement 实例

        Returns:
            委托人 Client 实例列表
        """
        return [party.client for party in agreement.parties.filter(role="PRINCIPAL")]

    def _get_contract_principals(self, contract: Any) -> Any:
        """
        获取原合同中的委托人列表

        Args: contract: Contract 实例

        Returns:
            委托人 Client 实例列表
        """
        return [party.client for party in contract.contract_parties.filter(role="PRINCIPAL")]

    def _get_agreement_opposing(self, agreement: Any) -> Any:
        """
        获取补充协议中的对方当事人列表

        Args: agreement: SupplementaryAgreement 实例

        Returns:
            对方当事人 Client 实例列表
        """
        return [party.client for party in agreement.parties.filter(role="OPPOSING")]

    def _save_to_bound_folder_if_exists(
        self, contract_id: int, file_content: bytes, file_name: str, subdir_key: str
    ) -> str | None:
        """
        如果合同有绑定文件夹,将文件保存到绑定文件夹

        Args:
            contract_id: 合同 ID
            file_content: 文件内容
            file_name: 文件名
            subdir_key: 子目录键名
        """
        if self.folder_binding_service is None:
            return None
        try:
            saved_path = self.folder_binding_service.save_file_to_bound_folder(
                owner_id=contract_id, file_content=file_content, file_name=file_name, subdir_key=subdir_key
            )
            if saved_path:
                logger.info(
                    "文件已保存到绑定文件夹: %s", saved_path,
                    extra={"contract_id": contract_id, "file_name": file_name, "saved_path": saved_path},
                )
        except Exception as e:
            logger.warning(
                "保存到绑定文件夹失败: %s", e,
                extra={"contract_id": contract_id, "file_name": file_name, "error": str(e)},
            )
            return None
        return saved_path
