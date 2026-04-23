"""znszj 外部 API 客户端实现。

认证流程：
1. POST gdzqfy.gov.cn/api/utils/getscwsurl → signatureCode
2. POST znszj-touch/api/v1/pcqsz/authentication → token + mac
3. POST znszj-touch/touch/getCodeByMac → sbbs

转换流程：
1. POST uploadOriginQsz（仅 mac）→ 提取文本
2. POST text2model（token + mac）→ 结构化数据
3. POST saveAndGetDownloadUrl（token + mac）→ 下载链接
4. GET download/docx（token + mac）→ docx 字节
"""

from __future__ import annotations

import logging
from typing import cast
from urllib.parse import parse_qs, urlparse

import httpx

from apps.doc_convert.exceptions import ZnszjInvalidResponseError, ZnszjUnavailableError

logger = logging.getLogger(__name__)

GDZQFY_URL = "https://www.gdzqfy.gov.cn/api/utils/getscwsurl"
ZNSZJ_BASE = "https://wxfxpg.susong51.com/znszj-touch"
TIMEOUT = 60


class ZnszjClient:
    """znszj 要素式转换客户端。"""

    def convert_document(
        self,
        *,
        file_content: bytes,
        filename: str,
        mbid: str,
    ) -> bytes:
        """执行完整的 znszj 转换流程，返回 docx 字节。"""
        try:
            auth = self._authenticate()
        except ZnszjUnavailableError:
            raise
        except Exception as exc:
            logger.exception("znszj 认证失败", extra={"mbid": mbid})
            raise ZnszjUnavailableError(detail=str(exc)) from exc

        try:
            return self._run_conversion(
                file_content=file_content,
                filename=filename,
                mbid=mbid,
                token=auth["token"],
                mac=auth["mac"],
                sbbs=auth["sbbs"],
            )
        except (ZnszjUnavailableError, ZnszjInvalidResponseError):
            raise
        except Exception as exc:
            logger.exception("znszj 转换失败", extra={"mbid": mbid, "doc_filename": filename})
            raise ZnszjUnavailableError(detail=str(exc)) from exc

    def _authenticate(self) -> dict[str, str]:
        """完成三步认证，返回 token、mac、sbbs。"""
        with httpx.Client(timeout=TIMEOUT, proxy=None) as client:
            # Step 1: 获取 signatureCode
            r1 = client.post(GDZQFY_URL)
            r1.raise_for_status()
            data1 = r1.json()
            if data1.get("code") != "200":
                raise ZnszjUnavailableError(detail=f"getscwsurl 失败: {data1}")
            auth_url: str = data1["data"]
            signature_code = auth_url.split("signatureCode=")[1]

            # Step 2: 换取 token + mac
            r2 = client.post(
                f"{ZNSZJ_BASE}/api/v1/pcqsz/authentication",
                json={"signatureCode": signature_code, "sessionId": "", "mbid": ""},
            )
            r2.raise_for_status()
            data2 = r2.json()
            if not data2.get("success"):
                raise ZnszjUnavailableError(detail=f"authentication 失败: {data2}")
            mac: str = data2["data"]["mac"]
            token: str = data2["data"]["token"]

            # Step 3: 换取 sbbs
            r3 = client.post(
                f"{ZNSZJ_BASE}/touch/getCodeByMac",
                params={"mac": mac},
            )
            r3.raise_for_status()
            data3 = r3.json()
            if not data3.get("success"):
                raise ZnszjUnavailableError(detail=f"getCodeByMac 失败: {data3}")
            sbbs: str = data3["code"]

        logger.info("znszj 认证成功")
        return {"token": token, "mac": mac, "sbbs": sbbs}

    def _run_conversion(
        self,
        *,
        file_content: bytes,
        filename: str,
        mbid: str,
        token: str,
        mac: str,
        sbbs: str,
    ) -> bytes:
        """执行上传→转写→保存→下载流程。"""
        headers = {"token": token, "mac": mac}

        with httpx.Client(timeout=TIMEOUT, proxy=None) as client:
            # Step 1: 上传传统文书（只需 mac）
            r1 = client.post(
                f"{ZNSZJ_BASE}/api/v1/tableTemplate/uploadOriginQsz",
                headers={"mac": mac},
                files={"file": (filename, file_content, "application/octet-stream")},
            )
            r1.raise_for_status()
            d1 = r1.json()
            if not d1.get("success"):
                raise ZnszjInvalidResponseError(detail=f"uploadOriginQsz 失败: {d1.get('message', d1)}")
            extracted_text: str = d1["data"]
            logger.info("znszj 上传成功", extra={"mbid": mbid, "doc_filename": filename})

            # Step 2: 智能转写
            r2 = client.post(
                f"{ZNSZJ_BASE}/api/v1/tableTemplate/text2model",
                headers=headers,
                json={"text": extracted_text, "mbid": mbid},
            )
            r2.raise_for_status()
            d2 = r2.json()
            if not d2.get("success"):
                raise ZnszjInvalidResponseError(detail=f"text2model 失败: {d2.get('message', d2)}")
            structured_data: dict[str, object] = d2["data"]
            logger.info("znszj 转写成功", extra={"mbid": mbid})

            # Step 3: 保存并获取下载链接
            r3 = client.post(
                f"{ZNSZJ_BASE}/api/v1/tableTemplate/saveAndGetDownloadUrl",
                headers=headers,
                json={"mbid": mbid, "data": structured_data, "sbbs": sbbs},
            )
            r3.raise_for_status()
            d3 = r3.json()
            if not d3.get("success"):
                raise ZnszjInvalidResponseError(detail=f"saveAndGetDownloadUrl 失败: {d3.get('message', d3)}")
            download_rel: str = d3["data"]

            # Step 4: 下载文书
            parsed = urlparse(download_rel)
            params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            r4 = client.get(
                f"{ZNSZJ_BASE}/api/v1/tableTemplate/download/docx",
                headers=headers,
                params=params,
            )
            r4.raise_for_status()
            logger.info("znszj 下载成功", extra={"mbid": mbid})
            return r4.content
