"""一张网收件箱 fetcher — 拉取文书送达消息并触发下载。"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.message_hub.models import InboxMessage, SyncStatus
from apps.message_hub.services.base import MessageFetcher

if TYPE_CHECKING:
    from apps.message_hub.models import MessageSource

logger = logging.getLogger("apps.message_hub")

_LIST_API = "https://zxfw.court.gov.cn/yzw/yzw-zxfw-sdfw/api/v1/sdfw/getSdListByZjhmAndAhdmNew"
_DETAIL_API = "https://zxfw.court.gov.cn/yzw/yzw-zxfw-sdfw/api/v1/sdfw/getWsListBySdbhNew"
_TIMEOUT = 30.0
_PAGE_SIZE = 20


def _api_post(url: str, token: str, data: dict[str, Any]) -> dict[str, Any]:
    """发送 POST 请求到一张网 API。"""
    headers = {"Authorization": token, "Content-Type": "application/json"}
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.post(url, headers=headers, json=data)
    if resp.status_code == 401:
        raise PermissionError(_("Token 已过期"))
    resp.raise_for_status()
    body: dict[str, Any] = resp.json()
    if body.get("code") != 200:
        raise RuntimeError(f"API 错误: {body.get('msg', body)}")
    return body


def _acquire_token(credential_id: int) -> str:
    """复用现有 token 获取链路。"""
    from apps.automation.services.document_delivery.token.document_delivery_token_service import (
        DocumentDeliveryTokenService,
    )

    svc = DocumentDeliveryTokenService()
    token = svc.acquire_token(credential_id)
    if not token:
        raise RuntimeError(_("无法获取一张网 Token"))
    return token


def _build_subject(record: dict[str, Any]) -> str:
    ah = record.get("ah", "")
    wsmc = record.get("wsmc", "")
    return f"{ah} - {wsmc}" if ah else wsmc or str(_("(无主题)"))


def _build_body(record: dict[str, Any]) -> str:
    lines = [
        f"案号：{record.get('ah', '')}",
        f"法院：{record.get('fymc', '')}",
        f"文书：{record.get('wsmc', '')}",
        f"发起人：{record.get('fqr', '')}",
        f"送达状态：{record.get('sdzt', '')}",
        f"签到状态：{record.get('qdzt', '')}",
        f"发送时间：{record.get('fssj', '')}",
    ]
    return "\n".join(lines)


from datetime import datetime as _dt


def _parse_datetime(s: str) -> _dt:
    try:
        dt = _dt.strptime(s, "%Y-%m-%d %H:%M:%S")
        return timezone.make_aware(dt)
    except (ValueError, TypeError):
        return timezone.now()


def _fetch_attachments_meta(token: str, sdbh: str) -> list[dict[str, Any]]:
    """获取文书详情（附件元信息 + 下载链接）。"""
    try:
        body = _api_post(_DETAIL_API, token, {"sdbh": sdbh, "sdsin": "", "mm": ""})
        items = body.get("data", [])
        meta: list[dict[str, Any]] = []
        for i, item in enumerate(items):
            wjlj = item.get("wjlj", "")
            if not wjlj:
                continue
            ext = item.get("c_wjgs", "pdf")
            name = item.get("c_wsmc", f"文书_{i}")
            meta.append({
                "filename": f"{name}.{ext}",
                "content_type": f"application/{ext}",
                "size": 0,
                "part_index": i,
                "wjlj": wjlj,
                "c_sdbh": item.get("c_sdbh", ""),
                "c_wsbh": item.get("c_wsbh", ""),
            })
        return meta
    except Exception as e:
        logger.warning("获取文书详情失败 sdbh=%s: %s", sdbh, e)
        return []


class CourtInboxFetcher(MessageFetcher):
    """一张网（zxfw.court.gov.cn）收件箱拉取器。"""

    def fetch_new_messages(self, source: MessageSource) -> int:
        credential_id = source.credential.pk
        try:
            token = _acquire_token(credential_id)
        except Exception as e:
            _mark_failed(source, str(e))
            raise

        try:
            new_count = 0
            # 第一页
            body = _api_post(_LIST_API, token, {"pageNum": 1, "pageSize": _PAGE_SIZE})
            data = body.get("data", {})
            total = data.get("total", 0)
            total_pages = max(1, math.ceil(total / _PAGE_SIZE))
            logger.info("一张网收件箱: 共 %d 条, %d 页", total, total_pages)

            new_count += self._process_page(source, token, data.get("data", []))

            for page_num in range(2, total_pages + 1):
                try:
                    body = _api_post(_LIST_API, token, {"pageNum": page_num, "pageSize": _PAGE_SIZE})
                    new_count += self._process_page(source, token, body.get("data", {}).get("data", []))
                except Exception as e:
                    logger.error("处理第 %d 页失败: %s", page_num, e)

            _mark_success(source)
            return new_count
        except Exception as e:
            _mark_failed(source, str(e))
            raise

    def _process_page(self, source: MessageSource, token: str, records: list[dict[str, Any]]) -> int:
        new_count = 0
        for record in records:
            sdbh = record.get("sdbh", "")
            if not sdbh:
                continue

            # 去重
            if InboxMessage.objects.filter(source=source, message_id=sdbh).exists():
                continue

            attachments_meta = _fetch_attachments_meta(token, sdbh)

            InboxMessage.objects.create(
                source=source,
                message_id=sdbh,
                subject=_build_subject(record),
                sender=f"{record.get('fymc', '')}（{record.get('fqr', '')}）",
                received_at=_parse_datetime(record.get("fssj", "")),
                body_text=_build_body(record),
                has_attachments=bool(attachments_meta),
                attachments_meta=attachments_meta,
            )
            new_count += 1

            # 触发附件下载
            if attachments_meta:
                self._download_attachments(attachments_meta, sdbh)

        return new_count

    def _download_attachments(self, meta: list[dict[str, Any]], sdbh: str) -> None:
        """下载文书附件到临时目录。"""
        from django.conf import settings

        save_dir = Path(settings.MEDIA_ROOT) / "message_hub" / "court_inbox" / sdbh
        save_dir.mkdir(parents=True, exist_ok=True)

        for att in meta:
            wjlj = att.get("wjlj", "")
            if not wjlj:
                continue
            filename = att.get("filename", "unknown.pdf")
            save_path = save_dir / filename
            try:
                with httpx.Client(timeout=60.0) as client:
                    resp = client.get(wjlj)
                    resp.raise_for_status()
                    save_path.write_bytes(resp.content)
                att["size"] = len(resp.content)
                att["local_path"] = str(save_path)
                logger.info("下载成功: %s → %s", filename, save_path)
            except Exception as e:
                logger.warning("下载失败 %s: %s", filename, e)

    def download_attachment(
        self, source: MessageSource, message_id: str, part_index: int
    ) -> tuple[bytes, str, str]:
        """按需下载单个附件（Admin 预览/下载用）。"""
        msg = InboxMessage.objects.get(source=source, message_id=message_id)
        meta_list = msg.attachments_meta or []
        for att in meta_list:
            if att.get("part_index") == part_index:
                # 优先读本地缓存
                local_path = att.get("local_path")
                if local_path and Path(local_path).exists():
                    content = Path(local_path).read_bytes()
                    return content, att["filename"], att.get("content_type", "application/octet-stream")
                # 回源下载
                wjlj = att.get("wjlj", "")
                if not wjlj:
                    raise ValueError(f"附件无下载链接: part_index={part_index}")
                with httpx.Client(timeout=60.0) as client:
                    resp = client.get(wjlj)
                    resp.raise_for_status()
                return resp.content, att["filename"], att.get("content_type", "application/octet-stream")
        raise ValueError(f"未找到 part_index={part_index} 的附件")


def _mark_success(source: MessageSource) -> None:
    source.last_sync_at = timezone.now()
    source.last_sync_status = SyncStatus.SUCCESS
    source.last_sync_error = ""
    source.save(update_fields=["last_sync_at", "last_sync_status", "last_sync_error"])


def _mark_failed(source: MessageSource, error: str) -> None:
    source.last_sync_at = timezone.now()
    source.last_sync_status = SyncStatus.FAILED
    source.last_sync_error = error[:1000]
    source.save(update_fields=["last_sync_at", "last_sync_status", "last_sync_error"])
