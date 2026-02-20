"""Business logic services."""

from __future__ import annotations

import inspect
from typing import Any


class TokenServiceAdapter:
    def __init__(self, token_service: Any) -> None:
        self._token_service = token_service

    async def _maybe_await(self, value: Any) -> Any:
        if inspect.isawaitable(value):
            return await value
        return value

    async def get_token(self, *, site_name: str, account: str) -> Any:
        get_token = getattr(self._token_service, "get_token", None)
        if get_token is None:
            return None

        try:
            signature = inspect.signature(get_token)
            if "account" in signature.parameters:
                return await self._maybe_await(get_token(site_name=site_name, account=account))
            return await self._maybe_await(get_token(site_name))
        except (TypeError, ValueError):
            return await self._maybe_await(get_token(site_name))

    async def save_token(self, *, site_name: str, account: str, token: str) -> None:
        save_token = getattr(self._token_service, "save_token", None)
        if save_token is None:
            return None

        try:
            signature = inspect.signature(save_token)
            params = signature.parameters
            accepts_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())

            if "account" in params or accepts_kwargs:
                kw: dict[str, Any] = {"site_name": site_name, "account": account, "token": token}
                if "expires_in" in params and params["expires_in"].default is inspect._empty:
                    kw["expires_in"] = 3600
                await self._maybe_await(save_token(**kw))
                return None

            kw2: dict[str, Any] = {}
            if "expires_in" in params:
                kw2["expires_in"] = 3600
            await self._maybe_await(save_token(**kw2))
            return None
        except (TypeError, ValueError):
            await self._maybe_await(save_token(site_name=site_name, token=token, expires_in=3600))
            return None
