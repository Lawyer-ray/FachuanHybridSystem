from __future__ import annotations

import logging

from apps.legal_research.services.similarity.tuning_config import LegalResearchTuningConfig

from . import api_optional
from .auth import WeikeAuthMixin
from .document import WeikeDocumentMixin
from .search import WeikeSearchMixin
from .transport import WeikeTransportMixin
from .types import WeikeCaseDetail, WeikeSearchItem, WeikeSession

logger = logging.getLogger(__name__)


class WeikeCaseClient(WeikeAuthMixin, WeikeSearchMixin, WeikeDocumentMixin, WeikeTransportMixin):  # pragma: no cover
    LOGIN_URL = "https://www.wkinfo.com.cn/login/index"
    LAW_LIST_URL = "https://law.wkinfo.com.cn/judgment-documents/list"
    LAW_SSO_URL = "https://law.wkinfo.com.cn/boldUsers/checkValidate"
    HOME_URL = "https://www.wkinfo.com.cn/?lang="
    HOME_LOGIN_URL = "https://www.wkinfo.com.cn/login/checkValidate?lang=zh_CN"

    def __init__(self, *, tuning: LegalResearchTuningConfig | None = None) -> None:  # pragma: no cover
        if tuning is not None:
            config = tuning
        else:
            try:
                config = LegalResearchTuningConfig.load()
            except Exception:
                config = LegalResearchTuningConfig()
        self._session_restrict_cooldown_seconds = max(
            30,
            int(
                getattr(config, "weike_session_restrict_cooldown_seconds", self.SESSION_RESTRICT_COOLDOWN_SECONDS) or 0
            ),
        )
        self._search_api_degrade_streak_threshold = max(
            1,
            int(getattr(config, "weike_search_api_degrade_streak_threshold", 2) or 0),
        )
        self._search_api_degrade_cooldown_seconds = max(
            30,
            int(getattr(config, "weike_search_api_degrade_cooldown_seconds", 180)),
        )

    def open_session(  # pragma: no cover
        self,
        *,
        username: str,
        password: str,
        login_url: str | None = None,
    ) -> WeikeSession:
        normalized_login_url = self._normalize_login_url(login_url)
        private_api = api_optional.get_private_weike_api()
        if private_api is not None:
            try:
                session = private_api.open_http_session(
                    client=self,
                    username=username,
                    password=password,
                    login_url=normalized_login_url,
                )
                if isinstance(session, WeikeSession):
                    session.username = session.username or username
                    session.password = session.password or password
                    session.login_url = session.login_url or normalized_login_url
                    session.search_via_api_enabled = True
                    return session
                logger.warning("私有wk API open_http_session 返回类型不正确，回退Playwright")
            except Exception:
                logger.exception("私有wk API登录失败，回退Playwright登录")

        from apps.core.services.browser import create_browser

        cm = create_browser("default")
        page, context = cm.__enter__()

        try:
            self._login_and_enter_law(
                page=page,
                username=username,
                password=password,
                login_url=normalized_login_url,
            )
            return WeikeSession(
                page=page,
                context=context,
                context_manager=cm,
                username=username,
                password=password,
                login_url=normalized_login_url,
            )
        except Exception:
            try:
                cm.__exit__(None, None, None)
            except Exception:
                pass
            raise


__all__ = [
    "WeikeCaseClient",
    "WeikeCaseDetail",
    "WeikeSearchItem",
    "WeikeSession",
]
