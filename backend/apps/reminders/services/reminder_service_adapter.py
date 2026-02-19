"""
提醒服务适配器

实现 IReminderService 接口,供其他模块(如案件模块、自动化模块)调用.
使用延迟导入避免循环依赖.

Requirements: 4.5, 7.2
"""

import logging
from collections.abc import Iterable
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar, Optional, cast

if TYPE_CHECKING:
    from apps.core.dtos import ReminderDTO, ReminderTypeDTO

logger = logging.getLogger(__name__)


class ReminderServiceAdapter:
    """
    提醒服务适配器

    实现 IReminderService 接口,提供提醒模块的核心功能给其他模块使用.
    使用延迟导入避免循环依赖问题.

    Requirements: 4.5, 7.2
    """

    # ============================================================
    # 文书类型到提醒类型的映射
    # ============================================================
    DOCUMENT_TYPE_TO_REMINDER_TYPE: ClassVar[dict[str, str]] = {
        # 开庭传票: "hearing",
        "court_summons": "hearing",
        "hearing_summons": "hearing",
        # 举证通知: "evidence_deadline",
        "evidence_deadline_notice": "evidence_deadline",
        # 缴费通知: "payment_deadline",
        "fee_notice": "payment_deadline",
        # 补正通知: "submission_deadline",
        "submission_notice": "submission_deadline",
        # 判决书/裁定书: "appeal_deadline",
        "ruling": "appeal_deadline",
        "verdict": "appeal_deadline",
        # 财产保全裁定: "asset_preservation_expires",
        "asset_preservation": "asset_preservation_expires",
    }

    # ============================================================
    # 内部方法 - 供跨模块调用(无权限检查)
    # Requirements: 4.5, 7.2
    # ============================================================

    def create_reminder_internal(
        self, case_log_id: int, reminder_type: str, reminder_time: datetime | None, user_id: int | None = None
    ) -> Optional["ReminderDTO"]:
        """
        内部方法:创建提醒

        Args:
            case_log_id: 案件日志 ID
            reminder_type: 提醒类型代码
            reminder_time: 提醒时间
            user_id: 用户 ID(可选,暂未使用)

        Returns:
            ReminderDTO,创建失败返回 None

        Requirements: 4.5, 7.2
        """
        try:
            from django.utils import timezone

            from apps.reminders.models import Reminder, ReminderType

            # 验证提醒类型是否有效
            if reminder_type not in ReminderType.values:
                logger.warning(
                    f"无效的提醒类型: {reminder_type}",
                    extra={"case_log_id": case_log_id, "reminder_type": reminder_type},
                )
                return None

            # 获取提醒类型的显示名称作为内容
            reminder_type_label = ReminderType(reminder_type).label

            # 处理时间
            if not reminder_time:
                logger.warning(
                    "提醒时间为空，跳过创建",
                    extra={"case_log_id": case_log_id, "reminder_type": reminder_type},
                )
                return None
            if timezone.is_naive(reminder_time):
                reminder_time = timezone.make_aware(reminder_time)

            # 创建提醒
            reminder = Reminder.objects.create(
                case_log_id=case_log_id,
                reminder_type=reminder_type,
                content=str(reminder_type_label),
                due_at=reminder_time,
                metadata={"created_by_user_id": user_id} if user_id else {},
            )

            logger.info(
                "创建提醒成功",
                extra={
                    "reminder_id": reminder.pk,
                    "case_log_id": case_log_id,
                    "reminder_type": reminder_type,
                },
            )

            return self._to_reminder_dto(reminder)

        except Exception:
            logger.exception(
                "create_reminder_internal_failed",
                extra={"case_log_id": case_log_id, "reminder_type": reminder_type, "user_id": user_id},
            )
            raise

    def get_reminder_type_by_code_internal(self, code: str) -> Optional["ReminderTypeDTO"]:
        """
        内部方法:根据代码获取提醒类型

        Args:
            code: 提醒类型代码

        Returns:
            ReminderTypeDTO,不存在返回 None

        Requirements: 4.5, 7.2
        """
        try:
            from apps.core.dtos import ReminderTypeDTO
            from apps.reminders.models import ReminderType

            # 检查代码是否有效
            if code not in ReminderType.values:
                logger.debug(f"提醒类型代码不存在: {code}")
                return None

            # 获取提醒类型信息
            reminder_type = ReminderType(code)

            return ReminderTypeDTO(
                id=list(ReminderType.values).index(code) + 1,  # 使用索引作为 ID
                code=code,
                name=str(reminder_type.label),
                description=None,
            )

        except Exception:
            logger.exception("get_reminder_type_by_code_internal_failed", extra={"code": code})
            raise

    def get_reminder_type_for_document_internal(self, document_type: str) -> Optional["ReminderTypeDTO"]:
        """
        内部方法:根据文书类型获取对应的提醒类型

        Args:
            document_type: 文书类型

        Returns:
            ReminderTypeDTO,不存在返回 None

        Requirements: 4.5, 7.2
        """
        try:
            # 查找映射的提醒类型代码
            reminder_type_code = self.DOCUMENT_TYPE_TO_REMINDER_TYPE.get(document_type)

            if not reminder_type_code:
                logger.debug(f"文书类型 {document_type} 没有对应的提醒类型")
                return None

            # 使用已有方法获取提醒类型
            return self.get_reminder_type_by_code_internal(reminder_type_code)

        except Exception:
            logger.exception("get_reminder_type_for_document_internal_failed", extra={"document_type": document_type})
            raise

    def get_existing_reminder_times_internal(self, case_log_id: int, reminder_type: str) -> set[datetime]:
        """
        内部方法:获取案件日志已存在的提醒时间集合

        Args:
            case_log_id: 案件日志 ID
            reminder_type: 提醒类型代码

        Returns:
            已存在的提醒时间集合 (set of datetime)

        Requirements: 5.2
        """
        try:
            from apps.reminders.models import Reminder

            due_at_values = Reminder.objects.filter(
                case_log_id=case_log_id,
                reminder_type=reminder_type,
            ).values_list("due_at", flat=True)
            existing_times = set(cast(Iterable[datetime], due_at_values))

            logger.debug(
                "获取已存在的提醒时间",
                extra={
                    "case_log_id": case_log_id,
                    "reminder_type": reminder_type,
                    "count": len(existing_times),
                },
            )

            return existing_times

        except Exception:
            logger.exception(
                "get_existing_reminder_times_internal_failed",
                extra={"case_log_id": case_log_id, "reminder_type": reminder_type},
            )
            raise

    def create_contract_reminders_internal(self, *, contract_id: int, reminders: list[dict[str, Any]]) -> int:
        from django.utils import timezone

        from apps.reminders.models import Reminder, ReminderType

        if not contract_id or not reminders:
            return 0

        objs: list[Reminder] = []
        for item in reminders:
            reminder_type = (item.get("reminder_type") or "").strip()
            content = (item.get("content") or "").strip()
            due_at = item.get("due_at")
            metadata = item.get("metadata") or {}

            if not reminder_type or reminder_type not in ReminderType.values:
                continue
            if not content:
                continue
            if not due_at or not isinstance(due_at, datetime):
                continue
            if timezone.is_naive(due_at):
                due_at = timezone.make_aware(due_at)

            objs.append(
                Reminder(
                    contract_id=contract_id,
                    reminder_type=reminder_type,
                    content=content,
                    due_at=due_at,
                    metadata=metadata,
                )
            )

        if not objs:
            return 0

        Reminder.objects.bulk_create(objs)
        return len(objs)

    # ============================================================
    # 辅助方法
    # ============================================================

    def _to_reminder_dto(self, reminder: Any) -> "ReminderDTO":
        """
        将 Reminder Model 转换为 DTO

        Args:
            reminder: Reminder Model 实例

        Returns:
            ReminderDTO 实例
        """
        from apps.core.dtos import ReminderDTO

        reminder_id = getattr(reminder, "id", None)
        if reminder_id is None:
            reminder_id = getattr(reminder, "pk", None)

        return ReminderDTO(
            id=cast(int, reminder_id),
            case_log_id=cast(int, reminder.case_log_id),
            reminder_type=cast(str, reminder.reminder_type),
            reminder_time=str(reminder.due_at) if reminder.due_at else "",
            is_completed=False,  # Reminder 模型没有 is_completed 字段,默认 False
            created_at=str(reminder.created_at) if reminder.created_at else None,
        )
