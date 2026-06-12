"""
一张网纯 HTTP 逆向登录服务

流程：
    1. GET  /api/v1/publicKey  → SM2 公钥
    2. GET  /api/v1/captcha    → {jpg: base64, id: captchaId}
    3. ddddocr 识别验证码
    4. SM2(password, publicKey, C1C3C2)  — 使用 gmssl 实现（与前端加密模式一致）
    5. POST /api/v1/login      → {token, userId, username}
"""

from __future__ import annotations

import base64
import logging
from typing import Any

import httpx
from gmssl import sm2

logger = logging.getLogger("apps.automation")

_API_BASE = "https://zxfw.court.gov.cn/yzw/yzw-zxfw-yhfw"

def _normalize_public_key(public_key_hex: str) -> str:  # pragma: no cover
    """规范化 SM2 公钥，兼容 04 前缀。"""
    key = public_key_hex.strip().lower()
    if key.startswith("04") and len(key) == 130:
        return key[2:]
    if len(key) == 128:
        return key
    raise ValueError(f"公钥格式不正确，长度={len(key)}")

def _sm2_encrypt(plain: str, public_key_hex: str) -> str:  # pragma: no cover
    """SM2 加密（C1C3C2），使用 gmssl，避免依赖 Node.js 模块。"""
    normalized_key = _normalize_public_key(public_key_hex)
    try:
        sm2_cipher = sm2.CryptSM2(public_key=normalized_key, private_key="", mode=1)
    except TypeError:
        sm2_cipher = sm2.CryptSM2(public_key=normalized_key, private_key="")
    encrypted = sm2_cipher.encrypt(plain.encode("utf-8"))
    if isinstance(encrypted, bytes):
        ciphertext = encrypted.hex()
    elif isinstance(encrypted, str):
        ciphertext = encrypted
    else:
        raise TypeError(f"SM2 加密返回未知类型: {type(encrypted)}")
    if not ciphertext:
        raise ValueError("SM2 加密结果为空")
    return ciphertext

