"""Tests for core utils.id_card_utils module."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from apps.core.utils.id_card_utils import (
    ID_CARD_CHECK_CODES,
    ID_CARD_WEIGHTS,
    IdCardInfo,
    IdCardUtils,
)


class TestIdCardInfo:
    def test_defaults(self) -> None:
        info = IdCardInfo()
        assert info.birth_date is None
        assert info.gender is None
        assert info.age is None

    def test_with_values(self) -> None:
        info = IdCardInfo(birth_date="1990年01月01日", gender="男", age=34)
        assert info.birth_date == "1990年01月01日"


class TestIdCardUtilsParseIdCardInfo:
    def test_empty(self) -> None:
        info = IdCardUtils.parse_id_card_info("")
        assert info.birth_date is None
        assert info.gender is None
        assert info.age is None

    def test_too_short(self) -> None:
        info = IdCardUtils.parse_id_card_info("12345")
        assert info.birth_date is None

    def test_18_digit(self) -> None:
        # Use a valid-looking 18-digit ID card (Beijing, male born 1990-01-01)
        # 11010119900101001X is not valid check code but format is correct
        info = IdCardUtils.parse_id_card_info("110101199001010011")
        assert info.birth_date == "1990年01月01日"

    def test_15_digit(self) -> None:
        info = IdCardUtils.parse_id_card_info("110101900101001")
        assert info.birth_date == "1990年01月01日"


class TestIdCardUtilsExtractBirthDate:
    def test_none(self) -> None:
        assert IdCardUtils.extract_birth_date(None) is None  # type: ignore[arg-type]

    def test_empty(self) -> None:
        assert IdCardUtils.extract_birth_date("") is None

    def test_18_digit(self) -> None:
        result = IdCardUtils.extract_birth_date("11010119900101001X")
        assert result == "1990年01月01日"

    def test_15_digit(self) -> None:
        result = IdCardUtils.extract_birth_date("110101900101001")
        assert result == "1990年01月01日"

    def test_unsupported_length(self) -> None:
        assert IdCardUtils.extract_birth_date("12345") is None


class TestIdCardUtilsExtractGender:
    def test_none(self) -> None:
        assert IdCardUtils.extract_gender(None) is None  # type: ignore[arg-type]

    def test_too_short(self) -> None:
        assert IdCardUtils.extract_gender("12345") is None

    def test_18_digit_male(self) -> None:
        # Second to last digit odd = male
        result = IdCardUtils.extract_gender("11010119900101001X")
        # last char X -> second to last is 1 -> odd -> male
        assert result == "男"

    def test_18_digit_female(self) -> None:
        # Second to last digit even = female
        result = IdCardUtils.extract_gender("11010119900101002X")
        assert result == "女"

    def test_15_digit_male(self) -> None:
        # Last digit odd = male
        result = IdCardUtils.extract_gender("110101900101001")
        assert result == "男"

    def test_15_digit_female(self) -> None:
        result = IdCardUtils.extract_gender("110101900101002")
        assert result == "女"


class TestIdCardUtilsCalculateAge:
    def test_none(self) -> None:
        assert IdCardUtils.calculate_age(None) is None  # type: ignore[arg-type]

    def test_empty(self) -> None:
        assert IdCardUtils.calculate_age("") is None

    def test_unsupported_length(self) -> None:
        assert IdCardUtils.calculate_age("12345") is None

    def test_18_digit(self) -> None:
        # Use a date in the past to ensure positive age
        result = IdCardUtils.calculate_age("11010119900101001X")
        assert result is not None
        assert result > 30

    def test_15_digit(self) -> None:
        result = IdCardUtils.calculate_age("110101900101001")
        assert result is not None
        assert result > 30


class TestIdCardUtilsValidateIdCard:
    def test_empty(self) -> None:
        result = IdCardUtils.validate_id_card("")
        assert result["valid"] is False
        assert "不能为空" in result["message"]

    def test_wrong_length(self) -> None:
        result = IdCardUtils.validate_id_card("12345")
        assert result["valid"] is False
        assert "长度" in result["message"]

    def test_18_digit_non_digit_first_17(self) -> None:
        result = IdCardUtils.validate_id_card("1101011990010100AX")
        assert result["valid"] is False

    def test_18_digit_invalid_last_char(self) -> None:
        result = IdCardUtils.validate_id_card("11010119900101001A")
        assert result["valid"] is False

    def test_18_digit_invalid_province(self) -> None:
        result = IdCardUtils.validate_id_card("990101199001010010")
        assert result["valid"] is False
        assert "地区码" in result["message"]

    def test_18_digit_invalid_date(self) -> None:
        result = IdCardUtils.validate_id_card("110101199013010010")
        assert result["valid"] is False
        assert "出生日期" in result["message"]

    def test_15_digit_non_digit(self) -> None:
        result = IdCardUtils.validate_id_card("11010190010100A")
        assert result["valid"] is False

    def test_15_digit_invalid_province(self) -> None:
        result = IdCardUtils.validate_id_card("990101900101001")
        assert result["valid"] is False

    def test_15_digit_invalid_date(self) -> None:
        result = IdCardUtils.validate_id_card("110101901301001")
        assert result["valid"] is False


class TestIdCardUtilsValidateBirthDate:
    def test_valid_date(self) -> None:
        assert IdCardUtils._validate_birth_date("19900101", is_18_digit=True) is True

    def test_invalid_month(self) -> None:
        assert IdCardUtils._validate_birth_date("19901301", is_18_digit=True) is False

    def test_invalid_day(self) -> None:
        assert IdCardUtils._validate_birth_date("19900132", is_18_digit=True) is False

    def test_wrong_length(self) -> None:
        assert IdCardUtils._validate_birth_date("199001", is_18_digit=True) is False

    def test_year_too_old(self) -> None:
        assert IdCardUtils._validate_birth_date("18000101", is_18_digit=True) is False

    def test_future_year(self) -> None:
        assert IdCardUtils._validate_birth_date("20990101", is_18_digit=True) is False

    def test_invalid_date_feb_30(self) -> None:
        assert IdCardUtils._validate_birth_date("19900230", is_18_digit=True) is False


class TestIdCardConstants:
    def test_weights_length(self) -> None:
        assert len(ID_CARD_WEIGHTS) == 17

    def test_check_codes_length(self) -> None:
        assert len(ID_CARD_CHECK_CODES) == 11
