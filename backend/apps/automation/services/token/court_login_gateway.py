"""Business logic services."""

from django.utils.translation import gettext_lazy as _
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from apps.core.dtos import AccountCredentialDTO


class CourtLoginGateway(Protocol):
    def login(self, *, credential: AccountCredentialDTO, browser_context) -> str: ...


@dataclass(frozen=True)
class CourtZxfwLoginGateway:
    def login(self, *, credential: AccountCredentialDTO, browser_context) -> Any:
        from apps.automation.services.scraper.sites.court_zxfw import CourtZxfwService

        page = browser_context.new_page()
        service = CourtZxfwService(page=page, context=browser_context, site_name=credential.site_name)
        login_result = service.login(
            account=credential.account,
            password=credential.password,
            max_captcha_retries=1,
            save_debug=False,
        )

        if not login_result.get("success"):
            from apps.automation.exceptions import LoginFailedError

            raise LoginFailedError(message=f"登录失败: {login_result.get('message', '未知错误')}", attempts=[])

        token = login_result.get("token")
        if not token:
            from apps.automation.exceptions import LoginFailedError

            raise LoginFailedError(message=_("登录成功但未获取到token"), attempts=[])
        return token
