from __future__ import annotations

import logging

import httpx

from . import ProviderRegistry
from .base import SocialProfile, SocialProvider, TokenResponse

logger = logging.getLogger(__name__)


@ProviderRegistry.register("wechat")
class WeChatProvider(SocialProvider):  # pragma: no cover
    """微信开放平台 — 网站应用 OAuth2.0 扫码登录"""

    def get_authorization_url(self, state: str) -> str:  # pragma: no cover
        redirect_uri = self.config.extra["redirect_uri"]
        return (
            "https://open.weixin.qq.com/connect/qrconnect"
            f"?appid={self.config.client_id}"
            f"&redirect_uri={redirect_uri}"
            "&response_type=code"
            "&scope=snsapi_login"
            f"&state={state}"
            "#wechat_redirect"
        )

    def exchange_code(self, code: str, state: str) -> TokenResponse:  # pragma: no cover
        resp = httpx.get(
            "https://api.weixin.qq.com/sns/oauth2/access_token",
            params={
                "appid": self.config.client_id,
                "secret": self.config.client_secret,
                "code": code,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        data = resp.json()
        if "errcode" in data and data["errcode"] != 0:
            logger.warning("WeChat token exchange failed: %s", data)
            raise ValueError(f"微信授权失败: {data.get('errmsg', 'unknown')}")
        return TokenResponse(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in"),
            raw=data,
        )

    def get_profile(self, token_response: TokenResponse) -> SocialProfile:  # pragma: no cover
        openid = token_response.raw["openid"]
        resp = httpx.get(
            "https://api.weixin.qq.com/sns/userinfo",
            params={
                "access_token": token_response.access_token,
                "openid": openid,
                "lang": "zh_CN",
            },
            timeout=10,
        )
        data = resp.json()
        if "errcode" in data and data["errcode"] != 0:
            logger.warning("WeChat get profile failed: %s", data)
            raise ValueError(f"获取微信用户信息失败: {data.get('errmsg', 'unknown')}")
        return SocialProfile(
            provider="wechat",
            provider_user_id=openid,
            email=None,
            display_name=data.get("nickname"),
            avatar_url=data.get("headimgurl"),
            raw_data=data,
        )

    async def aexchange_code(self, code: str, state: str) -> TokenResponse:  # pragma: no cover
        """异步版本。"""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.weixin.qq.com/sns/oauth2/access_token",
                params={
                    "appid": self.config.client_id,
                    "secret": self.config.client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                },
            )
        data = resp.json()
        if "errcode" in data and data["errcode"] != 0:
            logger.warning("WeChat token exchange failed: %s", data)
            raise ValueError(f"微信授权失败: {data.get('errmsg', 'unknown')}")
        return TokenResponse(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in"),
            raw=data,
        )

    async def aget_profile(self, token_response: TokenResponse) -> SocialProfile:  # pragma: no cover
        """异步版本。"""
        openid = token_response.raw["openid"]
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.weixin.qq.com/sns/userinfo",
                params={
                    "access_token": token_response.access_token,
                    "openid": openid,
                    "lang": "zh_CN",
                },
            )
        data = resp.json()
        if "errcode" in data and data["errcode"] != 0:
            logger.warning("WeChat get profile failed: %s", data)
            raise ValueError(f"获取微信用户信息失败: {data.get('errmsg', 'unknown')}")
        return SocialProfile(
            provider="wechat",
            provider_user_id=openid,
            email=None,
            display_name=data.get("nickname"),
            avatar_url=data.get("headimgurl"),
            raw_data=data,
        )

    def get_client_config(self) -> dict[str, str]:
        return {"appid": self.config.client_id}
