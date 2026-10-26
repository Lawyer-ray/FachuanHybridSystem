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
from uuid import UUID, uuid5

import httpx
from django.db import transaction
from django.db.models import F, Max
from django.utils import timezone

from ..models import EditorSession
from .signing import make_document_key

logger = logging.getLogger(__name__)

# DS 侧文档体积上限（docx 编辑版不会更大；防御异常回调塞大文件）
_MAX_SAVE_BYTES = 100 * 1024 * 1024

# 从路径派生会话 id 的命名空间（固定值，改了会与存量会话对不上）
_SESSION_NS = UUID("6f1b0c2e-7a41-5d8e-9b3c-2f4a6d8e0c11")
_DOWNLOAD_TIMEOUT = 60.0


def _doc_external_seq(task_id: UUID, task_type: str = "contract_review") -> int:
    """文档级外部写入代次（同一业务域同一任务取 max）。

    与 `_doc_saved_version` 同构：外写是**文档级**事件（AI 改的是盘上那份文件），
    两个律师同时开着同一份文件时，任一方触发的外部写入都会让两边的画布同时过期。
    """
    agg = EditorSession.objects.filter(task_type=task_type, task_id=task_id).aggregate(m=Max("external_write_seq"))
    return int(agg["m"] or 0)


def _doc_saved_version(task_id: UUID, task_type: str = "contract_review") -> int:
    """文档级保存轮次：同一业务域同一任务，所有用户会话的 max(saved_version)。

    `task_type` 必须带：合同文件夹（`contract_folder`）与审查任务可能算出同一个
    UUID（folder 是从路径派生的），不带域就会把两边的轮次混在一起。
    """
    agg = EditorSession.objects.filter(task_type=task_type, task_id=task_id).aggregate(m=Max("saved_version"))
    return int(agg["m"] or 0)


def session_id_for_path(source_path: str) -> UUID:
    """为「没有业务 task_id」的业务域（合同文件夹）派生稳定 UUID。

    `EditorSession.task_id` 是 UUIDField，而 folder 的主键是自增 int。用一个
    从路径派生的 uuid5 既能落进现有表结构，又保证「同一路径永远同一 id」——
    否则每次签配置都算新 id，会话查不到、保存回调全失败。
    """
    return uuid5(_SESSION_NS, source_path)


def bump_external_write(source_path: str, task_type: str = "contract_folder") -> int:
    """文档在编辑器之外被覆写（如 AI 划词直改落盘）后轮换文档 key。

    DS 按 document.key 缓存文档内容，不轮换的话已打开/重开的编辑器拿到的
    都是旧缓存——「AI 说已改好、画布却没有任何改动痕迹」正是缺这一步。
    与保存回写同一口径：把文档级 saved_version 抬到 max+1（key 由
    max(saved_version) 聚合而来，抬任意一条会话即可，这里统一抬全部）。

    返回推进后的版本号；该文档从没人打开过（无会话）返回 0——下次签配置
    本来就会取到覆写后的新内容，无需轮换。
    """
    task_id = session_id_for_path(source_path)
    new_saved_version = _doc_saved_version(task_id, task_type) + 1
    # **只抬文档级计数器**，绝不能动 canvas_seq：
    # canvas_seq 记的是「这份画布是按第几代签发的」，一旦跟着涨，
    # stale 判据就恒为 False（守门人变死代码，AI 的修订照样被旧画布盖掉）。
    # F() 原子自增，避免多 worker 并发外部写时丢计数。
    updated = EditorSession.objects.filter(task_type=task_type, task_id=task_id).update(
        saved_version=new_saved_version, external_write_seq=F("external_write_seq") + 1
    )
    if not updated:
        return 0
    logger.info("外部覆写后轮换文档 key: task_type=%s task=%s saved_version=%d", task_type, task_id, new_saved_version)
    return new_saved_version


def get_or_refresh_session(
    *,
    task_id: UUID,
    user: Any,
    source_path: str,
    version: str,
    task_type: str = "contract_review",
) -> tuple[EditorSession, str]:
    """取（或建）该用户的会话，并按文档级 saved_version 算出本次生效的 key。

    返回 (session, document_key)。key = hash(source_path + version +
    文档级 saved_version)：同一文档对所有用户算出**同一 key**——这是 DS
    实时协同的前提（同 key = 同一编辑会话，两名律师同开一份合同能互相
    看到修订）；保存回写后文档级版本 +1，下次签发自然换 key。
    """
    session = EditorSession.objects.filter(task_type=task_type, task_id=task_id, user=user).first()
    if session is None:
        session = EditorSession(task_type=task_type, task_id=task_id, user=user)
    document_key = make_document_key(source_path, version, _doc_saved_version(task_id, task_type))
    if session.source_path != source_path or session.version != version or session.document_key != document_key:
        session.source_path = source_path
        session.version = version
        session.document_key = document_key
        # 新签发的 key 意味着浏览器会（重新）向 DS 拉一份**当下磁盘**的内容，
        # 所以把画布代次快照对齐到文档级——这是**登记**，不是「跟着计数器涨」：
        # 此后 external_write_seq 再涨，本会话的 canvas_seq 就落在后面了，
        # stale 判据才能生效。
        session.canvas_seq = _doc_external_seq(task_id, task_type)
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


