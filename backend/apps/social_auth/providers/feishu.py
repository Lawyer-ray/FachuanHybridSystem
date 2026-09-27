"""飞书扫码登录 Provider

接入方式为飞书「二维码 SDK」：前端用 JS SDK 把二维码渲染在登录页内，
扫码成功后 SDK 回传一次性 ``tmp_code``，前端把它拼到授权页 URL 上完成跳转，
飞书再以 302 打回 ``redirect_uri`` 并带上 ``code``。

接口地址分散在三个域名下，不能假设只有一个 BASE_URL：
- 授权页走**旧版**端点 ``passport.feishu.cn``，因为二维码 SDK 的 ``goto``
  只支持旧流程（官方文档明确写了 "The new login process is not supported yet"）。
- 换取令牌走新版 ``accounts.feishu.cn/oauth/v3/token``（v2 端点已废弃，
  v3 修正了 PKCE 校验行为）。
- 用户信息与 app_access_token 走 ``open.feishu.cn``。

用户唯一键用 ``union_id`` 而非 ``open_id``：union_id 在同一开发者所有应用间一致，
将来换应用或接入第二个飞书应用不会重复建号。
"""

from __future__ import annotations

import logging

import httpx

from . import ProviderRegistry
from .base import AuthorizationRequest, LoginMode, SocialProfile, SocialProvider, TokenResponse

logger = logging.getLogger(__name__)

_TIMEOUT = 10


@ProviderRegistry.register("feishu")
class FeishuProvider(SocialProvider):  # pragma: no cover
    """飞书自建应用 — 二维码扫码登录"""

    login_mode = LoginMode.EMBEDDED_QR
    ENDPOINTS = {
        # 二维码 SDK 的 goto 专用（旧版流程）
        "authorize": "https://passport.feishu.cn/suite/passport/oauth/authorize",
        # v3 令牌端点
        "token": "https://accounts.feishu.cn/oauth/v3/token",
        "user_info": "https://open.feishu.cn/open-apis/authen/v1/user_info",
        "app_access_token": "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
    }

    def get_authorization_url(self, request: AuthorizationRequest) -> str:  # pragma: no cover
        scope = self.config.extra.get("scope") or "contact:user.base:readonly"
        return (
            f"{self.endpoint('authorize')}"
            f"?client_id={self.config.client_id}"
            f"&redirect_uri={request.redirect_uri}"
            "&response_type=code"
            f"&scope={scope}"
            f"&state={request.state}"
        )

    def _get_app_access_token(self) -> str:  # pragma: no cover
        """换取 app_access_token。

        登录流程本身不需要它（用户信息用 user_access_token 就够），
        保留供将来以应用身份调用 OpenAPI 时使用。
        """
        resp = httpx.post(
            self.endpoint("app_access_token"),
            json={"app_id": self.config.client_id, "app_secret": self.config.client_secret},
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=_TIMEOUT,
        )
        data = resp.json()
        # 飞书把业务错误放在 HTTP 200 里，必须显式检查
        self._check_api_error(data, code_key="code", msg_key="msg")
        return str(data["app_access_token"])

    def exchange_code(self, code: str, request: AuthorizationRequest) -> TokenResponse:  # pragma: no cover
        resp = httpx.post(
            self.endpoint("token"),
            json={
                "grant_type": "authorization_code",
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
                "code": code,
                "redirect_uri": request.redirect_uri,
            },
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=_TIMEOUT,
        )
        data = resp.json()
        # v3 令牌端点按 RFC 6749 返回 {"error":"invalid_grant","error_description":"..."}
        if resp.status_code >= 400 or "error" in data:
            logger.warning("Feishu token exchange failed: %s %s", resp.status_code, data)
            raise ValueError(f"飞书授权失败: {data.get('error_description') or data.get('error') or 'unknown'}")
        return TokenResponse(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in"),
            raw=data,
        )

    def get_profile(self, token_response: TokenResponse) -> SocialProfile:  # pragma: no cover
        resp = httpx.get(
            self.endpoint("user_info"),
            headers={
                "Authorization": f"Bearer {token_response.access_token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            timeout=_TIMEOUT,
        )
        data = resp.json()
        self._check_api_error(data, code_key="code", msg_key="msg")
        info = data.get("data") or {}
        # union_id 跨应用稳定，作为账号唯一键
        provider_uid = info.get("union_id") or info.get("open_id") or ""
        if not provider_uid:
            raise ValueError("飞书用户信息缺少 union_id/open_id")
        return SocialProfile(
            provider="feishu",
            provider_user_id=str(provider_uid),
            email=info.get("email"),
            display_name=info.get("name"),
            avatar_url=info.get("avatar_url"),
            raw_data=info,
        )

    async def aexchange_code(self, code: str, request: AuthorizationRequest) -> TokenResponse:  # pragma: no cover
        """异步版本。"""
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                self.endpoint("token"),
                json={
                    "grant_type": "authorization_code",
                    "client_id": self.config.client_id,
                    "client_secret": self.config.client_secret,
                    "code": code,
                    "redirect_uri": request.redirect_uri,
                },
                headers={"Content-Type": "application/json; charset=utf-8"},
            )
        data = resp.json()
        if resp.status_code >= 400 or "error" in data:
            logger.warning("Feishu token exchange failed: %s %s", resp.status_code, data)
            raise ValueError(f"飞书授权失败: {data.get('error_description') or data.get('error') or 'unknown'}")
        return TokenResponse(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in"),
            raw=data,
        )

    async def aget_profile(self, token_response: TokenResponse) -> SocialProfile:  # pragma: no cover
        """异步版本。"""
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                self.endpoint("user_info"),
                headers={
                    "Authorization": f"Bearer {token_response.access_token}",
                    "Content-Type": "application/json; charset=utf-8",
                },
            )
        data = resp.json()
        self._check_api_error(data, code_key="code", msg_key="msg")
        info = data.get("data") or {}
        provider_uid = info.get("union_id") or info.get("open_id") or ""
        if not provider_uid:
            raise ValueError("飞书用户信息缺少 union_id/open_id")
        return SocialProfile(
            provider="feishu",
            provider_user_id=str(provider_uid),
            email=info.get("email"),
            display_name=info.get("name"),
            avatar_url=info.get("avatar_url"),
            raw_data=info,
        )

    def get_client_config(self) -> dict[str, str]:
        """返回前端内嵌二维码所需信息（不含 secret）。"""
        return {
            "app_id": self.config.client_id,
            "authorize_url": self.endpoint("authorize"),
            "scope": self.config.extra.get("scope") or "contact:user.base:readonly",
            # 二维码容器尺寸，SDK 本身固定渲染 250x250
            "width": "300",
            "height": "300",
        }
