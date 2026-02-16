from unittest.mock import AsyncMock, Mock

import pytest

from apps.automation.services.token.auto_login_service import AutoLoginService
from apps.automation.usecases.token.auto_login_usecase import AutoLoginUsecase, RetryConfig
from apps.core.exceptions import NetworkError
from apps.core.interfaces import AccountCredentialDTO


@pytest.fixture
def sample_credential():
    return AccountCredentialDTO(
        id=1,
        lawyer_id=1,
        site_name="court_zxfw",
        account="test_user",
        password="test_password",
        url="https://zxfw.court.gov.cn",
    )


@pytest.mark.anyio
async def test_auto_login_usecase_network_retry_success(sample_credential):
    usecase = AutoLoginUsecase(
        retry_config=RetryConfig(max_network_retries=2, max_captcha_retries=1, network_retry_delay_base=0.0),
        browser_context_factory=Mock(),
        login_gateway=Mock(),
        sleep=AsyncMock(),
    )
    usecase._single_login_attempt = AsyncMock(side_effect=[NetworkError("network down"), "token_123"])

    token = await usecase.execute(sample_credential)

    assert token == "token_123"
    assert len(usecase.get_login_attempts()) == 2
    assert usecase.get_login_attempts()[0].success is False
    assert usecase.get_login_attempts()[1].success is True


@pytest.mark.anyio
async def test_auto_login_service_delegates_to_usecase(sample_credential):
    usecase = Mock()
    usecase.execute = AsyncMock(return_value="token_123")
    service = AutoLoginService(usecase=usecase)

    token = await service.login_and_get_token(sample_credential)

    assert token == "token_123"
    usecase.execute.assert_awaited_once()
