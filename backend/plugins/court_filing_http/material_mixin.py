from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

import httpx

from .constants import _OSS_BUCKET

logger = logging.getLogger("plugins.court_filing_http")


class MaterialMixin:
    async def _extract_material_slot_ids(self: Any, layyid: str) -> dict[str, str]:
        detail = await self._get(f"/yzw-zxfw-lafw/api/v3/layy/layyxq/{layyid}/0")
        mapping: dict[str, str] = {}
        id_keys = ("ssclid", "ssclId", "id", "clid")
        cllx_keys = ("cllx", "cllxDm", "cllxdm", "cllxId", "cllxid")

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                node_cllx = ""
                for key in cllx_keys:
                    value = node.get(key)
                    if value:
                        node_cllx = str(value).strip()
                        break

                node_id = ""
                for key in id_keys:
                    value = node.get(key)
                    if value:
                        node_id = str(value).strip()
                        break

                if node_cllx and node_id:
                    mapping.setdefault(node_cllx, node_id)

                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(detail)
        logger.info("提取材料槽位映射完成: %d, cllx列表=%s", len(mapping), list(mapping.keys()))
        return mapping

    async def _upload_material(
        self: Any,
        layyid: str,
        fyid: str,
        file_path: str,
        cllx: str,
        clmc: str,
        *,
        ssclid: str | None = None,
        xh: int = 1,
        original_filename: str = "",
    ) -> None:
        ext = Path(file_path).suffix
        sig = await self._post(
            "/yzw-zxfw-ajfw/api/v1/file/upload/signature",
            {
                "path": "layy",
                "ext": ext,
                "fydm": fyid,
                "cllx": cllx,
            },
        )
        key: str = sig["storeAs"]
        oss_url: str = sig.get("ossPath", _OSS_BUCKET)

        fname = original_filename or Path(file_path).name

        with open(file_path, "rb") as f:
            file_bytes = f.read()
        form: dict[str, Any] = {
            "key": key,
            "policy": sig["policy"],
            "OSSAccessKeyId": sig["ossaccessKeyId"],
            "success_action_status": "200",
            "Signature": sig["signature"],
            "x-oss-security-token": sig.get("token", ""),
            "Content-Type": f"application/{ext.lstrip('.')}",
        }
        async with httpx.AsyncClient(timeout=60.0) as oss_client:
            oss_resp = await oss_client.post(
                oss_url,
                data=form,
                files={"file": (fname, file_bytes)},
            )
            oss_resp.raise_for_status()

        await self._post(
            "/yzw-zxfw-lafw/api/v3/layy/ssclfj",
            {
                "wjbh": key,
                "layyid": layyid,
                "fyId": fyid,
                "wjmc": fname,
                "path": key,
                "ssclid": ssclid or uuid.uuid4().hex,
                "cllx": cllx,
                "clmc": clmc,
                "bccl": None,
                "name": fname,
                "extname": ext.lstrip("."),
                "url": f"{oss_url.rstrip('/')}/{key}",
                "xh": int(xh or 1),
            },
        )
        logger.info("材料上传完成: %s", fname)
