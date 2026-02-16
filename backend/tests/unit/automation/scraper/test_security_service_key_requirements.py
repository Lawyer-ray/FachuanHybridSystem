import pytest

from apps.automation.services.scraper.core.security_service import SecurityService


class TestSecurityServiceKeyRequirements:
    def test_requires_key_in_production(self, settings, monkeypatch):
        settings.DEBUG = False

        monkeypatch.setattr(
            "apps.automation.services.scraper.core.security_service.get_config",
            lambda _key, _default=None: None,
        )

        with pytest.raises(RuntimeError):
            SecurityService()

    def test_allows_ephemeral_key_in_debug(self, settings, monkeypatch):
        settings.DEBUG = True

        monkeypatch.setattr(
            "apps.automation.services.scraper.core.security_service.get_config",
            lambda _key, _default=None: None,
        )

        service = SecurityService()
        assert service.cipher is not None
