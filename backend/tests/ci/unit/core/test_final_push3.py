"""Final push coverage tests for core module — config utils, validators, filename templates."""

from __future__ import annotations

import io
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, PropertyMock

import pytest

from apps.core.exceptions import ValidationException


# ============================================================================
# config/utils.py tests
# ============================================================================


class TestGetNestedConfigValue:
    def test_returns_existing_key(self):
        from apps.core.config.utils import get_nested_config_value

        assert get_nested_config_value({"a": 1, "b": 2}, "a") == 1

    def test_returns_default_for_missing_key(self):
        from apps.core.config.utils import get_nested_config_value

        assert get_nested_config_value({"a": 1}, "z", default=42) == 42

    def test_returns_none_when_no_default(self):
        from apps.core.config.utils import get_nested_config_value

        assert get_nested_config_value({}, "missing") is None

    def test_empty_dict(self):
        from apps.core.config.utils import get_nested_config_value

        assert get_nested_config_value({}, "key", "fallback") == "fallback"


class TestIsConfigManagerAvailable:
    def test_returns_false_when_not_set(self):
        from apps.core.config.utils import is_config_manager_available

        with patch("apps.core.config.utils.settings") as mock_settings:
            del mock_settings.CONFIG_MANAGER_AVAILABLE
            assert is_config_manager_available() is False

    def test_returns_true_when_set(self):
        from apps.core.config.utils import is_config_manager_available

        with patch("apps.core.config.utils.settings") as mock_settings:
            mock_settings.CONFIG_MANAGER_AVAILABLE = True
            assert is_config_manager_available() is True


class TestGetConfigManager:
    def test_returns_none_when_not_available(self):
        from apps.core.config.utils import get_config_manager

        with patch("apps.core.config.utils.is_config_manager_available", return_value=False):
            assert get_config_manager() is None

    def test_returns_manager_when_available(self):
        from apps.core.config.utils import get_config_manager

        mock_manager = Mock()
        with (
            patch("apps.core.config.utils.is_config_manager_available", return_value=True),
            patch("apps.core.config.utils.settings") as mock_settings,
        ):
            mock_settings.UNIFIED_CONFIG_MANAGER = mock_manager
            assert get_config_manager() is mock_manager


class TestGetConfigValue:
    def test_returns_default_when_no_config(self):
        from apps.core.config.utils import get_config_value

        with patch("apps.core.config.utils.settings") as mock_settings:
            mock_settings.CONFIG_MANAGER_AVAILABLE = False
            result = get_config_value("some.key", default="fallback")
            assert result == "fallback"

    def test_returns_from_unified_config(self):
        from apps.core.config.utils import get_config_value

        with patch("apps.core.config.utils.settings") as mock_settings:
            mock_settings.CONFIG_MANAGER_AVAILABLE = True
            mock_settings.get_unified_config = Mock(return_value="unified_value")
            result = get_config_value("some.key", default="fallback")
            assert result == "unified_value"

    def test_falls_back_to_settings_key(self):
        from apps.core.config.utils import get_config_value

        with patch("apps.core.config.utils.settings") as mock_settings:
            mock_settings.CONFIG_MANAGER_AVAILABLE = False
            mock_settings.MY_SETTING = "settings_value"
            result = get_config_value("some.key", fallback_settings_key="MY_SETTING")
            assert result == "settings_value"

    def test_returns_none_when_unified_returns_none(self):
        from apps.core.config.utils import get_config_value

        with patch("apps.core.config.utils.settings") as mock_settings:
            mock_settings.CONFIG_MANAGER_AVAILABLE = True
            mock_settings.get_unified_config = Mock(return_value=None)
            result = get_config_value("key", default="d")
            assert result == "d"

    def test_handles_exception_in_unified_config(self):
        from apps.core.config.utils import get_config_value

        with patch("apps.core.config.utils.settings") as mock_settings:
            mock_settings.CONFIG_MANAGER_AVAILABLE = True
            mock_settings.get_unified_config = Mock(side_effect=RuntimeError("boom"))
            result = get_config_value("key", default="safe")
            assert result == "safe"


class TestRegisterConfigChangeListener:
    def test_registers_when_manager_available(self):
        from apps.core.config.utils import register_config_change_listener

        mock_manager = Mock()
        listener = Mock()
        with patch("apps.core.config.utils.get_config_manager", return_value=mock_manager):
            register_config_change_listener(listener, key_filter="k", prefix_filter="p")
        mock_manager.add_listener.assert_called_once_with(listener, "k", "p")

    def test_warns_when_manager_unavailable(self):
        from apps.core.config.utils import register_config_change_listener

        with patch("apps.core.config.utils.get_config_manager", return_value=None):
            register_config_change_listener(Mock())


