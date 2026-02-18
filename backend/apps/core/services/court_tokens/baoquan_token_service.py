"""Business logic services."""

import logging

from asgiref.sync import sync_to_async

from apps.core.exceptions import TokenError

logger = logging.getLogger(__name__)


class BaoquanTokenService:
    COURT_SITE_NAME = "court_zxfw"
    BAOQUAN_SITE_NAME = "court_baoquan"
    _BAOQUAN_TOKEN_PREFIX = "eyJhbGciOiJIUzUxMiJ9"  # noqa: S105

    async def get_valid_baoquan_token(self, credential_id: int | None = None) -> str:
        logger.info("获取保全系统 Token (HS512)...")

        from apps.core.services.wiring import get_court_token_store_service, get_organization_service

        organization_service = get_organization_service()
        token_store = get_court_token_store_service()

        if credential_id:
            credential = await sync_to_async(organization_service.get_credential_internal)(credential_id)
        else:
            all_credentials = await sync_to_async(organization_service.get_all_credentials_internal)()
            credentials = [
                c
                for c in all_credentials
                if ("zxfw.court.gov.cn" in (c.url or "")) or ("baoquan.court.gov.cn" in (c.url or ""))
            ]
            if not credentials:
                raise TokenError("没有找到法院保全系统的账号凭证")
            credential = credentials[0]

        account = credential.account

        token_info = await sync_to_async(token_store.get_latest_valid_token_internal)(
            site_name=self.BAOQUAN_SITE_NAME,
            account=account,
            token_prefix=self._BAOQUAN_TOKEN_PREFIX,
        )
        if token_info:
            logger.info(f"✅ 找到现有有效保全 Token: {token_info.account}")
            return token_info.token

        logger.info("无现有有效保全 Token,将自动获取")
        token = await self._acquire_baoquan_token(
            account=credential.account,
            password=credential.password,
            credential_id=credential_id,
        )
        return token

    async def _acquire_baoquan_token(
        self,
        *,
        account: str,
        password: str,
        credential_id: int | None = None,
    ) -> str:
        logger.info(f"使用账号 {account} 登录获取保全系统 Token")

        def _do_login_and_fetch() -> str:
            from playwright.sync_api import sync_playwright

            from apps.core.services.wiring import get_anti_detection, get_court_zxfw_service_factory

            anti_detection = get_anti_detection()

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False)
                context_options = anti_detection.get_browser_context_options()
                context = browser.new_context(**context_options)
                page = context.new_page()

                try:
                    service = get_court_zxfw_service_factory(page=page, context=context, site_name=self.COURT_SITE_NAME)
                    login_result = service.login(
                        account=account,
                        password=password,
                        max_captcha_retries=3,
                        save_debug=False,
                    )
                    if not login_result.get("success"):
                        raise TokenError(f"登录失败: {login_result.get('message')}")

                    result = service.fetch_baoquan_token(save_debug=False)
                    if not result.get("success"):
                        raise TokenError(result.get("message") or "获取保全 Token 失败")

                    token = result.get("token")
                    if not token or not token.startswith(self._BAOQUAN_TOKEN_PREFIX):
                        raise TokenError("获取到的保全 Token 非 HS512 格式")
                    return str(token)
                finally:
                    context.close()
                    browser.close()

        import asyncio

        loop = asyncio.get_running_loop()
        token = await loop.run_in_executor(None, _do_login_and_fetch)

        if not token:
            raise TokenError("登录成功但未获取到保全 Token")

        from apps.core.services.wiring import get_court_token_store_service

        token_store = get_court_token_store_service()
        await sync_to_async(token_store.save_token_internal)(
            site_name=self.BAOQUAN_SITE_NAME,
            account=account,
            token=token,
            expires_in=3600,
            credential_id=credential_id,
        )
        logger.info(f"✅ 保全 Token 已保存: {account}")
        return token
