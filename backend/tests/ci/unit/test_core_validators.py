"""Tests for apps.core.utils.validators — covering all branches."""

from __future__ import annotations

import io
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from apps.core.exceptions import ValidationException
from apps.core.utils.validators import Validators


# ---------- validate_phone ----------

class TestValidatePhone:
    def test_none_returns_none(self):
        assert Validators.validate_phone(None) is None

    def test_empty_string_returns_none(self):
        assert Validators.validate_phone("") is None
        assert Validators.validate_phone("   ") is None

    def test_valid_phone(self):
        assert Validators.validate_phone("13800138000") == "13800138000"

    def test_valid_phone_with_spaces(self):
        assert Validators.validate_phone(" 13800138000 ") == "13800138000"

    def test_invalid_phone(self):
        with pytest.raises(ValidationException, match="手机号码格式不正确"):
            Validators.validate_phone("1234567890")

    def test_invalid_phone_short(self):
        with pytest.raises(ValidationException, match="手机号码格式不正确"):
            Validators.validate_phone("1380013800")


# ---------- validate_email ----------

class TestValidateEmail:
    def test_none_returns_none(self):
        assert Validators.validate_email(None) is None

    def test_empty_returns_none(self):
        assert Validators.validate_email("") is None

    def test_valid_email(self):
        result = Validators.validate_email("Test@Example.com")
        assert result == "test@example.com"

    def test_invalid_email(self):
        with pytest.raises(ValidationException, match="邮箱格式不正确"):
            Validators.validate_email("not-an-email")


# ---------- validate_id_card ----------

class TestValidateIdCard:
    def test_none_returns_none(self):
        assert Validators.validate_id_card(None) is None

    def test_empty_returns_none(self):
        assert Validators.validate_id_card("") is None

    def test_valid_id_card_with_checksum(self):
        # 11010519900307771X has an incorrect checksum; use a known-valid one.
        # 11010519900307771X -> checksum should be X but let's compute.
        # Instead use a well-tested valid ID: 11010119800101001X
        # Actually let's just use a known-valid: 440306199208121230
        # We'll test the checksum path works by testing that a valid ID passes.
        # Let's use 11010519900307771X and see what the correct checksum is:
        weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
        check_codes = "10X98765432"
        id_base = "11010519900307771"
        total = sum(int(id_base[i]) * weights[i] for i in range(17))
        correct_check = check_codes[total % 11]
        valid_id = id_base + correct_check
        result = Validators.validate_id_card(valid_id)
        assert result == valid_id

    def test_invalid_checksum(self):
        with pytest.raises(ValidationException, match="校验失败"):
            Validators.validate_id_card("110101199001011234")

    def test_bad_format(self):
        with pytest.raises(ValidationException, match="格式不正确"):
            Validators.validate_id_card("abc")


# ---------- validate_social_credit_code ----------

class TestValidateSocialCreditCode:
    def test_none_returns_none(self):
        assert Validators.validate_social_credit_code(None) is None

    def test_valid_code(self):
        code = "91110108MA01Y4AB5Q"
        result = Validators.validate_social_credit_code(code)
        assert result == "91110108MA01Y4AB5Q"

    def test_invalid_code(self):
        with pytest.raises(ValidationException):
            Validators.validate_social_credit_code("INVALID123")


# ---------- validate_required ----------

class TestValidateRequired:
    def test_none_raises(self):
        with pytest.raises(ValidationException, match="不能为空"):
            Validators.validate_required(None, "field")

    def test_empty_string_raises(self):
        with pytest.raises(ValidationException, match="不能为空"):
            Validators.validate_required("  ", "field")

    def test_valid_value(self):
        assert Validators.validate_required("hello", "field") == "hello"

    def test_zero_is_valid(self):
        assert Validators.validate_required(0, "field") == 0


# ---------- validate_length ----------

class TestValidateLength:
    def test_none_returns_none(self):
        assert Validators.validate_length(None, "f") is None

    def test_empty_returns_none(self):
        assert Validators.validate_length("", "f") is None

    def test_too_short(self):
        with pytest.raises(ValidationException, match="长度不足"):
            Validators.validate_length("ab", "f", min_length=3)

    def test_too_long(self):
        with pytest.raises(ValidationException, match="长度超限"):
            Validators.validate_length("abcd", "f", max_length=3)

    def test_in_range(self):
        assert Validators.validate_length("abc", "f", min_length=2, max_length=5) == "abc"


# ---------- validate_range ----------

class TestValidateRange:
    def test_none_returns_none(self):
        assert Validators.validate_range(None, "f") is None

    def test_below_min(self):
        with pytest.raises(ValidationException, match="值过小"):
            Validators.validate_range(5, "f", min_value=10)

    def test_above_max(self):
        with pytest.raises(ValidationException, match="值过大"):
            Validators.validate_range(100, "f", max_value=50)

    def test_in_range(self):
        assert Validators.validate_range(15, "f", min_value=10, max_value=20) == 15


# ---------- validate_decimal ----------