class TestMigrateLegacyConfigAccess:
    def test_returns_from_unified_when_available(self):
        from apps.core.config.utils import migrate_legacy_config_access

        with patch("apps.core.config.utils.is_config_manager_available", return_value=True):
            with patch("apps.core.config.utils.settings") as mock_settings:
                mock_settings.get_unified_config = Mock(return_value="unified")
                result = migrate_legacy_config_access("OLD_KEY", "new.key")
                assert result == "unified"

    def test_returns_legacy_when_unified_unavailable(self):
        from apps.core.config.utils import migrate_legacy_config_access

        with patch("apps.core.config.utils.is_config_manager_available", return_value=False):
            with patch("apps.core.config.utils.settings") as mock_settings:
                mock_settings.OLD_KEY = "legacy_val"
                result = migrate_legacy_config_access("OLD_KEY", "new.key")
                assert result == "legacy_val"

    def test_returns_default_when_neither_available(self):
        from apps.core.config.utils import migrate_legacy_config_access

        with patch("apps.core.config.utils.is_config_manager_available", return_value=False):
            with patch("apps.core.config.utils.settings", spec=[]):
                result = migrate_legacy_config_access("NOPE", "nope", default="dflt")
                assert result == "dflt"


class TestGetFeishuConfig:
    def test_returns_from_feishu_settings(self):
        from apps.core.config.utils import get_feishu_config

        with patch("apps.core.config.utils.settings") as mock_settings:
            mock_settings.CONFIG_MANAGER_AVAILABLE = False
            mock_settings.FEISHU = {"APP_ID": "my_app"}
            mock_settings.COURT_SMS_PROCESSING = {}
            result = get_feishu_config("app_id")
            assert result == "my_app"

    def test_returns_from_legacy_court_sms(self):
        from apps.core.config.utils import get_feishu_config

        with patch("apps.core.config.utils.settings") as mock_settings:
            mock_settings.CONFIG_MANAGER_AVAILABLE = False
            mock_settings.FEISHU = {}
            mock_settings.COURT_SMS_PROCESSING = {"FEISHU_SECRET": "old_secret"}
            result = get_feishu_config("secret")
            assert result == "old_secret"

    def test_returns_default(self):
        from apps.core.config.utils import get_feishu_config

        with patch("apps.core.config.utils.settings") as mock_settings:
            mock_settings.CONFIG_MANAGER_AVAILABLE = False
            mock_settings.FEISHU = {}
            mock_settings.COURT_SMS_PROCESSING = {}
            result = get_feishu_config("missing", default="def")
            assert result == "def"


class TestGetDocumentProcessingConfig:
    def test_returns_from_unified(self):
        from apps.core.config.utils import get_document_processing_config

        with patch("apps.core.config.utils.settings") as mock_settings:
            mock_settings.CONFIG_MANAGER_AVAILABLE = True
            mock_settings.get_unified_config = Mock(return_value="val")
            assert get_document_processing_config("key") == "val"

    def test_falls_back_to_legacy(self):
        from apps.core.config.utils import get_document_processing_config

        with patch("apps.core.config.utils.settings") as mock_settings:
            mock_settings.CONFIG_MANAGER_AVAILABLE = False
            mock_settings.DOCUMENT_PROCESSING = {"MYKEY": "doc_val"}
            assert get_document_processing_config("mykey") == "doc_val"


class TestGetCaseChatConfig:
    def test_returns_from_unified(self):
        from apps.core.config.utils import get_case_chat_config

        with patch("apps.core.config.utils.settings") as mock_settings:
            mock_settings.CONFIG_MANAGER_AVAILABLE = True
            mock_settings.get_unified_config = Mock(return_value="chat_val")
            assert get_case_chat_config("key") == "chat_val"

    def test_falls_back_to_legacy(self):
        from apps.core.config.utils import get_case_chat_config

        with patch("apps.core.config.utils.settings") as mock_settings:
            mock_settings.CONFIG_MANAGER_AVAILABLE = False
            mock_settings.CASE_CHAT = {"GROUP": "g123"}
            assert get_case_chat_config("group") == "g123"


