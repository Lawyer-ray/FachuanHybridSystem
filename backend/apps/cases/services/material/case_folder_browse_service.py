"""案件绑定文件夹的浏览与目录管理（前端办案详情页「文件夹视图」）。

通用逻辑（列目录 / 预览 / 新建 / 上传 / 重命名、子路径收敛）全部在
``apps.core.filesystem.bound_folder_browse.BoundFolderBrowseService``，
本类只负责两件案件特有的事：案件行级 ACL 与 ``CaseFolderBinding`` 解析。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from apps.cases.models import CaseFolderBinding
from apps.cases.services.case.case_access_policy import CaseAccessPolicy
from apps.cases.services.case.case_query_service import CaseQueryService
from apps.core.exceptions import NotFoundError
from apps.core.filesystem.bound_folder_browse import BoundFolderBrowseService

logger = logging.getLogger("apps.cases")


class CaseFolderBrowseService(BoundFolderBrowseService):
    """列出案件绑定文件夹的子项 / 预览文件 / 轻量目录管理。"""

    def __init__(self, case_query_service: CaseQueryService | None = None) -> None:
        super().__init__()
        self._case_query_service = case_query_service or CaseQueryService(access_policy=CaseAccessPolicy())

    def _require_access(
        self, *, owner_id: int, user: Any, org_access: dict[str, Any] | None, perm_open_access: bool
    ) -> None:
        # 案件不存在抛 NotFoundError；无权由策略抛 ForbiddenError
        self._case_query_service.get_case(
            case_id=owner_id, user=user, org_access=org_access, perm_open_access=perm_open_access
        )

    def _local_root(self, owner_id: int) -> Path:
        binding = CaseFolderBinding.objects.filter(case_id=owner_id).first()
        if binding is None:
            raise NotFoundError(message="该案件未绑定文件夹", code="FOLDER_BINDING_NOT_FOUND")
        storage_type = getattr(binding, "storage_type", "local")
        if storage_type != "local" and getattr(binding, "storage_account", None) is not None:
            raise NotFoundError(message="云存储绑定暂不支持在线浏览", code="FOLDER_CLOUD_UNSUPPORTED")
        root = Path(str(binding.resolved_folder_path)).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            logger.warning("case_folder_browse_root_missing", extra={"case_id": owner_id, "root": str(root)})
            raise NotFoundError(message="绑定文件夹不可达，请检查路径", code="FOLDER_ROOT_MISSING")
        return root

    def _local_root_with_display(self, owner_id: int) -> tuple[Path, str]:
        root = self._local_root(owner_id)
        binding = CaseFolderBinding.objects.filter(case_id=owner_id).first()
        return root, (binding.folder_path_display if binding and binding.folder_path_display else str(root))
