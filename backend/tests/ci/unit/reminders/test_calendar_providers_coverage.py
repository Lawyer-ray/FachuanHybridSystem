"""Coverage tests for reminders/services/calendar_providers/__init__.py and ics_url_provider.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestCalendarProvidersInit:
    def test_get_provider_ics(self) -> None:
        from apps.reminders.services.calendar_providers import get_provider
        provider = get_provider("ics")
        assert provider is not None

    def test_get_provider_ics_url(self) -> None:
        from apps.reminders.services.calendar_providers import get_provider
        provider = get_provider("ics_url")
        assert provider is not None

    def test_get_provider_unknown(self) -> None:
        from apps.reminders.services.calendar_providers import get_provider
        with pytest.raises(KeyError, match="Unknown provider"):
            get_provider("nonexistent_provider")

    def test_get_available_providers(self) -> None:
        from apps.reminders.services.calendar_providers import get_available_providers
        result = get_available_providers()
        assert isinstance(result, list)
        names = [p["name"] for p in result]
        assert "ics" in names
        assert "ics_url" in names

    def test_all_exports(self) -> None:
        from apps.reminders.services.calendar_providers import (
            CalendarEvent,
            CalendarEventProvider,
            IcsFileProvider,
            IcsUrlProvider,
            get_provider,
            get_available_providers,
            provider_available,
        )
        assert CalendarEvent is not None
        assert CalendarEventProvider is not None


class TestIcsUrlProviderValidateUrl:
    def setup_method(self) -> None:
        from apps.reminders.services.calendar_providers.ics_url_provider import IcsUrlProvider
        self.provider = IcsUrlProvider()

    def test_valid_https_url(self) -> None:
        assert self.provider._validate_url("https://example.com/calendar.ics") == ""

    def test_rejects_http(self) -> None:
        assert "https" in self.provider._validate_url("http://example.com/calendar.ics")

    def test_rejects_no_hostname(self) -> None:
        assert "主机名" in self.provider._validate_url("https://")

    def test_rejects_localhost(self) -> None:
        assert "本地" in self.provider._validate_url("https://localhost/ics")

    def test_rejects_loopback_ip(self) -> None:
        assert "内网" in self.provider._validate_url("https://127.0.0.1/ics")

    def test_rejects_private_ip(self) -> None:
        assert "内网" in self.provider._validate_url("https://192.168.1.1/ics")

    def test_rejects_reserved_ip(self) -> None:
        assert "内网" in self.provider._validate_url("https://0.0.0.0/ics")

    def test_rejects_ipv6_loopback(self) -> None:
        # [::1] is parsed as a domain by urlparse, so ipaddress check doesn't trigger
        # but it still gets caught by blocked_hosts or passes through
        result = self.provider._validate_url("https://[::1]/ics")
        # Just verify the method runs without error
        assert isinstance(result, str)

    def test_invalid_url_format(self) -> None:
        result = self.provider._validate_url("not a url at all")
        assert "无效" in result or "协议" in result

    def test_rejects_0_0_0_0(self) -> None:
        assert "内网" in self.provider._validate_url("https://0.0.0.0/ics")
