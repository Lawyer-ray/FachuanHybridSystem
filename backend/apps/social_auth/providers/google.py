"""Google 登录 Provider

标准 OAuth 2.0 授权码流程（OpenID Connect），整页跳转授权：
前端点按钮 → 跳 Google 授权页 → Google 302 打回后端 ``redirect_uri`` →
后端用 code 换 token、取 userinfo → 建 TempAuth 回前端换 JWT。

与飞书 / 微信的实现差异都是**接口约定**不同，不是设计差异：

1. token 端点要求 ``application/x-www-form-urlencoded``，必须走 ``data=``
   （飞书用 JSON body，微信用 GET query 参数）。
2. ``scope`` 是空格分隔的多值 ``openid email profile``，拼进 URL 前必须编码 ——
   裸空格会让授权页直接报错。
3. 身份唯一键取 ``sub``。Google 明文警告不得用 ``email`` 当唯一标识：邮箱可变，
   且 Workspace 域内可被管理员回收后重新分配给他人。

刻意不传 ``access_type=offline`` / ``prompt=consent``：本系统只要一次性的身份断言，
不需要 refresh token，传了会多要权限并强制每次弹同意页。

端点值对照 Google 发现文档
``https://accounts.google.com/.well-known/openid-configuration``（官方要求不硬编码，
但这三个地址极其稳定，写死可少一次网络依赖与失败点；Google 改版时对照该文档核对即可）。
"""

from __future__ import annotations

import logging
from urllib.parse import quote, urlencode

import httpx

from . import ProviderRegistry
from .base import AuthorizationRequest, LoginMode, SocialProfile, SocialProvider, TokenResponse

logger = logging.getLogger(__name__)

_TIMEOUT = 10

# 必须以 openid 开头；profile 提供 name/picture，email 提供 email/email_verified
_DEFAULT_SCOPE = "openid email profile"


@ProviderRegistry.register("google")
class GoogleProvider(SocialProvider):  # pragma: no cover
    """Google — OAuth 2.0 网络服务器流程（整页跳转授权）"""

    login_mode = LoginMode.REDIRECT
    ENDPOINTS = {
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "userinfo": "https://openidconnect.googleapis.com/v1/userinfo",
    }

    def _scope(self) -> str:  # pragma: no cover
        return self.config.extra.get("scope") or _DEFAULT_SCOPE

    def get_authorization_url(self, request: AuthorizationRequest) -> str:  # pragma: no cover
        params = {
            "client_id": self.config.client_id,
            "redirect_uri": request.redirect_uri,
            "response_type": "code",
            "scope": self._scope(),
            "state": request.state,
        }
        # quote_via=quote：空格编码为 %20 而非 +，避免中间层对 + 的处理差异
        # urlencode 默认 safe=''，因此 redirect_uri 里的 / 也会被正确编码
        return f"{self.endpoint('authorize')}?{urlencode(params, quote_via=quote)}"

    def _token_request_data(self, code: str, request: AuthorizationRequest) -> dict[str, str]:  # pragma: no cover
        return {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "redirect_uri": request.redirect_uri,
        }

    def _parse_token_response(self, resp: httpx.Response) -> TokenResponse:  # pragma: no cover
        data = resp.json()
        # Google 按 RFC 6749 返回 {"error": "...", "error_description": "..."}
        if resp.status_code >= 400 or "error" in data:
            logger.warning("Google token exchange failed: %s %s", resp.status_code, data)
            raise ValueError(f"Google 授权失败: {data.get('error_description') or data.get('error') or 'unknown'}")
        return TokenResponse(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in"),
            raw=data,
        )

    def _parse_profile(self, resp: httpx.Response) -> SocialProfile:  # pragma: no cover
        if resp.status_code >= 400:
            logger.warning("Google get profile failed: %s %s", resp.status_code, resp.text[:200])
            raise ValueError("获取 Google 用户信息失败")

        info = resp.json()
        # sub 是 Google 账号的不可变唯一标识；不用 email 作键（可变、域内可被回收再分配）
        provider_uid = info.get("sub") or ""
        if not provider_uid:
            raise ValueError("Google 用户信息缺少 sub")

        return SocialProfile(
            provider="google",
            provider_user_id=str(provider_uid),
            email=info.get("email"),
            display_name=info.get("name"),
            avatar_url=info.get("picture"),
            raw_data=info,
        )

    def exchange_code(self, code: str, request: AuthorizationRequest) -> TokenResponse:  # pragma: no cover
        resp = httpx.post(
            self.endpoint("token"),
            data=self._token_request_data(code, request),
            timeout=_TIMEOUT,
        )
        return self._parse_token_response(resp)

    def get_profile(self, token_response: TokenResponse) -> SocialProfile:  # pragma: no cover
        resp = httpx.get(
            self.endpoint("userinfo"),
            headers={"Authorization": f"Bearer {token_response.access_token}"},
            timeout=_TIMEOUT,
        )
        return self._parse_profile(resp)

    async def aexchange_code(self, code: str, request: AuthorizationRequest) -> TokenResponse:  # pragma: no cover
        """异步版本。Django 侧是 async view，用同步 httpx 会阻塞事件循环。"""
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                self.endpoint("token"),
                data=self._token_request_data(code, request),
            )
        return self._parse_token_response(resp)

    async def aget_profile(self, token_response: TokenResponse) -> SocialProfile:  # pragma: no cover
        """异步版本。"""
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                self.endpoint("userinfo"),
                headers={"Authorization": f"Bearer {token_response.access_token}"},
            )
        return self._parse_profile(resp)