class TestGetCourtSmsConfig:
    def test_returns_from_unified(self):
        from apps.core.config.utils import get_court_sms_config

        with patch("apps.core.config.utils.settings") as mock_settings:
            mock_settings.CONFIG_MANAGER_AVAILABLE = True
            mock_settings.get_unified_config = Mock(return_value="sms_val")
            assert get_court_sms_config("key") == "sms_val"

    def test_falls_back_to_legacy(self):
        from apps.core.config.utils import get_court_sms_config

        with patch("apps.core.config.utils.settings") as mock_settings:
            mock_settings.CONFIG_MANAGER_AVAILABLE = False
            mock_settings.COURT_SMS_PROCESSING = {"ENABLED": "true"}
            assert get_court_sms_config("enabled") == "true"


class TestGetSystemConfigValue:
    def test_returns_value(self):
        from apps.core.config.utils import get_system_config_value

        mock_service = Mock()
        mock_service.get_value.return_value = "sys_val"
        with patch("apps.core.services.system_config_service.SystemConfigService", return_value=mock_service):
            result = get_system_config_value("key", default="d")
            assert result == "sys_val"

    def test_returns_default_on_exception(self):
        from apps.core.config.utils import get_system_config_value

        with patch(
            "apps.core.services.system_config_service.SystemConfigService", side_effect=RuntimeError("boom")
        ):
            result = get_system_config_value("key", default="safe")
            assert result == "safe"


# ============================================================================
# validators.py tests (core/utils/validators.py)
# ============================================================================


class TestValidatorsPhone:
    def test_valid_phone(self):
        from apps.core.utils.validators import Validators

        assert Validators.validate_phone("13800138000") == "13800138000"

    def test_phone_with_spaces(self):
        from apps.core.utils.validators import Validators

        assert Validators.validate_phone("  13800138000  ") == "13800138000"

    def test_none_phone(self):
        from apps.core.utils.validators import Validators

        assert Validators.validate_phone(None) is None

    def test_empty_phone(self):
        from apps.core.utils.validators import Validators

        assert Validators.validate_phone("") is None

    def test_invalid_phone(self):
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_phone("1234567")

    def test_invalid_phone_starts_with_wrong_digit(self):
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_phone("12345678901")


class TestValidatorsEmail:
    def test_valid_email(self):
        from apps.core.utils.validators import Validators

        assert Validators.validate_email("Test@Example.com") == "test@example.com"

    def test_none_email(self):
        from apps.core.utils.validators import Validators

        assert Validators.validate_email(None) is None

    def test_empty_email_raises(self):
        from apps.core.utils.validators import Validators

        # "  " strips to "" which is falsy but matches empty check in validate_email
        # Actually, validate_email checks "if not email" after strip, so "  " -> "" -> returns None
        # But actually the code does email = email.strip().lower() first, then checks EMAIL_PATTERN
        # So "  " -> "" -> doesn't match pattern -> raises ValidationException
        with pytest.raises(ValidationException):
            Validators.validate_email("  ")

    def test_invalid_email(self):
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_email("not-an-email")


class TestValidatorsIdCard:
    def test_valid_id_card(self):
        from apps.core.utils.validators import Validators

        # Use a known valid ID card: 11010519491231002X
        # weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
        # 1*7+1*9+0*10+1*5+0*8+5*4+1*2+9*1+4*6+9*3+1*7+2*9+3*10+1*5+0*8+0*4+2*2
        # = 7+9+0+5+0+20+2+9+24+27+7+18+30+5+0+0+4 = 167
        # 167 % 11 = 2, check_codes[2] = 'X'
        result = Validators.validate_id_card("11010519491231002X")
        assert result == "11010519491231002X"

    def test_none_id_card(self):
        from apps.core.utils.validators import Validators

        assert Validators.validate_id_card(None) is None

    def test_invalid_checksum(self):
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_id_card("110105194912310020")  # wrong checksum

    def test_invalid_format(self):
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_id_card("12345")


class TestValidatorsSocialCreditCode:
    def test_valid_code(self):
        from apps.core.utils.validators import Validators

        code = "91350100M000100Y43"
        result = Validators.validate_social_credit_code(code)
        assert result == code

    def test_none_code(self):
        from apps.core.utils.validators import Validators

        assert Validators.validate_social_credit_code(None) is None

    def test_invalid_code(self):
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_social_credit_code("invalid")


