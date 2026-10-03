"""GitHub 登录 Provider

标准 OAuth 2.0 授权码流程，整页跳转授权，链路与 Google Provider 相同：
前端点按钮 → 跳 GitHub 授权页 → GitHub 302 打回后端 ``redirect_uri`` →
后端用 code 换 token、取用户信息 → 建 TempAuth 回前端换 JWT。

与 Google 的实现差异都是**接口约定**不同，不是设计差异：

1. token 端点必须显式带 ``Accept: application/json``。GitHub 按请求头协商
   响应格式，缺了它会返回 ``access_token=...&scope=...`` 的 urlencoded 纯文本，
   ``resp.json()`` 直接抛解析异常。
2. 身份唯一键取数字 ``id``。``login``（用户名）可以改名，``email`` 可以更换
   或始终私密——拿它们当唯一键会导致改名后登录身份漂移（与 Google 用
   ``sub`` 不用 ``email`` 是同一条原则）。
3. 私密邮箱在 ``/user`` 里是 null，需单独调 ``/user/emails`` 取 primary 邮箱
   （``user:email`` scope）。邮箱只是展示信息：取不到不影响登录，身份判定
   只看 ``id``。
4. 授权 URL 只带 GitHub 文档列出的参数（client_id / redirect_uri / scope /
   state）。GitHub 的 Web 应用流程固定 response_type=code，文档不列该参数，
   传了也无意义，故不拼。

GitHub OAuth App 对本地部署友好：允许 ``http://localhost`` 回调（回环地址
端口可与登记值不同），注册免费、即时生效、无需审核。
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from . import ProviderRegistry
from .base import AuthorizationRequest, LoginMode, SocialProfile, SocialProvider, TokenResponse

logger = logging.getLogger(__name__)

_TIMEOUT = 10

# read:user 取昵称/头像；user:email 允许调 /user/emails 拿私密邮箱
_DEFAULT_SCOPE = "read:user user:email"

# GitHub API 的官方媒体类型；token 端点则必须用 application/json 协商 JSON 响应
_API_ACCEPT = "application/vnd.github+json"
_TOKEN_ACCEPT = "application/json"


@ProviderRegistry.register("github")
class GitHubProvider(SocialProvider):  # pragma: no cover
    """GitHub — OAuth 2.0 网络服务器流程（整页跳转授权）"""

    login_mode = LoginMode.REDIRECT
    ENDPOINTS = {
        "authorize": "https://github.com/login/oauth/authorize",
        "token": "https://github.com/login/oauth/access_token",
        "userinfo": "https://api.github.com/user",
        "emails": "https://api.github.com/user/emails",
    }

    def _scope(self) -> str:  # pragma: no cover
        return self.config.extra.get("scope") or _DEFAULT_SCOPE

    def _token_headers(self) -> dict[str, str]:  # pragma: no cover
        return {"Accept": _TOKEN_ACCEPT}

    def _api_headers(self, token_response: TokenResponse) -> dict[str, str]:  # pragma: no cover
        return {"Accept": _API_ACCEPT, "Authorization": f"Bearer {token_response.access_token}"}

    def get_authorization_url(self, request: AuthorizationRequest) -> str:  # pragma: no cover
        params = {
            "client_id": self.config.client_id,
            "redirect_uri": request.redirect_uri,
            "scope": self._scope(),
            "state": request.state,
        }
        # quote_via=quote：空格编码为 %20 而非 +，scope 里的冒号也一并编码，
        # 避免中间层对 + 的处理差异（与 Google Provider 同一处理）
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
        # GitHub 按 RFC 6749 返回 {"error": "...", "error_description": "..."}
        if resp.status_code >= 400 or "error" in data:
            logger.warning("GitHub token exchange failed: %s %s", resp.status_code, data)
            raise ValueError(f"GitHub 授权失败: {data.get('error_description') or data.get('error') or 'unknown'}")
        return TokenResponse(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in"),
            raw=data,
        )

    @staticmethod
    def _pick_email(info: dict[str, Any], emails_resp: httpx.Response | None) -> str | None:  # pragma: no cover
        """尽力而为地取邮箱：/user/emails 的 primary 优先，取不到回落公开邮箱。

        邮箱不参与身份判定（唯一键是数字 id），所以这里任何失败都只导致
        ``email=None``，绝不影响登录本身。
        """
        if emails_resp is not None and emails_resp.status_code < 400:
            entries = emails_resp.json()
            if isinstance(entries, list):
                primary = next(
                    (str(e["email"]) for e in entries if isinstance(e, dict) and e.get("primary") and e.get("email")),
                    None,
                )
                if primary:
                    return primary
        public_email = info.get("email")
        return public_email if isinstance(public_email, str) else None

    def _parse_profile(
        self, user_resp: httpx.Response, emails_resp: httpx.Response | None
    ) -> SocialProfile:  # pragma: no cover
        if user_resp.status_code >= 400:
            logger.warning("GitHub get profile failed: %s %s", user_resp.status_code, user_resp.text[:200])
            raise ValueError("获取 GitHub 用户信息失败")

        info = user_resp.json()
        # 数字 id 是 GitHub 账号的不可变唯一标识；login 可改名、email 可更换
        provider_uid = info.get("id")
        if provider_uid is None:
            raise ValueError("GitHub 用户信息缺少 id")

        return SocialProfile(
            provider="github",
            provider_user_id=str(provider_uid),
            email=self._pick_email(info, emails_resp),
            display_name=info.get("name") or info.get("login"),
            avatar_url=info.get("avatar_url"),
            raw_data=info,
        )

    def exchange_code(self, code: str, request: AuthorizationRequest) -> TokenResponse:  # pragma: no cover
        resp = httpx.post(
            self.endpoint("token"),
            data=self._token_request_data(code, request),
            headers=self._token_headers(),
            timeout=_TIMEOUT,
        )
        return self._parse_token_response(resp)

    def _fetch_emails(self, headers: dict[str, str]) -> httpx.Response | None:  # pragma: no cover
        """取 /user/emails。失败返回 None（邮箱是展示信息，不阻断登录）。"""
        try:
            return httpx.get(self.endpoint("emails"), headers=headers, timeout=_TIMEOUT)
        except httpx.HTTPError as exc:
            logger.warning("GitHub fetch emails failed: %s", exc)
            return None

    def get_profile(self, token_response: TokenResponse) -> SocialProfile:  # pragma: no cover
        headers = self._api_headers(token_response)
        user_resp = httpx.get(self.endpoint("userinfo"), headers=headers, timeout=_TIMEOUT)
        return self._parse_profile(user_resp, self._fetch_emails(headers))

    async def aexchange_code(self, code: str, request: AuthorizationRequest) -> TokenResponse:  # pragma: no cover
        """异步版本。Django 侧是 async view，用同步 httpx 会阻塞事件循环。"""
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                self.endpoint("token"),
                data=self._token_request_data(code, request),
                headers=self._token_headers(),
            )
        return self._parse_token_response(resp)

    async def aget_profile(self, token_response: TokenResponse) -> SocialProfile:  # pragma: no cover
        """异步版本。邮箱请求失败不阻断登录，捕获后按无邮箱处理。"""
        headers = self._api_headers(token_response)
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            user_resp = await client.get(self.endpoint("userinfo"), headers=headers)
            try:
                emails_resp = await client.get(self.endpoint("emails"), headers=headers)
            except httpx.HTTPError as exc:
                logger.warning("GitHub fetch emails failed: %s", exc)
                emails_resp = None
        return self._parse_profile(user_resp, emails_resp)
