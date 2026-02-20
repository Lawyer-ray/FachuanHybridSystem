"""Business logic services."""

from __future__ import annotations
from django.utils.translation import gettext_lazy as _

"""
案件文件夹绑定服务
处理案件与本地文件夹绑定的业务逻辑
"""


import logging
from typing import TYPE_CHECKING, Any, ClassVar, cast

from django.db import transaction

from apps.cases.models import Case, CaseFolderBinding
from apps.cases.services.case.case_access_policy import CaseAccessPolicy
from apps.core.exceptions import NotFoundError
from apps.core.filesystem import (
    FolderBindingCrudService,
    FolderBrowsePolicy,
    FolderFilesystemService,
    FolderPathValidator,
)

if TYPE_CHECKING:
    from apps.core.interfaces import ICaseService, IDocumentService
    from apps.core.security.access_context import AccessContext

logger = logging.getLogger("apps.cases")


class CaseFolderBindingService(FolderBindingCrudService):
    """
    案件文件夹绑定服务

    职责:
    1. 管理案件与文件夹的绑定关系
    2. 验证文件夹路径格式
    3. 处理文件保存到绑定文件夹
    4. 管理子目录结构
    5. 根据文书模板绑定配置确定保存路径

    通过 ServiceLocator 获取跨模块依赖,符合四层架构规范.
    """

    def __init__(
        self,
        document_service: IDocumentService | None = None,
        case_service: ICaseService | None = None,
        filesystem_service: FolderFilesystemService | None = None,
        path_validator: FolderPathValidator | None = None,
        browse_policy: FolderBrowsePolicy | None = None,
    ) -> None:
        """
        构造函数支持依赖注入

        Args:
            document_service: 文档服务实例(可选,用于测试时注入)
        """
        super().__init__(
            filesystem_service=filesystem_service,
            path_validator=path_validator,
            browse_policy=browse_policy,
            roots_setting_name="FOLDER_BROWSE_ROOTS",
            fallback_roots_setting_name="CONTRACT_FOLDER_BROWSE_ROOTS",
        )
        self._document_service = document_service
        self._case_service = case_service
        self._access_policy: CaseAccessPolicy | None = None

    @property
    def document_service(self) -> IDocumentService:
        """
        延迟加载文档服务

        通过 ServiceLocator 获取 IDocumentService 实例,
        避免直接导入 apps.documents 模块.

        Returns:
            IDocumentService 实例
        """
        if self._document_service is None:
            raise RuntimeError("CaseFolderBindingService.document_service 未注入")
        return self._document_service

    @property
    def case_service(self) -> ICaseService:
        if self._case_service is None:
            raise RuntimeError("CaseFolderBindingService.case_service 未注入")
        return self._case_service

    @property
    def access_policy(self) -> CaseAccessPolicy:
        if self._access_policy is None:
            self._access_policy = CaseAccessPolicy()
        return self._access_policy

    def _require_case_access(
        self,
        case_id: int,
        user: Any | None,
        org_access: dict[str, Any] | None,
        perm_open_access: bool,
    ) -> Case:
        case = self._get_case_internal(case_id)
        if not case:
            raise NotFoundError(
                message=_("案件不存在"),
                code="CASE_NOT_FOUND",
                errors={"case_id": f"ID 为 {case_id} 的案件不存在"},
            )

        self.access_policy.ensure_access(
            case_id=case.id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
            case=case,
            message=_("无权限访问此案件"),
        )

        return case

    def _require_case_access_ctx(self, case_id: int, ctx: AccessContext) -> Case:
        return self._require_case_access(
            case_id=case_id,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )

    # 默认子目录配置(仅在没有文书模板绑定配置时使用)
    DEFAULT_SUBDIRS: ClassVar = {
        "case_documents": "案件文书",
        "trial_materials": "庭审材料",
        "judgments": "判决书",
        "execution_documents": "执行文书",
        "other_files": "其他文件",
    }

    binding_model = CaseFolderBinding
    owner_model = Case
    owner_rel_field: str = "case"
    owner_id_field: str = "case_id"
    owner_label: str = "案件"

    def _get_owner(self, *, owner_id: int) -> Case:
        case = self._get_case_internal(owner_id)
        if not case:
            raise NotFoundError(
                message=_("案件不存在"),
                code="CASE_NOT_FOUND",
                errors={"case_id": f"ID 为 {owner_id} 的案件不存在"},
            )
        return case

    def _require_owner(
        self,
        *,
        owner_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
        **kwargs: Any,
    ) -> Case:
        return self._require_case_access(
            case_id=owner_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

    def _resolve_subdir_path(self, *, owner_type: str, subdir_key: str) -> str | None | None:
        try:
            folder_node_path = self.document_service.get_folder_binding_path(owner_type, subdir_key)
            if not folder_node_path:
                return None

            from apps.core.filesystem.folder_node_path import normalize_folder_node_path

            return normalize_folder_node_path(folder_node_path)
        except Exception:
            logger.exception("resolve_subdir_path_failed", extra={"case_type": owner_type, "subdir_key": subdir_key})
            raise

    @transaction.atomic
    def create_binding( # type: ignore
        self,
        case_id: int,
        folder_path: str,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> CaseFolderBinding:
        """
        创建文件夹绑定

        Args:
            case_id: 案件ID
            folder_path: 文件夹路径

        Returns:
            创建的绑定记录

        Raises:
            ValidationException: 路径无效
            NotFoundError: 案件不存在
        """
        return cast(
            CaseFolderBinding,
            super().create_binding(
                owner_id=case_id,
                folder_path=folder_path,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
            ),
        )

    @transaction.atomic
    def create_binding_ctx(self, case_id: int, folder_path: str, ctx: AccessContext) -> CaseFolderBinding:
        return self.create_binding(
            case_id=case_id,
            folder_path=folder_path,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )

    @transaction.atomic
    def update_binding( # type: ignore
        self,
        case_id: int,
        folder_path: str,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> CaseFolderBinding:
        """
        更新文件夹绑定

        Args:
            case_id: 案件ID
            folder_path: 新的文件夹路径

        Returns:
            更新后的绑定记录
        """
        return self.create_binding(
            case_id, folder_path, user=user, org_access=org_access, perm_open_access=perm_open_access
        )

    @transaction.atomic
    def update_binding_ctx(self, case_id: int, folder_path: str, ctx: AccessContext) -> CaseFolderBinding:
        return self.update_binding(
            case_id=case_id,
            folder_path=folder_path,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )

    @transaction.atomic
    def delete_binding( # type: ignore
        self,
        case_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> bool:
        """
        删除文件夹绑定

        Args:
            case_id: 案件ID

        Returns:
            是否删除成功
        """
        return super().delete_binding(
            owner_id=case_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

    @transaction.atomic
    def delete_binding_ctx(self, case_id: int, ctx: AccessContext) -> bool:
        return self.delete_binding(
            case_id=case_id,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )

    def get_binding( # type: ignore
        self,
        case_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> CaseFolderBinding | None:
        """
        获取文件夹绑定

        Args:
            case_id: 案件ID

        Returns:
            绑定记录或 None
        """
        return super().get_binding(
            owner_id=case_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

    def get_binding_ctx(self, case_id: int, ctx: AccessContext) -> CaseFolderBinding | None:
        return self.get_binding(
            case_id=case_id,
            user=ctx.user,
            org_access=ctx.org_access,
            perm_open_access=ctx.perm_open_access,
        )

    def save_file_to_bound_folder( # type: ignore
        self,
        case_id: int,
        file_content: bytes,
        file_name: str,
        subdir_key: str = "case_documents",
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> str | None:
        """
        将文件保存到绑定的文件夹

        优先使用文书模板绑定配置中的路径,如果没有配置则使用默认子目录.

        Args:
            case_id: 案件ID
            file_content: 文件内容
            file_name: 文件名
            subdir_key: 子目录键名 (case_documents, trial_materials, judgments, execution_documents, other_files)

        Returns:
            保存的完整路径,如果未绑定则返回 None
        """
        return super().save_file_to_bound_folder(
            owner_id=case_id,
            file_content=file_content,
            file_name=file_name,
            subdir_key=subdir_key,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

    def extract_zip_to_bound_folder( # type: ignore
        self,
        case_id: int,
        zip_content: bytes,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> str | None:
        """
        将ZIP包解压到绑定的文件夹

        Args:
            case_id: 案件ID
            zip_content: ZIP文件内容

        Returns:
            解压的目标路径,如果未绑定则返回 None
        """
        return super().extract_zip_to_bound_folder(
            owner_id=case_id,
            zip_content=zip_content,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

    def _get_case_internal(self, case_id: int) -> Case | None | None:
        """
        内部方法:获取案件信息(无权限检查)

        Args:
            case_id: 案件ID

        Returns:
            案件对象或 None
        """
        try:
            return Case.objects.get(id=case_id)
        except Case.DoesNotExist:
            return None
