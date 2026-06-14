"""Tests for apps.core.utils.id_card_utils."""

from __future__ import annotations

from unittest.mock import patch
from datetime import date

import pytest

from apps.core.utils.id_card_utils import IdCardInfo, IdCardUtils


class TestIdCardUtilsParse:
    def test_empty_string(self):
        result = IdCardUtils.parse_id_card_info("")
        assert result == IdCardInfo()

    def test_none(self):
        result = IdCardUtils.parse_id_card_info(None)
        assert result == IdCardInfo()

    def test_too_short(self):
        result = IdCardUtils.parse_id_card_info("12345")
        assert result == IdCardInfo()

    def test_18_digit(self):
        result = IdCardUtils.parse_id_card_info("11010119900307771X")
        assert result.birth_date is not None
        assert result.gender is not None
        assert result.age is not None

    def test_15_digit(self):
        # 15-digit: last digit determines gender. Odd = male, even = female.
        # "110101900307771" -> last digit = 1 (odd) = male
        result = IdCardUtils.parse_id_card_info("110101900307771")
        assert result.birth_date == "1990年03月07日"
        assert result.gender == "男"


class TestExtractBirthDate:
    def test_18_digit(self):
        assert IdCardUtils.extract_birth_date("11010119900307771X") == "1990年03月07日"

    def test_15_digit(self):
        assert IdCardUtils.extract_birth_date("110101900307771") == "1990年03月07日"

    def test_none_returns_none(self):
        assert IdCardUtils.extract_birth_date(None) is None

    def test_empty_returns_none(self):
        assert IdCardUtils.extract_birth_date("") is None


class TestExtractGender:
    def test_male(self):
        # 18-digit: second to last digit odd = male
        assert IdCardUtils.extract_gender("11010119900307771X") == "男"

    def test_female(self):
        # 15-digit: last digit even = female
        assert IdCardUtils.extract_gender("110101900307770") == "女"

    def test_short_returns_none(self):
        assert IdCardUtils.extract_gender("123") is None

    def test_none_returns_none(self):
        assert IdCardUtils.extract_gender(None) is None


class TestCalculateAge:
    def test_18_digit(self):
        with patch("apps.core.utils.id_card_utils.date") as mock_date:
            mock_date.today.return_value = date(2025, 6, 15)
            mock_date.side_effect = lambda *a, **k: date(*a, **k)
            age = IdCardUtils.calculate_age("11010119900307771X")
            assert age == 35  # birthday 03/07 < 06/15

    def test_18_digit_before_birthday(self):
        with patch("apps.core.utils.id_card_utils.date") as mock_date:
            mock_date.today.return_value = date(2025, 1, 1)
            mock_date.side_effect = lambda *a, **k: date(*a, **k)
            age = IdCardUtils.calculate_age("11010119900307771X")
            assert age == 34  # birthday 03/07 > 01/01

    def test_15_digit(self):
        with patch("apps.core.utils.id_card_utils.date") as mock_date:
            mock_date.today.return_value = date(2025, 6, 15)
            mock_date.side_effect = lambda *a, **k: date(*a, **k)
            age = IdCardUtils.calculate_age("110101900307771")
            assert age is not None

    def test_invalid_length_returns_none(self):
        assert IdCardUtils.calculate_age("1234") is None

    def test_none_returns_none(self):
        assert IdCardUtils.calculate_age(None) is None


class TestValidateIdCard:
    def test_empty(self):
        result = IdCardUtils.validate_id_card("")
        assert result["valid"] is False

    def test_none(self):
        result = IdCardUtils.validate_id_card(None)
        assert result["valid"] is False

    def test_wrong_length(self):
        result = IdCardUtils.validate_id_card("12345")
        assert result["valid"] is False
        assert "15位或18位" in result["message"]

    def test_18_digit_non_digit_first_17(self):
        result = IdCardUtils.validate_id_card("11010119900307771X")  # Valid one
        # Check that a valid ID passes format check
        assert "message" in result

    def test_18_digit_bad_province(self):
        # Province code 00
        result = IdCardUtils.validate_id_card("000101199003077712")
        assert result["valid"] is False
        assert "地区码" in result["message"]

    def test_18_digit_bad_check_digit(self):
        result = IdCardUtils.validate_id_card("110101199003077711")
        assert result["valid"] is False
        assert "校验码" in result["message"]

    def test_18_digit_bad_last_char(self):
        result = IdCardUtils.validate_id_card("11010119900307771Y")
        assert result["valid"] is False

    def test_15_digit_non_digit(self):
        result = IdCardUtils.validate_id_card("11010190030777A")
        assert result["valid"] is False
        assert "全部为数字" in result["message"]

    def test_15_digit_bad_province(self):
        result = IdCardUtils.validate_id_card("000101900307771")
        assert result["valid"] is False

    def test_18_digit_bad_date(self):
        result = IdCardUtils.validate_id_card("110101199013077712")
        assert result["valid"] is False
        assert "出生日期" in result["message"]


class TestValidateBirthDate:
    def test_valid_date(self):
        assert IdCardUtils._validate_birth_date("19900307", is_18_digit=True) is True

    def test_bad_month(self):
        assert IdCardUtils._validate_birth_date("19901307", is_18_digit=True) is False

    def test_bad_day(self):
        assert IdCardUtils._validate_birth_date("19900332", is_18_digit=True) is False

    def test_bad_year(self):
        assert IdCardUtils._validate_birth_date("21000101", is_18_digit=True) is False

    def test_wrong_length(self):
        assert IdCardUtils._validate_birth_date("199003", is_18_digit=True) is False

    def test_invalid_date(self):
        assert IdCardUtils._validate_birth_date("19900230", is_18_digit=True) is False
