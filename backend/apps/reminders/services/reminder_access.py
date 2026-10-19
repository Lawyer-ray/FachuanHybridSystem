"""提醒的写权限判定（安全审计 2026Q4 M-1）。

背景：``Reminder`` 的三个关联字段（contract / case / case_log）全空时即
「全局提醒」——团队共享日程（如全所统一的培训、放假安排）。这类提醒**任何人
可读**，但历史上修改/删除只校验了关联对象的访问权，而全局提醒没有任何关联
对象可校验，于是 ``_ensure_target_access`` 形同虚设：**任何登录用户可以列出、
修改、删除全所任何人的全局提醒**（横向越权，信息泄露 + 完整性破坏）。

本模块把写权限判定收敛到一处，API 层各写端点复用：

- 全局提醒 → 仅**创建人本人**与管理员（``is_superuser`` / ``is_admin``）可写；
- 关联了合同/案件/案件日志的提醒 → 写权限由调用方已做过的关联对象
  ``AccessPolicy`` 校验决定，本模块不再重复（保持原有行为不变）。

fail-closed：全局提醒的 ``created_by`` 为空（存量数据未回填、或创建人账号
已删）时**不允许任何非管理员写**——宁可让管理员兜底，也不退回「人人可写」。

注意与读权限的区别：读（列表/详情/日历）对全局提醒保持「创建人本人 + 管理员」
（见 ``calendar_month_service._scope_for_context``），本模块只管写。

删除单列一档（``can_delete_reminder``）：改 / 勾完成对关联了案件、合同的提醒
放行给所有有访问权的人（同案同事要能勾完成、改时间），但删除是不可逆的破坏
性操作，产品口径收敛为「谁创建谁删」——即使两人同在一个案件，A 也不能删 B
建的日程；管理员豁免。
"""

from __future__ import annotations

from typing import Any

from apps.core.exceptions import PermissionDenied
from apps.core.security.admin_access import is_admin_user

# 解耦（2026-10-19）：is_admin_user 删除本地同体实现，改为对
# core.security.admin_access.is_admin_user 的 re-export（tests 等外部 import 不断裂）。
# 口径不变：superuser 或 is_admin（Lawyer 的管理员标志）视为全所管理员；
# is_staff 仅是 Django admin 准入标志，不视为系统管理员。


def can_write_reminder(user: Any | None, reminder: Any) -> bool:
    """当前用户是否可修改/删除该提醒。

    关联了合同/案件/案件日志的提醒返回 True——调用方在拿到对象后已做过
    ``_ensure_target_access``，此处不重复判定。
    """
    if reminder is None:
        return False
    if not getattr(reminder, "is_global", True):
        return True
    if is_admin_user(user):
        return True
    if user is None:
        return False
    creator_id = getattr(reminder, "created_by_id", None)
    if creator_id is None:
        # 全局提醒但无创建人记录（存量未回填 / 创建人已删）→ 拒绝非管理员
        return False
    return bool(creator_id == getattr(user, "id", None))


def ensure_can_write_reminder(user: Any | None, reminder: Any) -> None:
    """写权限校验，不通过抛 PermissionDenied（403）。

    与 message_hub 的 IDOR 修复不同，这里**故意不返回 404**：提醒的存在性
    本身不是敏感信息（前端列表已能看到标题），且「你改了但没权限」比
    「404 让人以为没保存成功」更利于排错。
    """
    if can_write_reminder(user, reminder):
        return
    raise PermissionDenied(
        message="仅提醒创建人或管理员可以修改/删除该提醒",
        code="REMINDER_NOT_OWNER",
    )


def reminder_creator_id(reminder: Any) -> int | None:
    """提醒的创建人 id：优先 ``created_by`` FK，回退 ``metadata.created_by_user_id``。

    回退不是历史包袱：案件日志等内部路径（``reminder_service_adapter``）至今
    只写 metadata、不填 FK，与 ``calendar_month_service._scope_for_context``
    的可见性判定取同一口径，否则同一条提醒会「看得见却删不掉」。
    """
    creator_id = getattr(reminder, "created_by_id", None)
    if creator_id is not None:
        return int(creator_id)
    metadata = getattr(reminder, "metadata", None)
    if not isinstance(metadata, dict):
        return None
    legacy = metadata.get("created_by_user_id")
    if isinstance(legacy, bool) or not isinstance(legacy, int):
        return None
    return legacy


def can_delete_reminder(user: Any | None, reminder: Any) -> bool:
    """当前用户是否可删除该提醒：仅创建人本人与管理员，不看关联对象的访问权。

    无创建人记录（同步 / 导入产生、存量未回填、创建人已删）时 fail-closed，
    只有管理员能删。
    """
    if reminder is None or user is None:
        return False
    if is_admin_user(user):
        return True
    creator_id = reminder_creator_id(reminder)
    if creator_id is None:
        return False
    return bool(creator_id == getattr(user, "id", None))


def ensure_can_delete_reminder(user: Any | None, reminder: Any) -> None:
    """删除权限校验，不通过抛 PermissionDenied（403，理由同 ensure_can_write_reminder）。"""
    if can_delete_reminder(user, reminder):
        return
    raise PermissionDenied(
        message="仅提醒创建人或管理员可以删除该提醒",
        code="REMINDER_NOT_CREATOR",
    )
