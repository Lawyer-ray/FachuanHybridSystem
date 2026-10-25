"""DS 状态回调的处理服务：会话解析 + 保存回写。

官方语义（callback-handler 文档）：status=2（最后一个用户关闭文档 10 秒后）
与 status=6（forcesave/点击保存）时 body 带 `url`，指向**编辑后的文档**，
集成方必须拉取该 url 并落盘，然后才能应答 {"error": 0}——不落盘就应答
等于告诉 DS「已保存」，DS 随即清理临时副本，修订不可恢复地丢失。
保存失败必须返回 {"error": 1} 让 DS 重试。

保存后按官方要求轮换 document key，否则 DS 继续用缓存旧内容。

**版本模型**：saved_version 是**文档级**状态（同一 task 所有用户会话取
max），不是用户级——两名律师同开同一文档是同一个 DS 协同会话（同 key），
任一方保存都推进整个文档的版本；各自会话记录「我最近签发的 key」，保存
回写后重开会拿到聚合出的最新版本 key。
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import httpx
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from ..models import EditorSession
from .signing import make_document_key

logger = logging.getLogger(__name__)

# DS 侧文档体积上限（docx 编辑版不会更大；防御异常回调塞大文件）
_MAX_SAVE_BYTES = 100 * 1024 * 1024
_DOWNLOAD_TIMEOUT = 60.0


def _doc_saved_version(task_id: UUID) -> int:
    """文档级保存轮次：该 task 所有用户会话的 max(saved_version)。"""
    agg = EditorSession.objects.filter(task_type="contract_review", task_id=task_id).aggregate(m=Max("saved_version"))
    return int(agg["m"] or 0)


def get_or_refresh_session(
    *,
    task_id: UUID,
    user: Any,
    source_path: str,
    version: str,
) -> tuple[EditorSession, str]:
    """取（或建）该用户的会话，并按文档级 saved_version 算出本次生效的 key。

    返回 (session, document_key)。key = hash(source_path + version +
    文档级 saved_version)：同一文档对所有用户算出**同一 key**——这是 DS
    实时协同的前提（同 key = 同一编辑会话，两名律师同开一份合同能互相
    看到修订）；保存回写后文档级版本 +1，下次签发自然换 key。
    """
    session = EditorSession.objects.filter(task_type="contract_review", task_id=task_id, user=user).first()
    if session is None:
        session = EditorSession(task_type="contract_review", task_id=task_id, user=user)
    document_key = make_document_key(source_path, version, _doc_saved_version(task_id))
    if session.source_path != source_path or session.version != version or session.document_key != document_key:
        session.source_path = source_path
        session.version = version
        session.document_key = document_key
        session.save()
    return session, document_key


def load_session_by_key(key: str) -> EditorSession | None:
    """按回调里的 key 找会话。

    多用户同开同一文档时 key 相同、可能匹配多条（各会话都记录过它）；
    取最近更新的那条即可——落盘的是 DS 协同会话内容，与哪个用户触发
    保存无关，task 是同一个。
    """
    return EditorSession.objects.filter(document_key=key).order_by("-updated_at").first()


def _download_edited_docx(url: str) -> bytes:
    """拉取 DS 给的编辑后文档。DS 在内网容器，必须绕过系统代理（trust_env=False）。"""
    resp = httpx.get(url, trust_env=False, timeout=_DOWNLOAD_TIMEOUT, follow_redirects=True)
    resp.raise_for_status()
    if len(resp.content) > _MAX_SAVE_BYTES:
        raise ValueError(f"编辑产物超过大小上限: {len(resp.content)} bytes")
    return resp.content


def handle_save_callback(session: EditorSession, url: str, status: int) -> bool:
    """处理 status=2/6：下载编辑产物 → 落回业务实体 → 轮换 key。

    返回 False 时调用方应答 {"error": 1} 让 DS 重试。
    """
    from apps.contract_review.services.wiring import get_review_service

    if session.task_type != "contract_review":
        logger.warning("保存回写暂不支持业务域: %s", session.task_type)
        return False
    try:
        data = _download_edited_docx(url)
        svc = get_review_service()
        new_saved_version = _doc_saved_version(session.task_id) + 1
        old_output = _current_output_file(session.task_id)
        saved_name = svc.adopt_edited_output(session.task_id, data, version_tag=new_saved_version)
    except Exception:
        logger.warning("OnlyOffice 保存回写失败（DS 会重试）: key=%s", session.document_key, exc_info=True)
        return False

    with transaction.atomic():
        session.prev_output_file = old_output or ""
        session.saved_version = new_saved_version
        session.document_key = make_document_key(session.source_path, session.version, new_saved_version)
        session.last_callback_status = status
        session.last_saved_at = timezone.now()
        session.save()
    logger.info(
        "OnlyOffice 保存回写完成: task=%s v%d -> %s（旧产物留档 %s）",
        session.task_id,
        new_saved_version,
        saved_name,
        session.prev_output_file or "（无）",
    )
    return True


def _current_output_file(task_id: UUID) -> str:
    """读取任务当前产物路径（留档用）；任务缺失不阻断保存流程。"""
    from apps.contract_review.services.wiring import get_review_service

    try:
        task = get_review_service().get_task_status(task_id)
        return str(getattr(task, "output_file", "") or "")
    except Exception:
        logger.warning("读取任务 %s 当前产物失败（不影响保存）", task_id, exc_info=True)
        return ""


def record_callback_status(session: EditorSession, status: int) -> None:
    session.last_callback_status = status
    session.save(update_fields=["last_callback_status", "updated_at"])


def note_unknown_key(key: str) -> None:
    logger.warning("OnlyOffice 回调携带未知 document key: %s", key[:32] if key else "(空)")