class CourtZxfwHttpLoginService:  # pragma: no cover
    """纯 HTTP 逆向登录，不依赖 Playwright"""

    def __init__(  # pragma: no cover
        self,
        captcha_recognizer: Any | None = None,
        timeout: float = 15.0,
    ) -> None:
        self._timeout = timeout
        if captcha_recognizer is None:
            from apps.automation.services.scraper.core.captcha_recognizer import get_captcha_recognizer

            self._recognizer = get_captcha_recognizer()
        else:
            self._recognizer = captcha_recognizer

    def _build_client(self) -> httpx.Client:  # pragma: no cover
        return httpx.Client(
            timeout=self._timeout,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/146.0.0.0 Safari/537.36"
                ),
                "Referer": "https://zxfw.court.gov.cn/zxfw/",
                "Origin": "https://zxfw.court.gov.cn",
            },
            follow_redirects=True,
        )

    def _get_public_key(self, client: httpx.Client) -> str:  # pragma: no cover
        resp = client.get(f"{_API_BASE}/api/v1/publicKey")
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 200:
            raise ValueError(f"获取公钥失败: {data.get('message')}")
        return str(data["data"])

    def _get_captcha(self, client: httpx.Client) -> tuple[str, str]:  # pragma: no cover
        """返回 (captcha_id, captcha_base64_jpg)"""
        resp = client.get(f"{_API_BASE}/api/v1/captcha")
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 200:
            raise ValueError(f"获取验证码失败: {data.get('message')}")
        captcha_data = data["data"]
        return str(captcha_data["id"]), str(captcha_data["jpg"])

    def _recognize_captcha(self, jpg_base64: str) -> str | None:  # pragma: no cover
        """base64 jpg → OCR 识别文本"""
        # 去掉 data:image/jpeg;base64, 前缀
        raw = jpg_base64.split(",", 1)[-1]
        image_bytes = base64.b64decode(raw)
        return self._recognizer.recognize(image_bytes)

    def _do_login(  # pragma: no cover
        self,
        client: httpx.Client,
        *,
        login: str,
        encrypted_pass: str,
        yzm: str,
        captcha_id: str,
        login_type: str,
    ) -> dict[str, Any]:
        resp = client.post(
            f"{_API_BASE}/api/v1/login",
            json={
                "login": login,
                "pass": encrypted_pass,
                "yzm": yzm,
                "id": captcha_id,
                "type": login_type,
            },
        )
        resp.raise_for_status()
        return dict(resp.json())

    def login(  # pragma: no cover
        self,
        account: str,
        password: str,
        login_type: str = "gryh",
        max_retries: int = 3,
    ) -> dict[str, Any]:
        """
        纯 HTTP 登录

        Returns:
            {"success": True, "token": ..., "userId": ..., "username": ..., "data": ...}
        """
        with self._build_client() as client:
            public_key = self._get_public_key(client)
            logger.info("获取公钥成功: %s...%s", public_key[:10], public_key[-6:])
            encrypted_pass = _sm2_encrypt(password, public_key)

            for attempt in range(1, max_retries + 1):
                captcha_id, captcha_jpg = self._get_captcha(client)
                yzm = self._recognize_captcha(captcha_jpg)
                if not yzm:
                    logger.warning("验证码识别失败（第 %d 次）", attempt)
                    continue

                logger.info("验证码识别: %s（第 %d 次）", yzm, attempt)
                result = self._do_login(
                    client,
                    login=account,
                    encrypted_pass=encrypted_pass,
                    yzm=yzm,
                    captcha_id=captcha_id,
                    login_type=login_type,
                )
                if result.get("code") == 200:
                    login_data = result.get("data", {})
                    token = login_data.get("token") if isinstance(login_data, dict) else None
                    logger.info("纯逆向登录成功! token=%s...", str(token)[:20] if token else "N/A")
                    return {
                        "success": True,
                        "token": token,
                        "userId": login_data.get("userId") if isinstance(login_data, dict) else None,
                        "username": login_data.get("username") if isinstance(login_data, dict) else None,
                        "data": login_data,
                    }

                msg = result.get("message", "未知错误")
                logger.warning("登录失败（第 %d 次）: %s", attempt, msg)

        return {"success": False, "message": f"登录失败，已重试 {max_retries} 次"}

    def fetch_baoquan_token(  # pragma: no cover
        self,
        account: str,
        password: str,
        login_type: str = "gryh",
        max_retries: int = 3,
    ) -> dict[str, Any]:
        """
        纯 HTTP 获取保全系统 HS512 Token（一步到位）

        流程：登录一张网 → oauth code → 保全 getauthorization → HS512 token

        Returns:
            {"success": True, "token": "eyJhbGciOiJIUzUxMiJ9...", "zxfw_token": "..."}
        """
        # 1. 登录一张网
        login_result = self.login(account, password, login_type=login_type, max_retries=max_retries)
        if not login_result.get("success"):
            return login_result

        zxfw_token = login_result["token"]

        with self._build_client() as client:
            client.headers["Authorization"] = zxfw_token

            # 2. 获取 oauth code
            resp = client.post(f"{_API_BASE}/api/v1/oauth/code")
            resp.raise_for_status()
            code_data = resp.json()
            if code_data.get("code") != 200:
                return {"success": False, "message": f"获取 oauth code 失败: {code_data.get('message')}"}
            oauth_code = code_data["data"]
            logger.info("获取 oauth code 成功: %s", oauth_code)

            # 3. 用 code 换保全 HS512 token
            resp2 = client.get(
                "https://baoquan.court.gov.cn/wsbq/account/api/account/getauthorization",
                params={"code": oauth_code, "type": "yzw", "state": "200"},
            )
            resp2.raise_for_status()
            bq_data = resp2.json()
            if bq_data.get("code") != 200 or not bq_data.get("data"):
                return {"success": False, "message": f"保全 token 获取失败: {bq_data.get('message')}"}

            bq_token = bq_data["data"].get("token", "")
            logger.info("保全 HS512 token 获取成功: %s...", bq_token[:30] if bq_token else "N/A")

        return {"success": True, "token": bq_token, "zxfw_token": zxfw_token}
