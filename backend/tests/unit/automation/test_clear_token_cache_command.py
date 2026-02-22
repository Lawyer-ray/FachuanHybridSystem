import io

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.automation.services.token.cache_manager import TokenCacheManager


def test_clear_token_cache_command_prints_plan_without_execute():
    out = io.StringIO()
    call_command("clear_token_cache", "--site", "s1", stdout=out)
    assert "计划:定向失效 token 缓存" in out.getvalue()


def test_clear_token_cache_command_all_requires_allow_in_production(settings, monkeypatch):
    settings.DEBUG = False
    monkeypatch.delenv("ALLOW_CACHE_CLEAR", raising=False)
    with pytest.raises(CommandError):
        call_command("clear_token_cache", "--all", "--execute")


def test_clear_token_cache_command_executes_targeted(monkeypatch):
    called = {"site": None, "accounts": None, "blacklist": 0}

    def fake_invalidate_site_cache(self, site_name: str, *, accounts=None):
        called["site"] = site_name # type: ignore[assignment]
        called["accounts"] = accounts

    def fake_invalidate_blacklist_cache(self):
        called["blacklist"] += 1  # type: ignore[operator]

    monkeypatch.setattr(TokenCacheManager, "invalidate_site_cache", fake_invalidate_site_cache)
    monkeypatch.setattr(TokenCacheManager, "invalidate_blacklist_cache", fake_invalidate_blacklist_cache)

    out = io.StringIO()
    call_command(
        "clear_token_cache",
        "--site",
        "s1",
        "--account",
        "a1@example.com",
        "--account",
        "a2@example.com",
        "--blacklist",
        "--execute",
        stdout=out,
    )
    assert called["site"] == "s1"
    assert called["accounts"] == ["a1@example.com", "a2@example.com"]
    assert called["blacklist"] == 1
