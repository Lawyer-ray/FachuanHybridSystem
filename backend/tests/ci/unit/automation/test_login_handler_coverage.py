"""Coverage tests for automation.services.token._login_handler."""

from unittest.mock import MagicMock, AsyncMock, patch

import pytest
import asyncio


class TestLoginHandler:
    def _make(self):
        from apps.automation.services.token._login_handler import LoginHandler

        account_strategy = AsyncMock()
        auto_login = AsyncMock()
        token_service = AsyncMock()
        config = MagicMock()
        config.acquisition_timeout = 30
        return LoginHandler(account_strategy, auto_login, token_service, config)

    @pytest.mark.asyncio
    async def test_select_credential_by_id(self):
        handler = self._make()
        with patch("apps.core.dependencies.build_organization_service") as mock_build:
            mock_svc = MagicMock()
            mock_credential = MagicMock()
            mock_credential.account = "test"
            mock_credential.password = "pass"
            mock_svc.get_credential = AsyncMock(return_value=mock_credential)
            mock_build.return_value = mock_svc
            with patch("apps.core.interfaces.AccountCredentialDTO.from_model", return_value=MagicMock(account="test")):
                result = await handler.select_credential("acq1", "site", credential_id=1, selected_credential=None)
                assert result is not None

    @pytest.mark.asyncio
    async def test_select_credential_pre_selected(self):
        handler = self._make()
        mock_cred = MagicMock()
        mock_cred.account = "pre_selected"
        result = await handler.select_credential("acq1", "site", credential_id=None, selected_credential=mock_cred)
        assert result == mock_cred

    @pytest.mark.asyncio
    async def test_select_credential_auto(self):
        handler = self._make()
        mock_cred = MagicMock()
        mock_cred.account = "auto"
        handler._account_selection_strategy.select_account.return_value = mock_cred
        result = await handler.select_credential("acq1", "site", credential_id=None, selected_credential=None)
        assert result == mock_cred

    @pytest.mark.asyncio
    async def test_select_credential_no_available(self):
        from apps.core.exceptions import NoAvailableAccountError

        handler = self._make()
        handler._account_selection_strategy.select_account.return_value = None
        with pytest.raises(NoAvailableAccountError):
            await handler.select_credential("acq1", "site", credential_id=None, selected_credential=None)
