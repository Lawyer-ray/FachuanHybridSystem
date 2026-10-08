"""收件箱消息/来源的可见性策略。

安全审计（2026Q4 IDOR）：收件箱是全所案件材料的汇聚点（法院送达文书、当事人
上传的身份证/合同/证据 PDF）。历史上 ``list_messages`` / ``list_sources`` /
各附件端点均未按用户收敛，任意登录用户可遍历 message_id 批量拉取全库材料。

本模块把可见性判定收敛到一处，供 API 层各端点复用：

- **手动上传的消息**（``InboxMessage.uploaded_by`` 非空）：仅上传人本人与
  superuser/admin 可见——上传是明确的个人归属行为。
- **外部拉取的消息**（IMAP/法院短信等，``uploaded_by`` 为空）：按来源凭证
  属主收敛，即 ``MessageSource.credential.lawyer`` 为当前用户，或
  superuser/admin 可见。外部来源本身由管理员/凭证属主配置（见
  ``message_source_api._ensure_source_manageable``），其拉取结果应同边界。

判定同时覆盖 QuerySet 过滤（列表）与单对象校验（详情/附件/改删）。
"""

from __future__ import annotations

from typing import Any

from django.db.models import Q, QuerySet

from apps.message_hub.models import InboxMessage, MessageSource


def is_admin_user(user: Any | None) -> bool:
    """superuser 或 is_admin（Lawyer 的管理员标志）视为全所可见。

    is_staff 仅是 Django admin 准入标志，不视为系统管理员——与
    ``message_source_api._ensure_source_manageable`` 口径一致。
    """
    if user is None:
        return False
    return bool(getattr(user, "is_superuser", False) or getattr(user, "is_admin", False))


def can_view_message(user: Any | None, msg: InboxMessage) -> bool:
    """当前用户是否可访问该条收件箱消息。"""
    if is_admin_user(user):
        return True
    if user is None:
        return False
    uploader_id = getattr(msg, "uploaded_by_id", None)
    if uploader_id is not None:
        return bool(uploader_id == getattr(user, "id", None))
    return _can_view_source_owner(user, getattr(msg, "source", None))


def can_view_source(user: Any | None, source: MessageSource) -> bool:
    """当前用户是否可访问该消息来源。"""
    if is_admin_user(user):
        return True
    if user is None:
        return False
    return _can_view_source_owner(user, source)


def _can_view_source_owner(user: Any, source: Any) -> bool:
    """外部来源按凭证属主收敛；无凭证来源仅管理员可见。"""
    if source is None:
        return False
    credential = getattr(source, "credential", None)
    if credential is None:
        return False
    return bool(getattr(credential, "lawyer_id", None) == getattr(user, "id", None))


def visible_messages_qs(user: Any | None) -> QuerySet[InboxMessage]:
    """按当前用户收敛的收件箱消息 QuerySet（含 source/credential 关联预取）。"""
    from apps.message_hub.services.inbox_query import get_base_queryset

    qs = get_base_queryset()
    if is_admin_user(user):
        return qs
    if user is None:
        return qs.none()
    user_id = getattr(user, "id", None)
    # 手动上传归本人；外部拉取归来源凭证属主。uploaded_by 为空且来源无凭证的
    # 历史数据不落入任一条件，仅管理员可见（fail-closed）。
    return qs.filter(Q(uploaded_by_id=user_id) | Q(source__credential__lawyer_id=user_id))


def visible_sources_qs(user: Any | None) -> QuerySet[MessageSource]:
    """按当前用户收敛的消息来源 QuerySet。"""
    qs = MessageSource.objects.select_related("credential")
    if is_admin_user(user):
        return qs
    if user is None:
        return qs.none()
    # django-stubs 对可选值的 lookup 报 misc，已在上方 is_admin/user None 分支
    # 之后收窄；此处显式取值以满足类型检查（运行期等价）。
    user_id = int(user.id)
    return qs.filter(credential__lawyer_id=user_id)
