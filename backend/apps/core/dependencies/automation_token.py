"""Module for automation token."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from apps.core.protocols import (
        IAccountSelectionStrategy,
        IAutoLoginService,
        IAutoTokenAcquisitionService,
        IBrowserService,
        ICaptchaService,
        ICourtDocumentService,
        ICourtTokenStoreService,
        IMonitorService,
        IOcrService,
        ISecurityService,
        ITokenService,
        IValidatorService,
    )


def build_auto_token_acquisition_service() -> IAutoTokenAcquisitionService:
    from plugins.court_automation.token.auto_token_acquisition_service import AutoTokenAcquisitionService

    return AutoTokenAcquisitionService(
        account_selection_strategy=build_account_selection_strategy(),
        auto_login_service=build_auto_login_service(),
        token_service=build_token_service(),
    )


def build_account_selection_strategy() -> IAccountSelectionStrategy:
    from plugins.court_automation.token.account_selection_strategy import AccountSelectionStrategy

    return AccountSelectionStrategy()


def build_auto_login_service() -> IAutoLoginService:
    from plugins.court_automation.token.auto_login_service import AutoLoginService
    from apps.automation.usecases.token.auto_login_usecase import RetryConfig

    return AutoLoginService(
        retry_config=RetryConfig(),  # type: ignore[arg-type]
        browser_service=build_browser_service(),
    )


def build_token_service() -> ITokenService:
    from apps.automation.services.scraper.core.token_service import TokenServiceAdapter

    return TokenServiceAdapter()


def build_court_token_store_service() -> ICourtTokenStoreService:
    from plugins.court_automation.token.court_token_store_service import CourtTokenStoreService

    return CourtTokenStoreService()


def build_browser_service() -> IBrowserService:
    from apps.core.services.browser import get_browser_service

    return get_browser_service()


def build_captcha_service() -> ICaptchaService:
    from apps.automation.services.captcha.captcha_recognition_service import CaptchaServiceAdapter

    return CaptchaServiceAdapter()


def build_ocr_service() -> IOcrService:
    from apps.automation.services.ocr.adapter import OCRServiceAdapter

    return OCRServiceAdapter()


def build_court_document_service() -> ICourtDocumentService:
    from apps.automation.services.scraper.court_document_service import CourtDocumentServiceAdapter

    return CourtDocumentServiceAdapter()


def build_monitor_service() -> IMonitorService:
    from apps.automation.services.scraper.core.monitor_service import MonitorServiceAdapter

    return MonitorServiceAdapter()


def build_security_service() -> ISecurityService:
    from apps.automation.services.scraper.core.security_service import SecurityServiceAdapter

    return SecurityServiceAdapter()


def build_validator_service() -> IValidatorService:
    from apps.automation.services.scraper.core.validator_service import ValidatorServiceAdapter

    return ValidatorServiceAdapter()
