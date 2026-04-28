"""Business logic services."""

from __future__ import annotations

from typing import Any, cast

from django.utils.translation import gettext_lazy as _

from apps.core.interfaces import ICaseLogService


class CaseLogServiceAdapter(ICaseLogService):
    """
    案件日志服务适配器

    实现跨模块接口,委托给 CaseLogService 执行.
    """

    def __init__(self, caselog_service: Any | None = None) -> None:
        self._caselog_service = caselog_service

    @property
    def caselog_service(self) -> Any:
        """延迟加载 CaseLogService"""
        if self._caselog_service is None:
            from .caselog_service import CaseLogService

            self._caselog_service = CaseLogService()
        return self._caselog_service

    def list_logs(
        self,
        case_id: int | None = None,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> Any:
        """获取日志列表"""
        return self.caselog_service.list_logs(
            case_id=case_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

    def get_log(
        self,
        log_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> Any:
        """获取单个日志"""
        return self.caselog_service.get_log(
            log_id=log_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

    def create_log(
        self,
        case_id: int,
        content: str,
        user: Any | None = None,
        reminder_type: str | None = None,
        reminder_time: Any | None = None,
    ) -> Any:
        """创建案件日志"""
        return self.caselog_service.create_log(
            case_id=case_id,
            content=content,
            user=user,
            reminder_type=reminder_type,
            reminder_time=reminder_time,
            perm_open_access=True,  # 跨模块调用时使用开放权限
        )

    def update_log(
        self,
        log_id: int,
        data: dict[str, Any],
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> Any:
        """更新案件日志"""
        return self.caselog_service.update_log(
            log_id=log_id,
            data=data,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

    def delete_log(
        self,
        log_id: int,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> dict[str, bool]:
        """删除案件日志"""
        return cast(
            dict[str, bool],
            self.caselog_service.delete_log(
                log_id=log_id,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
            ),
        )

    def upload_attachments(
        self,
        log_id: int,
        files: list[Any],
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> dict[str, int]:
        """上传日志附件"""
        return cast(
            dict[str, int],
            self.caselog_service.upload_attachments(
                log_id=log_id,
                files=files,
                user=user,
                org_access=org_access,
                perm_open_access=perm_open_access,
            ),
        )

    # ============================================================
    # 内部方法(供跨模块调用)
    # ============================================================

    def create_log_internal(
        self,
        case_id: int,
        content: str,
        user_id: int | None = None,
        reminder_type: str | None = None,
        reminder_time: Any | None = None,
    ) -> int:
        """
        内部方法:创建案件日志,返回日志ID

        供跨模块调用,不进行权限检查.

            case_id: 案件 ID
            content: 日志内容
            user_id: 用户 ID(可选)
            reminder_type: 提醒类型(可选)
            reminder_time: 提醒时间(可选)

            创建的日志 ID

            NotFoundError: 案件不存在
        """
        from apps.cases.models import Case, CaseLog
        from apps.core.exceptions import NotFoundError

        try:
            Case.objects.get(id=case_id)
        except Case.DoesNotExist:
            raise NotFoundError(_("案件 %(case_id)s 不存在") % {"case_id": case_id}) from None

        log = CaseLog.objects.create(
            case_id=case_id,
            content=content,
            actor_id=user_id,  # type: ignore[misc]
        )
        return int(log.id)