class TestValidatorsRequired:
    def test_valid_string(self):
        from apps.core.utils.validators import Validators

        assert Validators.validate_required("hello", "name") == "hello"

    def test_none_raises(self):
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_required(None, "name")

    def test_empty_string_raises(self):
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_required("  ", "name")


class TestValidatorsLength:
    def test_valid_length(self):
        from apps.core.utils.validators import Validators

        assert Validators.validate_length("hello", "f", min_length=2, max_length=10) == "hello"

    def test_too_short(self):
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_length("hi", "f", min_length=5)

    def test_too_long(self):
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_length("hello world", "f", max_length=3)

    def test_none_returns_none(self):
        from apps.core.utils.validators import Validators

        assert Validators.validate_length(None, "f", min_length=1) is None

    def test_empty_returns_none(self):
        from apps.core.utils.validators import Validators

        assert Validators.validate_length("", "f", min_length=1) is None


class TestValidatorsRange:
    def test_valid_range(self):
        from apps.core.utils.validators import Validators

        assert Validators.validate_range(5.0, "f", min_value=1, max_value=10) == 5.0

    def test_none_returns_none(self):
        from apps.core.utils.validators import Validators

        assert Validators.validate_range(None, "f") is None

    def test_below_min(self):
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_range(0.5, "f", min_value=1)

    def test_above_max(self):
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_range(100, "f", max_value=50)


class TestValidatorsDecimal:
    def test_valid_decimal(self):
        from apps.core.utils.validators import Validators

        result = Validators.validate_decimal("123.45", "amount")
        assert result == Decimal("123.45")

    def test_none_returns_none(self):
        from apps.core.utils.validators import Validators

        assert Validators.validate_decimal(None, "amount") is None

    def test_invalid_decimal(self):
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_decimal("abc", "amount")

    def test_too_many_integer_digits(self):
        from apps.core.utils.validators import Validators

        # 99999999999.99 has 11 integer digits, with max_digits=14 and decimal_places=2,
        # max integer digits = 14-2=12, so 11 integer digits is fine.
        # Let's use a number that exceeds: 12 integer + 2 decimal = 14, but 13 integer + 2 = 15 > 14
        with pytest.raises(ValidationException):
            Validators.validate_decimal("9999999999999.99", "amount", max_digits=14, decimal_places=2)

    def test_too_many_decimal_places(self):
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_decimal("1.123", "amount", decimal_places=2)


class TestValidatorsDate:
    def test_valid_date_object(self):
        from apps.core.utils.validators import Validators

        d = date(2024, 1, 15)
        assert Validators.validate_date(d, "dt") == d

    def test_valid_datetime_converted(self):
        from apps.core.utils.validators import Validators

        dt = datetime(2024, 1, 15, 10, 30)
        result = Validators.validate_date(dt, "dt")
        assert result == date(2024, 1, 15)

    def test_valid_string_date(self):
        from apps.core.utils.validators import Validators

        result = Validators.validate_date("2024-01-15", "dt")
        assert result == date(2024, 1, 15)

    def test_none_returns_none(self):
        from apps.core.utils.validators import Validators

        assert Validators.validate_date(None, "dt") is None

    def test_invalid_string_format(self):
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_date("not-a-date", "dt")

    def test_invalid_type(self):
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_date(12345, "dt")

    def test_before_min_date(self):
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_date("2020-01-01", "dt", min_date=date(2024, 1, 1))

    def test_after_max_date(self):
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_date("2030-01-01", "dt", max_date=date(2025, 12, 31))


class TestValidatorsInChoices:
    def test_valid_choice(self):
        from apps.core.utils.validators import Validators

        assert Validators.validate_in_choices("a", "f", ["a", "b", "c"]) == "a"

    def test_none_with_allow_none(self):
        from apps.core.utils.validators import Validators

        assert Validators.validate_in_choices(None, "f", ["a", "b"], allow_none=True) is None

    def test_none_without_allow_none(self):
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_in_choices(None, "f", ["a", "b"], allow_none=False)

    def test_invalid_choice(self):
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_in_choices("z", "f", ["a", "b"])


