"""Business logic services."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from django.core.files.uploadedfile import UploadedFile
from django.db.models import QuerySet

from apps.cases.models import CaseLog, CaseLogAttachment, CaseLogVersion
from apps.cases.services.case.case_access_policy import CaseAccessPolicy
from apps.cases.utils import CASE_LOG_ALLOWED_EXTENSIONS, CASE_LOG_MAX_FILE_SIZE
from apps.core.interfaces import ICaseService

from .case_log_attachment_service import CaseLogAttachmentService
from .case_log_mutation_service import CaseLogMutationService
from .case_log_query_repo import CaseLogQueryRepo
from .case_log_query_service import CaseLogQueryService
from .case_log_version_service import CaseLogVersionService
from .wiring import get_case_service


class CaseLogService:
    """
    案件日志服务

    职责:
    - 日志的 CRUD 操作
    - 权限检查
    - 附件管理
    - 版本历史管理
    """

    def __init__(
        self,
        case_service: ICaseService | None = None,
        query_repo: CaseLogQueryRepo | None = None,
        access_policy: CaseAccessPolicy | None = None,
        query_service: CaseLogQueryService | None = None,
        mutation_service: CaseLogMutationService | None = None,
        attachment_service: CaseLogAttachmentService | None = None,
        version_service: CaseLogVersionService | None = None,
    ) -> None:
        """
        构造函数,支持依赖注入

        Args:
            case_service: 案件服务实例,None 时使用 ServiceLocator 获取
        """
        self._case_service = case_service or get_case_service()
        self._access_policy = access_policy
        self._query_repo = query_repo
        self._query_service = query_service
        self._mutation_service = mutation_service
        self._attachment_service = attachment_service
        self._version_service = version_service

    @property
    def access_policy(self) -> CaseAccessPolicy:
        if self._access_policy is None:
            self._access_policy = CaseAccessPolicy()
        return self._access_policy

    @property
    def query_repo(self) -> CaseLogQueryRepo:
        if self._query_repo is None:
            self._query_repo = CaseLogQueryRepo()
        return self._query_repo

    @property
    def query_service(self) -> CaseLogQueryService:
        if self._query_service is None:
            self._query_service = CaseLogQueryService(access_policy=self.access_policy, query_repo=self.query_repo)
        return self._query_service

    @property
    def mutation_service(self) -> CaseLogMutationService:
        if self._mutation_service is None:
            self._mutation_service = CaseLogMutationService(query_service=self.query_service)
        return self._mutation_service

    @property
    def attachment_service(self) -> CaseLogAttachmentService:
        if self._attachment_service is None:
            self._attachment_service = CaseLogAttachmentService(query_service=self.query_service)
        return self._attachment_service

    @property
    def version_service(self) -> CaseLogVersionService:
        if self._version_service is None:
            self._version_service = CaseLogVersionService(query_service=self.query_service)
        return self._version_service

    def list_logs(
        self,
        case_id: int | None = None,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> QuerySet[CaseLog, CaseLog]:
        """
        获取日志列表

        Args:
            case_id: 案件 ID(可选,用于过滤)
            user: 当前用户
            org_access: 组织访问策略
            perm_open_access: 是否有开放访问权限

        Returns:
            日志查询集
        """
        return self.query_service.list_logs(
            case_id=case_id, user=user, org_access=org_access, perm_open_access=perm_open_access
        )

    def get_log(
        self,
        log_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> CaseLog:
        """
        获取单个日志

        Args:
            log_id: 日志 ID
            user: 当前用户
            org_access: 组织访问策略
            perm_open_access: 是否有开放访问权限

        Returns:
            日志对象

        Raises:
            NotFoundError: 日志不存在
            PermissionDenied: 无权限访问
        """
        return self.query_service.get_log(
            log_id=log_id, user=user, org_access=org_access, perm_open_access=perm_open_access
        )

    def create_log(
        self,
        case_id: int,
        content: str,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
        reminder_type: str | None = None,
        reminder_time: datetime | None = None,
    ) -> CaseLog:
        """
        创建案件日志

        Args:
            case_id: 案件 ID
            content: 日志内容
            user: 当前用户
            reminder_type: 提醒类型
            reminder_time: 提醒时间

        Returns:
            创建的日志对象

        Raises:
            NotFoundError: 案件不存在
        """
        return self.mutation_service.create_log(
            case_id=case_id,
            content=content,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
            reminder_type=reminder_type,
            reminder_time=reminder_time,
        )

    def update_log(
        self,
        log_id: int,
        data: dict[str, Any],
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> CaseLog:
        """
        更新案件日志(保存历史版本)

        Args:
            log_id: 日志 ID
            data: 更新数据字典
            user: 当前用户
            org_access: 组织访问策略
            perm_open_access: 是否有开放访问权限

        Returns:
            更新后的日志对象

        Raises:
            NotFoundError: 日志不存在
            PermissionDenied: 无权限修改
        """
        return self.mutation_service.update_log(
            log_id=log_id, data=data, user=user, org_access=org_access, perm_open_access=perm_open_access
        )

    def delete_log(
        self,
        log_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> dict[str, bool]:
        """
        删除案件日志

        Args:
            log_id: 日志 ID
            user: 当前用户
            org_access: 组织访问策略
            perm_open_access: 是否有开放访问权限

        Returns:
            {"success": True}

        Raises:
            NotFoundError: 日志不存在
            PermissionDenied: 无权限删除
        """
        return self.mutation_service.delete_log(
            log_id=log_id, user=user, org_access=org_access, perm_open_access=perm_open_access
        )

    def upload_attachments(
        self,
        log_id: int,
        files: list[UploadedFile],
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> list[CaseLogAttachment]:
        """
        上传日志附件

        Args:
            log_id: 日志 ID
            files: 上传的文件列表
            user: 当前用户
            org_access: 组织访问策略
            perm_open_access: 是否有开放访问权限

        Returns:
            创建的附件对象列表

        Raises:
            NotFoundError: 日志不存在
            PermissionDenied: 无权限上传
            ValidationException: 文件验证失败
        """
        return self.attachment_service.upload_attachments(
            log_id=log_id, files=files, user=user, org_access=org_access, perm_open_access=perm_open_access
        )

    def get_logs_for_case(
        self,
        case_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> QuerySet[CaseLog, CaseLog]:
        """
        获取案件的所有日志

        Args:
            case_id: 案件 ID
            user: 当前用户
            org_access: 组织访问策略
            perm_open_access: 是否有开放访问权限

        Returns:
            日志查询集
        """
        return self.list_logs(case_id=case_id, user=user, org_access=org_access, perm_open_access=perm_open_access)

    def get_log_versions(
        self,
        log_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> list[CaseLogVersion]:
        """
        获取日志的历史版本

        Args:
            log_id: 日志 ID
            user: 当前用户
            org_access: 组织访问策略
            perm_open_access: 是否有开放访问权限

        Returns:
            历史版本列表

        Raises:
            NotFoundError: 日志不存在
            PermissionDenied: 无权限访问
        """
        return self.version_service.get_log_versions(
            log_id=log_id, user=user, org_access=org_access, perm_open_access=perm_open_access
        )

    def delete_attachment(
        self,
        attachment_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> dict[str, bool]:
        """
        删除日志附件

        Args:
            attachment_id: 附件 ID
            user: 当前用户
            org_access: 组织访问策略
            perm_open_access: 是否有开放访问权限

        Returns:
            {"success": True}

        Raises:
            NotFoundError: 附件不存在
            PermissionDenied: 无权限删除
        """
        return self.attachment_service.delete_attachment(
            attachment_id=attachment_id, user=user, org_access=org_access, perm_open_access=perm_open_access
        )
