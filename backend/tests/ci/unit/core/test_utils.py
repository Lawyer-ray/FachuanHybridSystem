"""测试 core.utils 子模块

覆盖: validators.py, id_card_utils.py
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.core.exceptions import ValidationException


# ============================================================
# validators.py - Validators
# ============================================================


class TestValidatorsPhone:
    """测试手机号验证"""

    def test_valid_phone(self) -> None:
        from apps.core.utils.validators import Validators

        assert Validators.validate_phone("13812345678") == "13812345678"

    def test_phone_with_spaces(self) -> None:
        from apps.core.utils.validators import Validators

        assert Validators.validate_phone("  13812345678  ") == "13812345678"

    def test_none_phone(self) -> None:
        from apps.core.utils.validators import Validators

        assert Validators.validate_phone(None) is None

    def test_empty_phone(self) -> None:
        from apps.core.utils.validators import Validators

        assert Validators.validate_phone("") is None

    def test_invalid_phone(self) -> None:
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_phone("12345678901")  # 不以 1[3-9] 开头

    def test_short_phone(self) -> None:
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_phone("1381234567")  # 10位


class TestValidatorsEmail:
    """测试邮箱验证"""

    def test_valid_email(self) -> None:
        from apps.core.utils.validators import Validators

        assert Validators.validate_email("User@Example.COM") == "user@example.com"

    def test_none_email(self) -> None:
        from apps.core.utils.validators import Validators

        assert Validators.validate_email(None) is None

    def test_invalid_email(self) -> None:
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_email("not-an-email")


class TestValidatorsIdCard:
    """测试身份证验证"""

    def test_none_id_card(self) -> None:
        from apps.core.utils.validators import Validators

        assert Validators.validate_id_card(None) is None

    def test_invalid_format(self) -> None:
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_id_card("12345")  # 太短


class TestValidatorsRequired:
    """测试必填验证"""

    def test_required_pass(self) -> None:
        from apps.core.utils.validators import Validators

        assert Validators.validate_required("value", "field") == "value"

    def test_required_none(self) -> None:
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_required(None, "field")

    def test_required_empty_string(self) -> None:
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_required("   ", "field")


class TestValidatorsLength:
    """测试长度验证"""

    def test_length_pass(self) -> None:
        from apps.core.utils.validators import Validators

        assert Validators.validate_length("hello", "name", min_length=1, max_length=10) == "hello"

    def test_length_too_short(self) -> None:
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_length("ab", "name", min_length=5)

    def test_length_too_long(self) -> None:
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_length("a" * 100, "name", max_length=10)

    def test_length_none(self) -> None:
        from apps.core.utils.validators import Validators

        assert Validators.validate_length(None, "name") is None


class TestValidatorsRange:
    """测试范围验证"""

    def test_range_pass(self) -> None:
        from apps.core.utils.validators import Validators

        assert Validators.validate_range(50, "score", min_value=0, max_value=100) == 50

    def test_range_below_min(self) -> None:
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_range(-1, "score", min_value=0)

    def test_range_above_max(self) -> None:
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_range(101, "score", max_value=100)

    def test_range_none(self) -> None:
        from apps.core.utils.validators import Validators

        assert Validators.validate_range(None, "score") is None


class TestValidatorsDecimal:
    """测试 Decimal 验证"""

    def test_valid_decimal(self) -> None:
        from apps.core.utils.validators import Validators

        result = Validators.validate_decimal("123.45", "amount")
        assert result == Decimal("123.45")

    def test_none_decimal(self) -> None:
        from apps.core.utils.validators import Validators

        assert Validators.validate_decimal(None, "amount") is None

    def test_invalid_decimal(self) -> None:
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_decimal("not-a-number", "amount")

    def test_too_many_decimal_places(self) -> None:
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_decimal("1.123", "amount", decimal_places=2)


class TestValidatorsDate:
    """测试日期验证"""

    def test_date_from_string(self) -> None:
        from apps.core.utils.validators import Validators

        result = Validators.validate_date("2025-01-15", "date")
        assert result == date(2025, 1, 15)

    def test_date_from_date_object(self) -> None:
        from apps.core.utils.validators import Validators

        d = date(2025, 6, 1)
        assert Validators.validate_date(d, "date") == d

    def test_date_none(self) -> None:
        from apps.core.utils.validators import Validators

        assert Validators.validate_date(None, "date") is None

    def test_date_invalid_string(self) -> None:
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_date("not-a-date", "date")

    def test_date_before_min(self) -> None:
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_date("2020-01-01", "date", min_date=date(2025, 1, 1))

    def test_date_after_max(self) -> None:
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_date("2030-01-01", "date", max_date=date(2025, 12, 31))


class TestValidatorsChoices:
    """测试选项验证"""

    def test_valid_choice(self) -> None:
        from apps.core.utils.validators import Validators

        assert Validators.validate_in_choices("a", "type", ["a", "b", "c"]) == "a"

    def test_invalid_choice(self) -> None:
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_in_choices("d", "type", ["a", "b", "c"])

    def test_none_allowed(self) -> None:
        from apps.core.utils.validators import Validators

        assert Validators.validate_in_choices(None, "type", ["a"], allow_none=True) is None

    def test_none_not_allowed(self) -> None:
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_in_choices(None, "type", ["a"], allow_none=False)


class TestValidatorsUploadedFile:
    """测试上传文件验证"""

    def test_valid_file(self) -> None:
        from apps.core.utils.validators import Validators

        f = SimpleNamespace(name="doc.pdf", size=1024, read=MagicMock(return_value=b"\x25\x50\x44\x46"), seek=MagicMock())
        result = Validators.validate_uploaded_file(f, allowed_extensions=[".pdf"])
        assert result is f

    def test_no_file(self) -> None:
        from apps.core.utils.validators import Validators

        with pytest.raises(ValidationException):
            Validators.validate_uploaded_file(None)

    def test_wrong_extension(self) -> None:
        from apps.core.utils.validators import Validators

        f = SimpleNamespace(name="malware.exe", size=1024, read=MagicMock(return_value=b"\x00\x00"), seek=MagicMock())
        with pytest.raises(ValidationException):
            Validators.validate_uploaded_file(f, allowed_extensions=[".pdf", ".docx"])

    def test_file_too_large(self) -> None:
        from apps.core.utils.validators import Validators

        f = SimpleNamespace(name="big.pdf", size=20 * 1024 * 1024, read=MagicMock(return_value=b"\x25\x50\x44\x46"), seek=MagicMock())
        with pytest.raises(ValidationException):
            Validators.validate_uploaded_file(f, max_size_mb=10)

    def test_executable_rejected(self) -> None:
        from apps.core.utils.validators import Validators

        f = SimpleNamespace(name="virus.exe", size=1024, read=MagicMock(return_value=b"MZ\x90\x00"), seek=MagicMock())
        with pytest.raises(ValidationException, match="可执行文件"):
            Validators.validate_uploaded_file(f)


# ============================================================
# id_card_utils.py
# ============================================================


class TestIdCardUtils:
    """测试身份证号码解析工具"""

    def test_parse_id_card_info_empty(self) -> None:
        from apps.core.utils.id_card_utils import IdCardUtils

        info = IdCardUtils.parse_id_card_info("")
        assert info.birth_date is None

    def test_parse_id_card_info_short(self) -> None:
        from apps.core.utils.id_card_utils import IdCardUtils

        info = IdCardUtils.parse_id_card_info("123")
        assert info.birth_date is None

    def test_extract_birth_date_18_digit(self) -> None:
        from apps.core.utils.id_card_utils import IdCardUtils

        result = IdCardUtils.extract_birth_date("110101199003071234")
        assert result == "1990年03月07日"

    def test_extract_birth_date_15_digit(self) -> None:
        from apps.core.utils.id_card_utils import IdCardUtils

        result = IdCardUtils.extract_birth_date("110101900307123")
        assert result == "1990年03月07日"

    def test_extract_birth_date_empty(self) -> None:
        from apps.core.utils.id_card_utils import IdCardUtils

        assert IdCardUtils.extract_birth_date("") is None
        assert IdCardUtils.extract_birth_date(None) is None  # type: ignore[arg-type]

    def test_extract_gender_male(self) -> None:
        from apps.core.utils.id_card_utils import IdCardUtils

        # 倒数第二位为奇数 = 男
        assert IdCardUtils.extract_gender("110101199003071234") == "男"

    def test_extract_gender_female(self) -> None:
        from apps.core.utils.id_card_utils import IdCardUtils

        # 倒数第二位为偶数 = 女
        assert IdCardUtils.extract_gender("110101199003072244") == "女"

    def test_extract_gender_short(self) -> None:
        from apps.core.utils.id_card_utils import IdCardUtils

        assert IdCardUtils.extract_gender("123") is None

    def test_calculate_age_18_digit(self) -> None:
        from apps.core.utils.id_card_utils import IdCardUtils

        age = IdCardUtils.calculate_age("110101199003071234")
        assert age is not None
        assert age >= 30  # 2025 - 1990 >= 35 (近似)

    def test_calculate_age_none(self) -> None:
        from apps.core.utils.id_card_utils import IdCardUtils

        assert IdCardUtils.calculate_age(None) is None  # type: ignore[arg-type]
        assert IdCardUtils.calculate_age("") is None

    def test_validate_id_card_empty(self) -> None:
        from apps.core.utils.id_card_utils import IdCardUtils

        result = IdCardUtils.validate_id_card("")
        assert result["valid"] is False

    def test_validate_id_card_wrong_length(self) -> None:
        from apps.core.utils.id_card_utils import IdCardUtils

        result = IdCardUtils.validate_id_card("12345")
        assert result["valid"] is False

    def test_validate_id_card_15_digit_valid(self) -> None:
        from apps.core.utils.id_card_utils import IdCardUtils

        result = IdCardUtils.validate_id_card("110101900307123")
        # 15位全数字 + 有效地区码 + 有效日期 => valid
        assert result["valid"] is True

    def test_validate_id_card_18_digit_non_digit(self) -> None:
        from apps.core.utils.id_card_utils import IdCardUtils

        result = IdCardUtils.validate_id_card("11010119900307abcd")
        assert result["valid"] is False

    def test_validate_birth_date_valid(self) -> None:
        from apps.core.utils.id_card_utils import IdCardUtils

        assert IdCardUtils._validate_birth_date("20000101", is_18_digit=True) is True

    def test_validate_birth_date_invalid_month(self) -> None:
        from apps.core.utils.id_card_utils import IdCardUtils

        assert IdCardUtils._validate_birth_date("20001301", is_18_digit=True) is False

    def test_validate_birth_date_invalid_day(self) -> None:
        from apps.core.utils.id_card_utils import IdCardUtils

        assert IdCardUtils._validate_birth_date("20000132", is_18_digit=True) is False

    def test_validate_birth_date_short(self) -> None:
        from apps.core.utils.id_card_utils import IdCardUtils

        assert IdCardUtils._validate_birth_date("2000", is_18_digit=True) is False
