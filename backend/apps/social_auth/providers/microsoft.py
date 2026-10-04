"""微软账号登录 Provider（Microsoft Entra ID）

标准 OAuth 2.0 / OIDC 授权码流程，整页跳转授权，与 Google Provider 同构：
前端点按钮 → 跳 Entra 授权页 → Entra 302 打回后端 ``redirect_uri`` →
后端用 code 换 token、取 userinfo → 建 TempAuth 回前端换 JWT。

对本地部署的关键政策（Microsoft Learn「Redirect URI (reply URL) best practices」
原文，2026-06 更新版核实）：

1. ``http://localhost`` 是官方明确允许的回环例外（"HTTP ... supported only for
   localhost URIs"，示例表里 ``http://localhost`` 标注 Valid），且遵循 RFC 8252
   §8.3/7.3——**匹配时忽略端口**（``http://localhost:1234`` 与 ``:8080`` 等价），
   本地重启换端口无需改登记。
2. 登记时用 ``http://localhost/<path>``（Azure 门户 UI 可直接保存）；官方推荐
   回环地址用 ``127.0.0.1`` 字面量，但门户 UI 不允许添加 http scheme 的
   127.0.0.1（须改 application manifest），故默认值用 localhost。
3. tenant 固定 ``common``：同时接受个人微软账号（Outlook/Hotmail）与工作/学校
   账号，律所律师两类都可能用。将来若要限定单一租户，再给 SocialAuthProvider
   加字段，不做 scope 之类的隐式约定。

与 Google 的实现差异（都是接口约定，不是设计差异）：

1. 授权/令牌端点带租户段 ``/{tenant}/oauth2/v2.0/``。
2. userinfo 走 Microsoft Graph 的 OIDC 端点（``graph.microsoft.com/oidc/userinfo``），
   身份唯一键取 ``sub``（Entra 按应用分配的稳定标识，与 Google ``sub`` 同语义；
   不用 email——邮箱可换可注销）。
3. scope 必须以 ``openid`` 开头（OIDC），``profile``/``email`` 取展示信息；
   Graph 的用户头像在 ``picture`` 字段（URL）。
"""

from __future__ import annotations

import logging
from urllib.parse import quote, urlencode

import httpx

from . import ProviderRegistry
from .base import AuthorizationRequest, LoginMode, SocialProfile, SocialProvider, TokenResponse

logger = logging.getLogger(__name__)

_TIMEOUT = 10

# OIDC 最小集：openid 为必填标识，profile 取姓名，email 取邮箱展示
_DEFAULT_SCOPE = "openid profile email"

# 授权/令牌端点的租户段：common = 个人账号 + 任意组织账号
_TENANT = "common"


@ProviderRegistry.register("microsoft")
class MicrosoftProvider(SocialProvider):  # pragma: no cover
    """Microsoft — OAuth 2.0 / OIDC 授权码流程（整页跳转授权）"""

    login_mode = LoginMode.REDIRECT
    ENDPOINTS = {
        "authorize": f"https://login.microsoftonline.com/{_TENANT}/oauth2/v2.0/authorize",
        "token": f"https://login.microsoftonline.com/{_TENANT}/oauth2/v2.0/token",
        "userinfo": "https://graph.microsoft.com/oidc/userinfo",
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
            # 回调时必须原样带回的对照参数（Entra 强制要求与 token 请求一致）
            "response_mode": "query",
        }
        # quote_via=quote：空格编码为 %20 而非 +，避免中间层对 + 的处理差异
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
        # Entra 按 RFC 6749 返回 {"error": "...", "error_description": "..."}
        if resp.status_code >= 400 or "error" in data:
            logger.warning("Microsoft token exchange failed: %s %s", resp.status_code, data)
            raise ValueError(f"微软授权失败: {data.get('error_description') or data.get('error') or 'unknown'}")
        return TokenResponse(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in"),
            raw=data,
        )

    def _parse_profile(self, resp: httpx.Response) -> SocialProfile:  # pragma: no cover
        if resp.status_code >= 400:
            logger.warning("Microsoft get profile failed: %s %s", resp.status_code, resp.text[:200])
            raise ValueError("获取微软用户信息失败")

        info = resp.json()
        # sub 是 Entra 按应用分配的稳定唯一标识；不用 email（可换、可注销）
        provider_uid = info.get("sub") or ""
        if not provider_uid:
            raise ValueError("微软用户信息缺少 sub")

        return SocialProfile(
            provider="microsoft",
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