class TestValidatorsUploadedFile:
    def test_valid_file(self):
        from apps.core.utils.validators import Validators

        f = Mock()
        f.name = "doc.pdf"
        f.size = 1024
        f.read.return_value = b"%PDF-1.4"
        f.seek = Mock()
        result = Validators.validate_uploaded_file(f, allowed_extensions=[".pdf"])
        assert result is f

    def test_no_file(self):
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_uploaded_file(None)

    def test_bad_extension(self):
        from apps.core.utils.validators import Validators

        f = Mock()
        f.name = "virus.exe"
        f.size = 100
        with pytest.raises(ValidationException):
            Validators.validate_uploaded_file(f, allowed_extensions=[".pdf"])

    def test_too_large_bytes(self):
        from apps.core.utils.validators import Validators

        f = Mock()
        f.name = "big.pdf"
        f.size = 10000
        with pytest.raises(ValidationException):
            Validators.validate_uploaded_file(f, max_size_bytes=5000)

    def test_too_large_mb(self):
        from apps.core.utils.validators import Validators

        f = Mock()
        f.name = "big.pdf"
        f.size = 20 * 1024 * 1024
        with pytest.raises(ValidationException):
            Validators.validate_uploaded_file(f, max_size_mb=10)

    def test_executable_rejected(self):
        from apps.core.utils.validators import Validators

        f = Mock()
        f.name = "program.pdf"
        f.size = 100
        f.read.return_value = b"MZ\x90\x00"
        f.seek = Mock()
        with pytest.raises(ValidationException):
            Validators.validate_uploaded_file(f)

    def test_elf_rejected(self):
        from apps.core.utils.validators import Validators

        f = Mock()
        f.name = "prog"
        f.size = 100
        f.read.return_value = b"\x7fELF"
        f.seek = Mock()
        with pytest.raises(ValidationException):
            Validators.validate_uploaded_file(f)


# ============================================================================
# filename_template_service.py tests
# ============================================================================


class TestFilenameTemplateRender:
    def test_render_basic(self):
        from apps.core.services.filename_template_service import FilenameTemplateService

        result = FilenameTemplateService._render(
            "{title}（{case_name}）_{date}",
            {"title", "case_name", "date"},
            title="起诉状",
            case_name="张某诉李某",
            date="20240101",
        )
        assert result == "起诉状（张某诉李某）_20240101"

    def test_render_preserves_unknown_placeholder(self):
        from apps.core.services.filename_template_service import FilenameTemplateService

        result = FilenameTemplateService._render(
            "{title}_{unknown}",
            {"title"},
            title="测试",
        )
        assert result == "测试_{unknown}"

    def test_render_no_placeholders(self):
        from apps.core.services.filename_template_service import FilenameTemplateService

        result = FilenameTemplateService._render("fixed_name", set())
        assert result == "fixed_name"


class TestGetUniqueFilepath:
    def test_no_conflict(self, tmp_path):
        from apps.core.services.filename_template_service import FilenameTemplateService

        filepath, name = FilenameTemplateService.get_unique_filepath(tmp_path, "test.pdf")
        assert name == "test.pdf"
        assert filepath == str(tmp_path / "test.pdf")

    def test_conflict_adds_counter(self, tmp_path):
        from apps.core.services.filename_template_service import FilenameTemplateService

        (tmp_path / "test.pdf").touch()
        filepath, name = FilenameTemplateService.get_unique_filepath(tmp_path, "test.pdf")
        assert name == "test_1.pdf"

    def test_multiple_conflicts(self, tmp_path):
        from apps.core.services.filename_template_service import FilenameTemplateService

        (tmp_path / "test.pdf").touch()
        (tmp_path / "test_1.pdf").touch()
        (tmp_path / "test_2.pdf").touch()
        filepath, name = FilenameTemplateService.get_unique_filepath(tmp_path, "test.pdf")
        assert name == "test_3.pdf"


# ============================================================================
# cases/utils.py tests
# ============================================================================


