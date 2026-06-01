"""送达地址确认书自动生成与上传。"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import httpx

from .constants import _OSS_BUCKET

logger = logging.getLogger("plugins.court_filing_http")

_CLLX = "11800016-254"
_CLMC = "送达地址确认书"

def _build_address_lines(info: dict[str, Any]) -> list[str]:
    """从地址信息字典组装可读文本行。"""
    lines: list[str] = []
    sjr = str(info.get("sjr") or info.get("sJr") or info.get("sjrmc") or info.get("name") or "").strip()
    lxdh = str(info.get("lxdh") or info.get("lxfs") or info.get("sjhm") or "").strip()
    yzbm = str(info.get("yzbm") or "").strip()
    dz = str(info.get("dzxx") or info.get("xxdz") or info.get("address") or info.get("dwdz") or "").strip()
    dz_mc = str(info.get("dzMc") or info.get("dzmc") or "").strip()

    if sjr:
        lines.append(f"收件人：{sjr}")
    if lxdh:
        lines.append(f"联系电话：{lxdh}")
    if dz_mc and dz:
        full_addr = f"{dz_mc} {dz}"
    elif dz:
        full_addr = dz
    elif dz_mc:
        full_addr = dz_mc
    else:
        full_addr = ""
    if full_addr:
        addr = f"{yzbm} {full_addr}" if yzbm else full_addr
        lines.append(f"送达地址：{addr}")
    elif yzbm:
        lines.append(f"邮编：{yzbm}")

    if not lines:
        for k, v in info.items():
            if v and k not in ("id", "layyid", "fyId", "fyid", "pageNum", "pageSize"):
                lines.append(f"{k}：{v}")
    return lines

class AddressConfirmationMixin:
    """送达地址确认书自动生成与上传。"""

    async def _generate_and_upload_address_confirmation(
        self: Any,
        *,
        layyid: str,
        fyid: str,
    ) -> None:
        try:
            await self._do_generate_and_upload(layyid=layyid, fyid=fyid)
        except Exception:
            logger.warning("送达地址确认书自动生成失败，跳过（不影响主流程）", exc_info=True)

    async def _do_generate_and_upload(
        self: Any,
        *,
        layyid: str,
        fyid: str,
    ) -> None:
        address_info = await self._fetch_address_info()
        if not address_info:
            logger.info("未找到送达地址信息，跳过自动生成送达地址确认书")
            return

        sig_download_url, sig_oss_path = await self._fetch_signature_info()

        signature_img_path: str | None = None
        if sig_download_url:
            try:
                signature_img_path = await self._download_signature_image(sig_download_url)
            except Exception:
                logger.warning("签名图片下载失败，生成无签名的送达地址确认书", exc_info=True)

        pdf_path = self._generate_address_pdf(address_info, signature_img_path)

        try:
            sddzxxId = str(
                address_info.get("bh") or address_info.get("id") or address_info.get("sddzxxId") or ""
            ).strip()
            await self._upload_address_confirmation_pdf(
                layyid=layyid,
                fyid=fyid,
                pdf_path=pdf_path,
                sddzxxId=sddzxxId,
                qmPath=sig_oss_path or "",
            )
        finally:
            Path(pdf_path).unlink(missing_ok=True)
            if signature_img_path:
                Path(signature_img_path).unlink(missing_ok=True)

    async def _fetch_address_info(self: Any) -> dict[str, Any] | None:
        """获取用户级送达地址列表（POST /yzw-zxfw-yhfw/api/v1/grxx/yjsd/list）。"""
        data = await self._post(
            "/yzw-zxfw-yhfw/api/v1/grxx/yjsd/list",
            {"pageNum": 1, "pageSize": 1000},
        )
        if isinstance(data, dict):
            items = data.get("data") or data.get("list") or data.get("rows") or data.get("records") or []
        elif isinstance(data, list):
            items = data
        else:
            items = []
        return items[0] if items else None

    async def _fetch_signature_info(self: Any) -> tuple[str | None, str | None]:
        """获取用户级电子签名，返回 (下载URL, OSS路径)。"""
        data = await self._post(
            "/yzw-zxfw-ajfw/api/v1/dzqm/dzqmList",
            {"pageNum": 1, "limit": 12},
        )
        if isinstance(data, dict):
            items = data.get("data") or data.get("list") or data.get("rows") or data.get("records") or []
        elif isinstance(data, list):
            items = data
        else:
            items = []
        if not items:
            return None, None
        item = items[0]
        download_url = item.get("url") or item.get("qmPath") or item.get("path") or item.get("qmUrl")
        oss_path = item.get("osspath") or item.get("qmPath") or item.get("path")
        return download_url, oss_path

    async def _download_signature_image(self: Any, signature_path: str) -> str:
        """从 OSS 下载签名图片到临时文件。"""
        if signature_path.startswith("http"):
            url = signature_path
        else:
            url = f"{_OSS_BUCKET}/{signature_path.lstrip('/')}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(url)
            r.raise_for_status()
        fd, tmp_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        Path(tmp_path).write_bytes(r.content)
        return tmp_path

    def _generate_address_pdf(
        self: Any,
        address_info: dict[str, Any],
        signature_img_path: str | None,
    ) -> str:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.pdfgen import canvas

        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        font = "STSong-Light"

        fd, pdf_path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)

        c = canvas.Canvas(pdf_path, pagesize=A4)
        w, h = A4

        c.setFont(font, 18)
        c.drawCentredString(w / 2, h - 80, "送达地址确认书")

        c.setFont(font, 12)
        y = h - 140
        for line in _build_address_lines(address_info):
            c.drawString(72, y, line)
            y -= 24

        if signature_img_path:
            sig_y = max(y - 120, 72)
            c.setFont(font, 10)
            c.drawString(72, sig_y + 80, "签名：")
            c.drawImage(
                signature_img_path,
                72,
                sig_y,
                width=200,
                height=80,
                preserveAspectRatio=True,
                anchor="sw",
            )

        c.save()
        return pdf_path

    async def _upload_address_confirmation_pdf(
        self: Any,
        *,
        layyid: str,
        fyid: str,
        pdf_path: str,
        sddzxxId: str,
        qmPath: str,
    ) -> None:
        """签名→OSS→ssclfj/upload 回调注册。"""
        import base64
        import json as _json

        ssryId = ""
        try:
            token = str(self._client.headers.get("Authorization", ""))
            payload_b64 = token.split(".")[1] if "." in token else ""
            if payload_b64:
                padded = payload_b64 + "=" * (-len(payload_b64) % 4)
                claims = _json.loads(base64.urlsafe_b64decode(padded))
                ssryId = str(claims.get("user-id", ""))
        except Exception:
            pass

        ext = Path(pdf_path).suffix
        sig = await self._post(
            "/yzw-zxfw-ajfw/api/v1/file/upload/signature",
            {
                "path": "layy",
                "ext": ext,
                "fydm": fyid,
                "cllx": _CLLX,
            },
        )
        key: str = sig["storeAs"]
        oss_url: str = sig.get("ossPath", _OSS_BUCKET)

        file_bytes = Path(pdf_path).read_bytes()
        form: dict[str, Any] = {
            "key": key,
            "policy": sig["policy"],
            "OSSAccessKeyId": sig["ossaccessKeyId"],
            "success_action_status": "200",
            "Signature": sig["signature"],
            "x-oss-security-token": sig.get("token", ""),
            "Content-Type": "application/pdf",
        }
        async with httpx.AsyncClient(timeout=60.0) as oss_client:
            oss_resp = await oss_client.post(
                oss_url,
                data=form,
                files={"file": (f"{_CLMC}.pdf", file_bytes)},
            )
            oss_resp.raise_for_status()

        slot_id_by_cllx = await self._extract_material_slot_ids(layyid)
        ssclid = slot_id_by_cllx.get(_CLLX)

        await self._post(
            "/yzw-zxfw-lafw/api/v3/layy/ssclfj/upload",
            {
                "id": ssclid or "",
                "layyid": layyid,
                "fyId": fyid,
                "clmc": _CLMC,
                "cllx": _CLLX,
                "ssryId": ssryId,
                "wjs": [],
                "ssclid": ssclid or "",
                "ywlx": "layy",
                "path": "layy",
                "deleteUrl": "/yzw-zxfw-lafw/api/v3/layy/ssclfj/delete",
                "updateUrl": "/yzw-zxfw-lafw/api/v3/layy/ssclfj/update",
                "showImportBtn": True,
                "subTitle": "必传材料",
                "isbx": "1",
                "xh": 5,
                "sfxs": "1",
                "qmPath": qmPath,
                "sddzxxId": sddzxxId,
                "sjhm": "",
                "email": "",
            },
        )
        logger.info("送达地址确认书上传完成: %s", f"{_CLMC}.pdf")
