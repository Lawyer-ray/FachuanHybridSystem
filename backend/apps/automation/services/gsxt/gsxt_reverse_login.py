"""国家企业信用信息公示系统 — 纯 HTTP 逆向登录服务。

无需浏览器，通过 httpx 直接发送请求完成登录。
RSA 加密账号密码，验证码部分预留打码平台接口。

本文件为可插拔模块：
- 存在时，系统自动使用 HTTP 逆向登录（无需 Chrome）
- 删除后，系统回退到 Playwright 手动验证码模式
"""

from __future__ import annotations

import abc
import logging
import uuid
from base64 import b64encode
from typing import Any

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding

logger = logging.getLogger("apps.automation")

# ── 常量 ──────────────────────────────────────────────

GSXT_BASE = "https://shiming.gsxt.gov.cn"
LOGIN_API = f"{GSXT_BASE}/socialuser-use-login-request.html"
CAPTCHA_ID = "b608ae7850d2e730b89b02a384d6b9cc"
GEETEST_LOAD_URL = "https://gcaptcha4.geetest.com/load"

RSA_PUBLIC_KEY_PEM = (
    "-----BEGIN PUBLIC KEY-----\n"
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEArqeSZx1T1/54PuJA29Km"
    "8eK/z0a5z9wrF4TjC3r6PjsVX9f9HRXy7TX1MTFkPJMI3BU/Yb/48IEn56Aftws"
    "AW3cDwPoSu9rvRdxf3tXcwtktbrTGuQHvvm82BAXN+04MQB+gy0MbXgNIIW6BZsD"
    "nI1FbV2fEx/ih0mhMG9FvHSB30Z/cUweklGYLjj5kMJ0C7wUNtM5vHXlfHGci079"
    "PuSmHrqrszfXZi0KWmahmRgZiViy6Q9lXqYnvTg4zvcWtSqEaxHtZ/DfG83ufxJP"
    "0AD6dLHFemTlZ83tMNm4IhFFeDmX5GQ9RVWKYwwDtIoHLtzyrzE4TUKmAA7eUo94"
    "1zQIDAQAB\n"
    "-----END PUBLIC KEY-----"
)

_rsa_key = serialization.load_pem_public_key(RSA_PUBLIC_KEY_PEM.encode())


# ── RSA 加密 ─────────────────────────────────────────


def rsa_encrypt(plain: str) -> str:
    """用 RSA 公钥加密字符串，返回 Base64 编码结果（与 JSEncrypt 兼容）。"""
    ct = _rsa_key.encrypt(plain.encode(), asym_padding.PKCS1v15())
    return b64encode(ct).decode()


# ── 打码平台抽象接口 ─────────────────────────────────


class CaptchaSolver(abc.ABC):
    """验证码求解器抽象基类。实现此接口即可接入任意打码平台。"""

    @abc.abstractmethod
    def solve_geetest_v4(self, captcha_id: str, challenge: str) -> dict[str, str]:
        """
        求解极验 v4 验证码。

        Args:
            captcha_id: 极验 captcha_id。
            challenge: 本次验证的 challenge UUID。

        Returns:
            包含以下 key 的 dict:
            - lot_number
            - captcha_output
            - pass_token
            - gen_time
        """
        ...


class NotImplementedSolver(CaptchaSolver):
    """占位求解器，提示用户需要接入打码平台。"""

    def solve_geetest_v4(self, captcha_id: str, challenge: str) -> dict[str, str]:
        raise NotImplementedError(
            "请实现 CaptchaSolver 接口并接入打码平台（如 rrocr / 2captcha / 超级鹰）。"
            "参考: gsxt_reverse_login.py 中的 CaptchaSolver 抽象类。"
        )


# ── 全局求解器（可替换） ─────────────────────────────

_solver: CaptchaSolver = NotImplementedSolver()


def set_captcha_solver(solver: CaptchaSolver) -> None:
    """注册自定义验证码求解器。"""
    global _solver
    _solver = solver


# ── HTTP 逆向登录 ────────────────────────────────────


def reverse_login(account: str, password: str) -> dict[str, Any]:
    """
    纯 HTTP 逆向登录国家企业信用信息公示系统。

    Args:
        account: 手机号或身份证号。
        password: 明文密码。

    Returns:
        登录响应 JSON: {"value": "1"/"0"/"2", "message": "..."}

    Raises:
        NotImplementedError: 未配置打码平台。
        httpx.HTTPError: 网络请求失败。
        ValueError: 登录失败。
    """
    challenge = str(uuid.uuid4())

    # 1. 求解验证码
    logger.info("开始求解极验验证码, captcha_id=%s", CAPTCHA_ID)
    captcha_result = _solver.solve_geetest_v4(CAPTCHA_ID, challenge)
    logger.info("验证码求解完成")

    # 2. RSA 加密
    un = rsa_encrypt(account)
    gp = rsa_encrypt(password)

    # 3. 发送登录请求
    data = {
        "un": un,
        "gp": gp,
        "lot_number": captcha_result["lot_number"],
        "captcha_output": captcha_result["captcha_output"],
        "pass_token": captcha_result["pass_token"],
        "gen_time": captcha_result["gen_time"],
        "captchaId": CAPTCHA_ID,
    }

    with httpx.Client(
        base_url=GSXT_BASE,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": f"{GSXT_BASE}/socialuser-use-rllogin.html",
            "Origin": GSXT_BASE,
        },
        follow_redirects=True,
        timeout=30,
    ) as client:
        # 先访问登录页获取 cookie
        client.get("/socialuser-use-rllogin.html")

        resp = client.post("/socialuser-use-login-request.html", data=data)
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()

    value = result.get("value")
    if value == "1":
        logger.info("逆向登录成功")
    elif value == "0":
        logger.warning("逆向登录失败: %s", result.get("message"))
        raise ValueError(result.get("message", "登录失败"))
    elif value == "2":
        logger.warning("账号未实名认证")
        raise ValueError("请先完成实名认证")

    return result
