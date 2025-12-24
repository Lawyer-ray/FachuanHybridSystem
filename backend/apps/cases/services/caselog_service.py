"""
案件日志服务层
处理案件日志相关的业务逻辑
符合三层架构规范：业务逻辑、权限检查、事务处理
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from django.db import transaction
from django.db.models import QuerySet, Q
from django.core.files.uploadedfile import UploadedFile

from apps.core.exceptions import NotFoundError, ValidationException, PermissionDenied
from apps.core.interfaces import ICaseService, ServiceLocator
from ..models import Case, CaseLog, CaseLogAttachment, CaseLogVersion


class CaseLogService:
    """
    案件日志服务

    职责：
    - 日志的 CRUD 操作
    - 权限检查
    - 附件管理
    - 版本历史管理
    """

    # 允许的附件扩展名
    ALLOWED_EXTENSIONS = {
        ".pdf", ".doc", ".docx", ".xls", ".xlsx",
        ".ppt", ".pptx", ".jpg", ".jpeg", ".png"
    }

    # 最大文件大小 (50MB)
    MAX_FILE_SIZE = 50 * 1024 * 1024

    def __init__(self, case_service: ICaseService = None):
        """
        构造函数，支持依赖注入

        Args:
            case_service: 案件服务实例，None 时使用 ServiceLocator 获取
        """
        self._case_service = case_service or ServiceLocator.get_case_service()

    def list_logs(
        self,
        case_id: Optional[int] = None,
        user=None,
        org_access: Optional[Dict] = None,
        perm_open_access: bool = False,
    ) -> QuerySet:
        """
        获取日志列表

        Args:
            case_id: 案件 ID（可选，用于过滤）
            user: 当前用户
            org_access: 组织访问策略
            perm_open_access: 是否有开放访问权限

        Returns:
            日志查询集
        """
        qs = CaseLog.objects.all().order_by("-created_at").select_related("actor").prefetch_related("attachments")

        if case_id:
            qs = qs.filter(case_id=case_id)

        # 开放访问权限，返回全部
        if perm_open_access:
            return qs

        # 权限过滤
        if user and getattr(user, "is_authenticated", False):
            if getattr(user, "is_admin", False):
                return qs

            # 非管理员需要按组织策略过滤
            if org_access:
                qs = qs.filter(
                    Q(case__assignments__lawyer_id__in=list(org_access.get("lawyers", [])))
                    | Q(case__assignments__lawyer_id=getattr(user, "id", None))
                    | Q(case_id__in=list(org_access.get("extra_cases", set())))
                ).distinct()

        return qs

    def get_log(
        self,
        log_id: int,
        user=None,
        org_access: Optional[Dict] = None,
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
        log = self._get_log_internal(log_id)

        # 开放访问权限
        if perm_open_access:
            return log

        # 权限检查
        if not self._check_case_access(log.case, user, org_access):
            raise PermissionDenied("无权限访问此日志")

        return log

    def create_log(
        self,
        case_id: int,
        content: str,
        user=None,
        reminder_type: Optional[str] = None,
        reminder_time: Optional[datetime] = None,
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
        # 验证案件存在
        if not Case.objects.filter(id=case_id).exists():
            raise NotFoundError(f"案件 {case_id} 不存在")

        actor_id = getattr(user, "id", None) if user else None

        return CaseLog.objects.create(
            case_id=case_id,
            content=content,
            actor_id=actor_id,
            reminder_type=reminder_type,
            reminder_time=reminder_time,
        )

    @transaction.atomic
    def update_log(
        self,
        log_id: int,
        data: Dict[str, Any],
        user=None,
        org_access: Optional[Dict] = None,
        perm_open_access: bool = False,
    ) -> CaseLog:
        """
        更新案件日志（保存历史版本）

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
        log = self._get_log_internal(log_id)

        # 权限检查
        if not perm_open_access and not self._check_case_access(log.case, user, org_access):
            raise PermissionDenied("无权限修改此日志")

        old_content = log.content
        actor_id = getattr(user, "id", None) if user else None

        # 更新字段
        for key, value in data.items():
            setattr(log, key, value)
        log.save()

        # 如果内容变更，保存历史版本
        if "content" in data and data.get("content") != old_content:
            CaseLogVersion.objects.create(
                log=log,
                content=old_content,
                actor_id=actor_id,
            )

        return log

    def delete_log(
        self,
        log_id: int,
        user=None,
        org_access: Optional[Dict] = None,
        perm_open_access: bool = False,
    ) -> Dict[str, bool]:
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
        log = self._get_log_internal(log_id)

        # 权限检查
        if not perm_open_access and not self._check_case_access(log.case, user, org_access):
            raise PermissionDenied("无权限删除此日志")

        log.delete()
        return {"success": True}

    def upload_attachments(
        self,
        log_id: int,
        files: List[UploadedFile],
        user=None,
        org_access: Optional[Dict] = None,
        perm_open_access: bool = False,
    ) -> Dict[str, int]:
        """
        上传日志附件

        Args:
            log_id: 日志 ID
            files: 上传的文件列表
            user: 当前用户
            org_access: 组织访问策略
            perm_open_access: 是否有开放访问权限

        Returns:
            {"count": 上传数量}

        Raises:
            NotFoundError: 日志不存在
            PermissionDenied: 无权限上传
            ValidationException: 文件验证失败
        """
        log = self._get_log_internal(log_id)

        # 权限检查
        if not perm_open_access and not self._check_case_access(log.case, user, org_access):
            raise PermissionDenied("无权限上传附件")

        created = []
        for f in files:
            self._validate_attachment(f)
            created.append(CaseLogAttachment.objects.create(log=log, file=f))

        return {"count": len(created)}

    # ============================================================
    # 内部方法（无权限检查）
    # ============================================================

    def _get_log_internal(self, log_id: int) -> CaseLog:
        """
        内部方法：获取日志（无权限检查）

        Args:
            log_id: 日志 ID

        Returns:
            日志对象

        Raises:
            NotFoundError: 日志不存在
        """
        try:
            return CaseLog.objects.select_related("actor", "case").prefetch_related("attachments").get(id=log_id)
        except CaseLog.DoesNotExist:
            raise NotFoundError(f"日志 {log_id} 不存在")

    def _check_case_access(self, case_obj, user, org_access: Optional[Dict]) -> bool:
        """
        检查用户是否有权限访问案件

        Args:
            case_obj: 案件对象
            user: 当前用户
            org_access: 组织访问策略

        Returns:
            是否有权限
        """
        if not user or not getattr(user, "is_authenticated", False):
            return False

        # 管理员有全部权限
        if getattr(user, "is_admin", False):
            return True

        uid = getattr(user, "id", None)
        if not org_access:
            return False

        # 检查额外案件访问权限
        if case_obj.id in org_access.get("extra_cases", set()):
            return True

        # 检查团队成员或被指派到该案件
        lawyers = list(org_access.get("lawyers", []))
        if case_obj.assignments.filter(
            Q(lawyer_id__in=lawyers) | Q(lawyer_id=uid)
        ).exists():
            return True

        return False

    def _validate_attachment(self, file: UploadedFile) -> None:
        """
        验证附件文件

        Args:
            file: 上传的文件

        Raises:
            ValidationException: 验证失败
        """
        import os

        name = getattr(file, "name", "")
        ext = os.path.splitext(name)[1].lower()

        if ext not in self.ALLOWED_EXTENSIONS:
            raise ValidationException(
                "不支持的文件类型",
                errors={"file": f"允许的类型: {', '.join(self.ALLOWED_EXTENSIONS)}"}
            )

        size = getattr(file, "size", 0)
        if size and size > self.MAX_FILE_SIZE:
            raise ValidationException(
                "文件大小超过限制",
                errors={"file": f"最大允许 {self.MAX_FILE_SIZE // (1024*1024)}MB"}
            )

    # ============================================================
    # 实例方法（业务逻辑方法）
    # ============================================================

    def get_logs_for_case(
        self,
        case_id: int,
        user=None,
        org_access: Optional[Dict] = None,
        perm_open_access: bool = False,
    ) -> QuerySet:
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
        return self.list_logs(
            case_id=case_id,
            user=user,
            org_access=org_access,
            perm_open_access=perm_open_access,
        )

    def get_log_versions(
        self,
        log_id: int,
        user=None,
        org_access: Optional[Dict] = None,
        perm_open_access: bool = False,
    ) -> List[CaseLogVersion]:
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
        log = self._get_log_internal(log_id)

        # 权限检查
        if not perm_open_access and not self._check_case_access(log.case, user, org_access):
            raise PermissionDenied("无权限访问此日志版本")

        return list(
            CaseLogVersion.objects.filter(log_id=log_id)
            .select_related("actor")
            .order_by("-version_at")
        )

    def delete_attachment(
        self,
        attachment_id: int,
        user=None,
        org_access: Optional[Dict] = None,
        perm_open_access: bool = False,
    ) -> Dict[str, bool]:
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
        try:
            attachment = CaseLogAttachment.objects.select_related("log__case").get(id=attachment_id)
        except CaseLogAttachment.DoesNotExist:
            raise NotFoundError(f"附件 {attachment_id} 不存在")

        # 权限检查
        if not perm_open_access and not self._check_case_access(attachment.log.case, user, org_access):
            raise PermissionDenied("无权限删除此附件")

        if attachment.file:
            attachment.file.delete(save=False)

        attachment.delete()
        return {"success": True}
