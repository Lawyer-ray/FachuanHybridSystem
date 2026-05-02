"""金诚同达 OA 立案脚本 —— JtnFilingScript facade。"""

from __future__ import annotations

import logging
from typing import Any

from playwright.sync_api import BrowserContext, Page

from .filing_models import CaseInfo, ClientInfo, ConflictPartyInfo, ContractInfo
from .http_filing import HttpFilingMixin
from .playwright_filing import PlaywrightFilingMixin
from .playwright_helpers import PlaywrightHelpersMixin

logger = logging.getLogger("apps.oa_filing.jtn")


class JtnFilingScript(PlaywrightFilingMixin, PlaywrightHelpersMixin, HttpFilingMixin):
    """金诚同达 OA 立案自动化。"""

    def __init__(self, account: str, password: str) -> None:
        self._account = account
        self._password = password
        self._page: Page | None = None
        self._context: BrowserContext | None = None

    def run(
        self,
        clients: list[ClientInfo],
        case_info: CaseInfo | None = None,
        conflict_parties: list[ConflictPartyInfo] | None = None,
        contract_info: ContractInfo | None = None,
    ) -> None:
        """执行完整立案流程（HTTP 主链路 + Playwright 兜底）。"""
        try:
            self._run_via_http(
                clients=clients,
                case_info=case_info,
                conflict_parties=conflict_parties,
                contract_info=contract_info,
            )
            logger.info("HTTP 立案流程完成")
            return
        except Exception as exc:
            logger.warning("HTTP 立案失败，回退 Playwright: %s", exc, exc_info=True)

        self._run_via_playwright(
            clients=clients,
            case_info=case_info,
            conflict_parties=conflict_parties,
            contract_info=contract_info,
        )