class TestValidateDecimal:
    def test_none_returns_none(self):
        assert Validators.validate_decimal(None, "f") is None

    def test_valid_decimal(self):
        result = Validators.validate_decimal("123.45", "f")
        assert result == Decimal("123.45")

    def test_invalid_string(self):
        with pytest.raises(ValidationException, match="格式不正确"):
            Validators.validate_decimal("abc", "f")

    def test_too_many_decimal_places(self):
        with pytest.raises(ValidationException, match="小数位数过多"):
            Validators.validate_decimal("1.23456", "f", decimal_places=2)

    def test_too_many_integer_digits(self):
        with pytest.raises(ValidationException, match="数值过大"):
            Validators.validate_decimal("123456789012345.00", "f", max_digits=14, decimal_places=2)


# ---------- validate_date ----------

class TestValidateDate:
    def test_none_returns_none(self):
        assert Validators.validate_date(None, "f") is None

    def test_string_date(self):
        from datetime import date
        result = Validators.validate_date("2024-01-15", "f")
        assert result == date(2024, 1, 15)

    def test_invalid_string_format(self):
        with pytest.raises(ValidationException, match="格式不正确"):
            Validators.validate_date("15-01-2024", "f")

    def test_datetime_converted_to_date(self):
        from datetime import date, datetime
        result = Validators.validate_date(datetime(2024, 1, 15, 12, 0), "f")
        assert result == date(2024, 1, 15)

    def test_invalid_type(self):
        with pytest.raises(ValidationException, match="类型不正确"):
            Validators.validate_date(12345, "f")

    def test_before_min_date(self):
        from datetime import date
        with pytest.raises(ValidationException, match="日期过早"):
            Validators.validate_date("2020-01-01", "f", min_date=date(2021, 1, 1))

    def test_after_max_date(self):
        from datetime import date
        with pytest.raises(ValidationException, match="日期过晚"):
            Validators.validate_date("2030-01-01", "f", max_date=date(2025, 1, 1))


# ---------- validate_in_choices ----------

class TestValidateInChoices:
    def test_none_allowed(self):
        assert Validators.validate_in_choices(None, "f", ["a", "b"]) is None

    def test_none_not_allowed(self):
        with pytest.raises(ValidationException, match="不能为空"):
            Validators.validate_in_choices(None, "f", ["a", "b"], allow_none=False)

    def test_valid_choice(self):
        assert Validators.validate_in_choices("a", "f", ["a", "b"]) == "a"

    def test_invalid_choice(self):
        with pytest.raises(ValidationException, match="值无效"):
            Validators.validate_in_choices("c", "f", ["a", "b"])


# ---------- validate_uploaded_file ----------

class TestValidateUploadedFile:
    def _make_file(self, name="test.pdf", size=1024, content=b"\x00" * 8):
        f = MagicMock()
        f.name = name
        f.size = size
        f.read.return_value = content
        return f

    def test_none_file_raises(self):
        with pytest.raises(ValidationException):
            Validators.validate_uploaded_file(None)

    def test_invalid_extension(self):
        f = self._make_file("test.exe")
        with pytest.raises(ValidationException, match="不支持的文件格式"):
            Validators.validate_uploaded_file(f, allowed_extensions=[".pdf", ".jpg"])

    def test_valid_extension(self):
        f = self._make_file("test.pdf")
        result = Validators.validate_uploaded_file(f, allowed_extensions=[".pdf", ".jpg"])
        assert result is f

    def test_extension_without_dot(self):
        f = self._make_file("test.unknown")
        with pytest.raises(ValidationException):
            Validators.validate_uploaded_file(f, allowed_extensions=[".pdf"])

    def test_size_exceeds_mb(self):
        f = self._make_file(size=2 * 1024 * 1024)
        with pytest.raises(ValidationException, match="文件大小超限"):
            Validators.validate_uploaded_file(f, max_size_mb=1)

    def test_size_exceeds_bytes(self):
        f = self._make_file(size=2000)
        with pytest.raises(ValidationException, match="文件大小超限"):
            Validators.validate_uploaded_file(f, max_size_bytes=1000)

    def test_executable_magic_detected(self):
        f = self._make_file(content=b"MZ\x90\x00" + b"\x00" * 4)
        with pytest.raises(ValidationException, match="可执行文件"):
            Validators.validate_uploaded_file(f)

    def test_elf_magic_detected(self):
        f = self._make_file(content=b"\x7fELF" + b"\x00" * 4)
        with pytest.raises(ValidationException, match="可执行文件"):
            Validators.validate_uploaded_file(f)

    def test_no_read_method_gracefully_handled(self):
        f = MagicMock()
        f.name = "test.pdf"
        f.size = 100
        del f.read  # No read method
        result = Validators.validate_uploaded_file(f)
        assert result is f

    def test_no_extension_file(self):
        f = self._make_file("noext")
        # No extension detected -> ext="" -> not in allowed_extensions
        with pytest.raises(ValidationException):
            Validators.validate_uploaded_file(f, allowed_extensions=[".pdf"])
