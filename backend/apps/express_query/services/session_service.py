"""快递查询会话（扫码登录态）的解析、加锁与状态维护。"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING

from django.core.cache import cache
from django.utils import timezone

from apps.core.tasking import submit_task
from apps.express_query.models import ExpressSession, ExpressSessionStatus

if TYPE_CHECKING:
    from collections.abc import Iterator

    from apps.express_query.models import ExpressQueryTask
    from apps.organization.models import Lawyer

logger = logging.getLogger("apps.express_query")

#: 会话锁的过期时间（秒）。单次查询 600s 上限，留一点余量。
SESSION_LOCK_TTL: int = 700


class SessionUnavailableError(Exception):
    """当前律师没有可用的登录会话。"""


def get_or_create_session(lawyer: Lawyer, carrier_type: str) -> ExpressSession:
    """取该律师在某承运商下的会话记录（不存在则创建空会话）。"""
    session, _created = ExpressSession.objects.get_or_create(
        lawyer=lawyer,
        carrier_type=carrier_type,
        defaults={"status": ExpressSessionStatus.EMPTY},
    )
    return session


def resolve_session(task: ExpressQueryTask) -> ExpressSession | None:
    """解析任务应使用的会话。

    会话归属任务的创建人；创建人为空的历史任务回退到默认共享目录（None）。
    """
    lawyer = task.created_by
    if lawyer is None:
        logger.info("任务无创建人，回退到共享 profile 目录", extra={"task_id": task.id})
        return None

    return get_or_create_session(lawyer, task.carrier_type)


def _lock_key(session_id: int) -> str:
    return f"express_query:session_lock:{session_id}"


@contextmanager
def session_lock(session: ExpressSession | None) -> Iterator[None]:
    """同一会话串行化，避免两个任务同时操作同一浏览器导致 Cookie 互踩。

    拿不到锁直接抛错，由调用方把任务转入等待，而不是无限排队。
    """
    if session is None:
        yield
        return

    key = _lock_key(session.id)
    acquired = cache.add(key, "1", timeout=SESSION_LOCK_TTL)
    if not acquired:
        raise SessionUnavailableError("该账号正在被其他任务使用，请稍后重试")

    try:
        yield
    finally:
        try:
            cache.delete(key)
        except Exception:
            logger.debug("释放会话锁失败（已忽略）", exc_info=True)


def mark_login_success(session: ExpressSession) -> None:
    """扫码成功后标记会话可用。"""
    now = timezone.now()
    session.status = ExpressSessionStatus.ACTIVE
    session.last_login_at = now
    session.last_verified_at = now
    session.last_error = ""
    session.save(update_fields=["status", "last_login_at", "last_verified_at", "last_error", "updated_at"])
    logger.info("会话已激活", extra={"session_id": session.id, "carrier": session.carrier_type})


def mark_login_expired(session: ExpressSession, reason: str = "") -> None:
    """标记会话失效，等待重新扫码。"""
    session.status = ExpressSessionStatus.EXPIRED
    session.last_error = reason[:255]
    session.save(update_fields=["status", "last_error", "updated_at"])
    logger.info("会话已失效", extra={"session_id": session.id, "reason": reason})


def mark_verified(session: ExpressSession) -> None:
    """确认会话仍然有效。"""
    session.last_verified_at = timezone.now()
    session.save(update_fields=["last_verified_at", "updated_at"])


def enqueue_login_helper(lawyer_id: int, carrier_type: str) -> None:
    """投递一个「打开浏览器等扫码」的后台任务。"""
    submit_task(
        "apps.express_query.tasks.open_login_browser_task",
        lawyer_id,
        carrier_type,
        task_name="express_open_login",
    )