class TestCaseUtils:
    def test_basename_unix(self):
        from apps.cases.utils import _basename

        assert _basename("/path/to/file.txt") == "file.txt"

    def test_basename_windows(self):
        from apps.cases.utils import _basename

        assert _basename("C:\\Users\\file.txt") == "file.txt"

    def test_basename_empty(self):
        from apps.cases.utils import _basename

        assert _basename("") == ""

    def test_basename_no_path(self):
        from apps.cases.utils import _basename

        assert _basename("file.txt") == "file.txt"

    def test_get_file_extension_lower(self):
        from apps.cases.utils import get_file_extension_lower

        assert get_file_extension_lower("file.PDF") == ".pdf"
        assert get_file_extension_lower("file.tar.gz") == ".gz"
        assert get_file_extension_lower("noext") == ""
        assert get_file_extension_lower("") == ""
        assert get_file_extension_lower(".") == ""
        assert get_file_extension_lower("..") == ""

    def test_validate_case_log_attachment_valid(self):
        from apps.cases.utils import validate_case_log_attachment

        ok, msg = validate_case_log_attachment("file.pdf", 1024)
        assert ok is True
        assert msg is None

    def test_validate_case_log_attachment_invalid_ext(self):
        from apps.cases.utils import validate_case_log_attachment

        ok, msg = validate_case_log_attachment("file.exe", 1024)
        assert ok is False
        assert "不支持" in msg

    def test_normalize_case_number(self):
        from apps.cases.utils import normalize_case_number

        assert normalize_case_number("(2024)粤0606执386号") == "（2024）粤0606执386号"
        assert normalize_case_number("[2024]粤0606执386号") == "（2024）粤0606执386号"
        assert normalize_case_number("〔2024〕粤0606执386号") == "（2024）粤0606执386号"

    def test_normalize_case_number_ensure_hao(self):
        from apps.cases.utils import normalize_case_number

        result = normalize_case_number("(2024)粤0606执386", ensure_hao=True)
        assert result.endswith("号")

    def test_normalize_case_number_empty(self):
        from apps.cases.utils import normalize_case_number

        assert normalize_case_number("") == ""
        assert normalize_case_number("", ensure_hao=True) == ""


# ============================================================================
# cases/domain/validators.py tests
# ============================================================================


class TestCaseDomainValidators:
    def test_is_applicable_valid_types(self):
        from apps.cases.domain.validators import is_applicable

        assert is_applicable("civil") is True
        assert is_applicable("criminal") is True

    def test_is_applicable_none(self):
        from apps.cases.domain.validators import is_applicable

        assert is_applicable(None) is False

    def test_is_applicable_unknown(self):
        from apps.cases.domain.validators import is_applicable

        assert is_applicable("unknown_type") is False

    def test_normalize_stages_not_applicable_type(self):
        from apps.cases.domain.validators import normalize_stages

        rep, cur = normalize_stages(None, ["stage1"], None)
        assert rep == []
        assert cur is None

    def test_normalize_stages_strict_raises(self):
        from apps.cases.domain.validators import normalize_stages

        with pytest.raises(ValueError, match="stages_not_applicable"):
            normalize_stages(None, ["stage1"], None, strict=True)

    def test_normalize_stages_valid(self):
        from apps.cases.domain.validators import normalize_stages
        from apps.core.models.enums import CaseStage

        valid_stage = str(CaseStage.choices[0][0])
        rep, cur = normalize_stages("civil", [valid_stage], valid_stage)
        assert valid_stage in rep
        assert cur == valid_stage

    def test_normalize_stages_invalid_rep(self):
        from apps.cases.domain.validators import normalize_stages

        with pytest.raises(ValueError, match="invalid_rep"):
            normalize_stages("civil", ["zzz_invalid"], None)

    def test_normalize_stages_invalid_cur(self):
        from apps.cases.domain.validators import normalize_stages

        with pytest.raises(ValueError, match="invalid_cur"):
            normalize_stages("civil", [], "zzz_invalid")

    def test_normalize_stages_cur_not_in_rep(self):
        from apps.cases.domain.validators import normalize_stages
        from apps.core.models.enums import CaseStage

        stages = [str(c[0]) for c in CaseStage.choices]
        if len(stages) >= 2:
            with pytest.raises(ValueError, match="cur_not_in_rep"):
                normalize_stages("civil", [stages[0]], stages[1])


# ============================================================================
# contracts/domain/validators.py tests
# ============================================================================


class TestContractDomainValidators:
    def test_normalize_representation_stages_not_applicable(self):
        from apps.contracts.domain.validators import normalize_representation_stages

        result = normalize_representation_stages(None, ["stage1"])
        assert result == []

    def test_normalize_representation_stages_strict_raises(self):
        from apps.contracts.domain.validators import normalize_representation_stages

        with pytest.raises(ValidationException):
            normalize_representation_stages(None, ["stage1"], strict=True)

    def test_normalize_representation_stages_valid(self):
        from apps.contracts.domain.validators import normalize_representation_stages
        from apps.core.models.enums import CaseType

        result = normalize_representation_stages(CaseType.CIVIL, [])
        assert result == []

    def test_normalize_representation_stages_invalid(self):
        from apps.contracts.domain.validators import normalize_representation_stages
        from apps.core.models.enums import CaseType

        with pytest.raises(ValidationException):
            normalize_representation_stages(CaseType.CIVIL, ["zzz_invalid"])
