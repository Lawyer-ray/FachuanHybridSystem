"""从收件箱附件直接跑核对：字节由服务端取，前端不再整本 base64 上传。

## 为什么要有这条路

`/runs` 要求前端把整本 PDF 读成 base64：一本 40 页扫描件 26MB，base64 之后
约 35MB，浏览器要整份驻留内存、请求体还要过一遍 JSON 解析。而这份字节本来就
在服务端（IMAP / 一张网 / 手工上传都已经落到收件箱），再让前端搬一遍只是把
大文件从磁盘搬到内存再搬回来。

## 为什么复用 message_hub 的取字节路径

附件的真实位置取决于来源（本地上传落在 media、IMAP 可能要连服务器拉、一张网
另有一套适配器），`get_fetcher()` 是这些来源唯一的取字节入口。这里按
`attachment_thumbnail_service` 的同一条路走（先查 `attachments_meta`，再
fetcher），异常族也直接复用它的 `_fetch_errors()`：两处各写一份，等哪天新增
一种来源，总有一处漏掉——然后这条链路就是一个没人复现的 500。

可见性用 `can_view_message`，与收件箱各附件端点同一口径（见
`message_hub/services/inbox_access.py` 的审计结论）：核对接口同样会把附件内容
展开成结论，不收敛就等于给任意登录用户开了一个读别人材料的后门。

## 取不到就是 404，不是 500

消息不存在 / 无权看 / 该 part_index 不存在 / 字节读取失败，对调用方都是
「拿不到附件」——这是数据状态，不是服务端故障。404 带 `reason`，前端才能
说清缺的是哪一份。
"""

from __future__ import annotations

import logging
from typing import Any

from apps.core.exceptions import NotFoundError
from apps.doc_verify.services.verify import run as run_service
from apps.message_hub.services import get_fetcher
from apps.message_hub.services.attachment_thumbnail_service import _fetch_errors, find_attachment_meta
from apps.message_hub.services.inbox_access import can_view_message
from apps.message_hub.services.inbox_query import get_message_or_none

logger = logging.getLogger(__name__)


def verify_from_material(
    *,
    artifact: Any,
    message_id: int,
    part_index: int,
    tier: int | None = None,
    operator: Any,
) -> Any:
    """取收件箱附件的字节跑一次核对，返回 `VerificationRun`（幂等口径与 `/runs` 一致）。

    `source_message_id` 记的就是这条收件箱消息的主键：核对结论要能指回「是哪一份
    材料跑出来的」，否则出问题时无法回到原件。
    """
    data, file_name = load_material_bytes(message_id=message_id, part_index=part_index, user=operator)
    return run_service.verify_inbound(
        artifact=artifact,
        data=data,
        file_name=file_name,
        source_message_id=message_id,
        tier=tier,
    )


def load_material_bytes(*, message_id: int, part_index: int, user: Any) -> tuple[bytes, str]:
    """按消息 + part_index 取附件字节与文件名；任何一环拿不到都抛 404（带 reason）。"""
    message = get_message_or_none(message_id)
    # 不存在与无权看合并成同一个 404：把「无权」写成「不存在」是为了不泄露消息是否存在
    if message is None or not can_view_message(user, message):
        raise NotFoundError(
            message=f"收件箱消息不存在：{message_id}",
            code="INBOX_MESSAGE_NOT_FOUND",
            errors={"message_id": message_id, "reason": "消息不存在或无权访问"},
        )
    att = _attachment_meta(message_id=message_id, part_index=part_index, message=message)
    data, served_name, _content_type = _fetch_bytes(message, part_index)
    if not data:
        raise NotFoundError(
            message=f"附件没有内容：message={message_id} part_index={part_index}",
            code="INBOX_ATTACHMENT_EMPTY",
            errors={"message_id": message_id, "part_index": part_index, "reason": "附件字节为空"},
        )
    file_name = served_name or str(att.get("filename") or att.get("original_filename") or "")
    return bytes(data), file_name


def _attachment_meta(*, message_id: int, part_index: int, message: Any) -> dict[str, Any]:
    """先查 meta 里有没有这个 part_index：没有就不必去联网/读盘了。"""
    try:
        return find_attachment_meta(message, part_index)
    except NotFoundError as exc:
        raise NotFoundError(
            message=f"该消息没有第 {part_index} 个附件：message={message_id}",
            code="INBOX_ATTACHMENT_NOT_FOUND",
            errors={"message_id": message_id, "part_index": part_index, "reason": "附件不存在"},
        ) from exc


def _fetch_bytes(message: Any, part_index: int) -> tuple[bytes, str, str]:
    """走 message_hub 的 fetcher 取字节；异常族与缩略图共用一份（见模块 docstring）。"""
    try:
        fetcher = get_fetcher(message.source.source_type)
        content, filename, content_type = fetcher.download_attachment(message.source, message.message_id, part_index)
    except _fetch_errors() as exc:
        logger.warning("取收件箱附件字节失败 message=%s part=%s: %s", message.pk, part_index, exc)
        raise NotFoundError(
            message=f"取不到附件字节：message={message.pk} part_index={part_index}",
            code="INBOX_ATTACHMENT_UNAVAILABLE",
            errors={"message_id": message.pk, "part_index": part_index, "reason": str(exc) or type(exc).__name__},
        ) from exc
    return bytes(content), filename, content_type