def stale_canvas_reason(session: EditorSession) -> str:
    """保存回调若会把外部写入盖掉，返回原因文案；否则返回空串。

    **为什么必须拦**：DS 的 forcesave/关闭回调交回的是**编辑器内存里的画布内容**。
    AI 划词直改走后端直接改 docx（`direct_edit_service`），磁盘已经变了、画布还是
    旧的；一旦这份旧画布被回写，AI 刚落的 `w:ins`/`w:del` 就被整篇静默覆盖——
    真机表现为「AI 说改好了，关掉编辑器再打开又变回旧文」。

    判据：文档级外写代次 > 该会话签发 key 时记下的代次，说明画布是外写**之前**
    加载的，属于过期内容。
    """
    doc_seq = _doc_external_seq(session.task_id, session.task_type)
    # 比的是「文档现在第几代」vs「这份画布签发时的代次快照」。
    # 不能用 external_write_seq（它和 doc_seq 永远相等，判据会恒假）。
    if doc_seq <= int(session.canvas_seq or 0):
        return ""
    return "文档已被 AI 改写（磁盘内容新于当前画布），本次保存已忽略以免覆盖修订；请关闭并重新打开文档后再编辑"


def handle_save_callback(session: EditorSession, url: str, status: int) -> bool:
    """处理 status=2/6：下载编辑产物 → 落回业务实体 → 轮换 key。

    返回 False 时调用方应答 {"error": 1} 让 DS 重试。
    """
    from .domain_registry import get_domain

    domain = get_domain(session.task_type)
    if domain is None:
        logger.warning("保存回写暂不支持业务域: %s", session.task_type)
        return False
    # 先判「画布是否已落后于磁盘」：AI 划词直改直写 docx 并抬了外写代次，
    # 这份画布若还是旧代次签发的，回写就是拿旧内容盖掉 AI 刚落的修订。
    # 返回 True 而非 False 是故意的：不让落盘、也不让 DS 重试——重试还是
    # 同一份旧内容，只会无限循环；丢掉这一次保存才是正确结果。
    stale = stale_canvas_reason(session)
    if stale:
        logger.warning(
            "忽略过期画布的保存回调（外部写入比画布新）: task=%s key=%s",
            session.task_id,
            session.document_key,
        )
        record_callback_status(session, status)
        return True
    try:
        data = _download_edited_docx(url)
        new_saved_version = _doc_saved_version(session.task_id) + 1
        old_output = _current_output_file(session.task_id, session.task_type)
        # 落盘目标交给业务域钩子（新增业务域不用改本函数）：
        # review 域改任务产物、folder 域覆写原文件
        saved_name = domain.adopt_edited(session, data, new_saved_version)
    except Exception:
        logger.warning("OnlyOffice 保存回写失败（DS 会重试）: key=%s", session.document_key, exc_info=True)
        return False

    with transaction.atomic():
        session.prev_output_file = old_output or ""
        session.saved_version = new_saved_version
        session.document_key = make_document_key(session.source_path, session.version, new_saved_version)
        session.last_callback_status = status
        session.last_saved_at = timezone.now()
        # 本次落盘成功 = 磁盘与这份画布已一致：把快照推到文档级，
        # 之后自己的保存不会再被当成旧画布（而别人的旧画布仍然会被拦）。
        session.canvas_seq = _doc_external_seq(session.task_id, session.task_type)
        session.save()
    logger.info(
        "OnlyOffice 保存回写完成: task=%s v%d -> %s（旧产物留档 %s）",
        session.task_id,
        new_saved_version,
        saved_name,
        session.prev_output_file or "（无）",
    )
    return True


def _current_output_file(task_id: UUID, task_type: str = "contract_review") -> str:
    """读取任务当前产物路径（留档用）；任务缺失/不适用不阻断保存流程。

    只有 `contract_review` 有「旧产物」概念（adopt_edited_output 会另存新文件名）。
    合同文件夹是**原地覆写**，没有旧产物可留档，直接返回空。
    """
    if task_type != "contract_review":
        return ""

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
