"""reminders/services/calendar_providers/mac_provider.py 单元测试。"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from apps.reminders.services.calendar_providers.mac_provider import MacCalendarProvider


class TestMacCalendarProviderParseLine:
    """_parse_line 静态方法测试。"""

    def test_valid_line(self) -> None:
        line = "uid123||Meeting||2026年6月1日 星期日 10:00:00||2026年6月1日 星期日 11:00:00||Office||desc||Work||false"
        event = MacCalendarProvider._parse_line(line)
        assert event is not None
        assert event.uid == "uid123"
        assert event.title == "Meeting"
        assert event.location == "Office"
        assert event.description == "desc"
        assert event.calendar_name == "Work"
        assert event.is_all_day is False

    def test_all_day_event(self) -> None:
        line = "uid456||Holiday||2026年1月1日 星期四 00:00:00||2026年1月1日 星期四 00:00:00||Loc||Desc||Cal||true"
        event = MacCalendarProvider._parse_line(line)
        assert event is not None
        assert event.is_all_day is True

    def test_too_few_parts_returns_none(self) -> None:
        assert MacCalendarProvider._parse_line("a||b||c") is None

    def test_empty_title_returns_none(self) -> None:
        line = "uid||||2026年6月1日 星期日 10:00:00||2026年6月1日 星期日 11:00:00||||cal||false"
        event = MacCalendarProvider._parse_line(line)
        assert event is None

    def test_empty_line_returns_none(self) -> None:
        assert MacCalendarProvider._parse_line("") is None

    def test_title_truncated_to_255(self) -> None:
        long_title = "A" * 300
        line = f"uid||{long_title}||2026年6月1日 星期日 10:00:00||2026年6月1日 星期日 11:00:00||||cal||false"
        event = MacCalendarProvider._parse_line(line)
        assert event is not None
        assert len(event.title) == 255

    def test_missing_all_day_field_defaults_false(self) -> None:
        line = "uid||Title||2026年6月1日 星期日 10:00:00||2026年6月1日 星期日 11:00:00||Loc||Desc||Cal"
        event = MacCalendarProvider._parse_line(line)
        assert event is not None
        assert event.is_all_day is False


class TestMacCalendarProviderParseAppleScriptDate:
    """_parse_applescript_date 静态方法测试。"""

    def test_chinese_format_am(self) -> None:
        result = MacCalendarProvider._parse_applescript_date("2026年4月25日 星期六 上午7:00:00")
        assert result is not None
        assert result.hour == 7

    def test_chinese_format_pm(self) -> None:
        result = MacCalendarProvider._parse_applescript_date("2026年4月25日 星期六 下午3:00:00")
        assert result is not None
        assert result.hour == 15

    def test_chinese_format_midnight(self) -> None:
        result = MacCalendarProvider._parse_applescript_date("2026年4月25日 星期六 上午12:00:00")
        assert result is not None
        assert result.hour == 0

    def test_chinese_format_noon(self) -> None:
        result = MacCalendarProvider._parse_applescript_date("2026年4月25日 星期六 下午12:00:00")
        assert result is not None
        assert result.hour == 12

    def test_chinese_format_24h(self) -> None:
        result = MacCalendarProvider._parse_applescript_date("2026年4月25日 星期六 00:00:00")
        assert result is not None
        assert result.hour == 0

    def test_english_format_with_day(self) -> None:
        result = MacCalendarProvider._parse_applescript_date("Friday, April 25, 2026 at 7:00:00 AM")
        assert result is not None
        assert result.year == 2026
        assert result.month == 4
        assert result.day == 25

    def test_missing_value_returns_none(self) -> None:
        assert MacCalendarProvider._parse_applescript_date("missing value") is None

    def test_empty_string_returns_none(self) -> None:
        assert MacCalendarProvider._parse_applescript_date("") is None

    def test_unparseable_returns_none(self) -> None:
        assert MacCalendarProvider._parse_applescript_date("completely invalid") is None


class TestMacCalendarProviderBuildScript:
    """_build_script 静态方法测试。"""

    def test_basic_script(self) -> None:
        start = datetime(2026, 6, 1, 10, 0, 0)
        end = datetime(2026, 6, 30, 18, 0, 0)
        script = MacCalendarProvider._build_script(start, end)
        assert "2026" in script
        assert "Calendar" in script
        assert "startRange" in script

    def test_script_with_included_calendars(self) -> None:
        start = datetime(2026, 6, 1)
        end = datetime(2026, 6, 30)
        script = MacCalendarProvider._build_script(start, end, included_calendars=["Work", "Personal"])
        assert '"Work"' in script
        assert '"Personal"' in script
        assert "includedCalNames" in script

    def test_script_without_included_calendars(self) -> None:
        start = datetime(2026, 6, 1)
        end = datetime(2026, 6, 30)
        script = MacCalendarProvider._build_script(start, end)
        assert "includedCalNames" not in script

    def test_script_escapes_quotes(self) -> None:
        start = datetime(2026, 6, 1)
        end = datetime(2026, 6, 30)
        script = MacCalendarProvider._build_script(start, end, included_calendars=['My "Calendar"'])
        assert '\\"' in script


class TestMacCalendarProviderDefaultExcludedCalendars:
    """DEFAULT_EXCLUDED_CALENDARS 测试。"""

    def test_contains_chinese_holidays(self) -> None:
        assert "中国大陆节假日" in MacCalendarProvider.DEFAULT_EXCLUDED_CALENDARS

    def test_contains_birthdays(self) -> None:
        assert "Birthdays" in MacCalendarProvider.DEFAULT_EXCLUDED_CALENDARS

    def test_is_list(self) -> None:
        assert isinstance(MacCalendarProvider.DEFAULT_EXCLUDED_CALENDARS, list)


class TestMacCalendarProviderListCalendars:
    """list_calendars 测试。"""

    @patch("apps.reminders.services.calendar_providers.mac_provider.subprocess.run")
    def test_success(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Work||local\nPersonal||icloud\n",
        )
        provider = MacCalendarProvider()
        cals = provider.list_calendars()
        assert len(cals) == 2
        assert cals[0]["name"] == "Work"
        assert cals[0]["type"] == "local"

    @patch("apps.reminders.services.calendar_providers.mac_provider.subprocess.run")
    def test_failure_returns_empty(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        provider = MacCalendarProvider()
        assert provider.list_calendars() == []

    @patch("apps.reminders.services.calendar_providers.mac_provider.subprocess.run")
    def test_timeout_returns_empty(self, mock_run: MagicMock) -> None:
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="osascript", timeout=15)
        provider = MacCalendarProvider()
        assert provider.list_calendars() == []

    @patch("apps.reminders.services.calendar_providers.mac_provider.subprocess.run")
    def test_empty_output(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        provider = MacCalendarProvider()
        assert provider.list_calendars() == []


class TestMacCalendarProviderGetAuthStatus:
    """get_auth_status 测试。"""

    @patch("apps.reminders.services.calendar_providers.mac_provider.subprocess.run")
    def test_authorized(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        assert MacCalendarProvider.get_auth_status() == 3

    @patch("apps.reminders.services.calendar_providers.mac_provider.subprocess.run")
    def test_denied(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1, stderr="not allowed to access calendars")
        assert MacCalendarProvider.get_auth_status() == 2

    @patch("apps.reminders.services.calendar_providers.mac_provider.subprocess.run")
    def test_not_determined(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1, stderr="some other error")
        assert MacCalendarProvider.get_auth_status() == 0

    @patch("apps.reminders.services.calendar_providers.mac_provider.subprocess.run")
    def test_exception_returns_zero(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = OSError("not found")
        assert MacCalendarProvider.get_auth_status() == 0
