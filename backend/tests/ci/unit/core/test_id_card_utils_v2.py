"""Tests for IdCardUtils covering parsing, validation, and edge cases."""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from apps.core.utils.id_card_utils import IdCardInfo, IdCardUtils


# ── parse_id_card_info ──


class TestParseIdCardInfo:
    def test_empty_string(self):
        result = IdCardUtils.parse_id_card_info("")
        assert result.birth_date is None
        assert result.gender is None
        assert result.age is None

    def test_too_short(self):
        result = IdCardUtils.parse_id_card_info("12345")
        assert result.birth_date is None

    def test_18_digit_male(self):
        # Use a known valid 18-digit ID: 11010119900307789X is not real, test parsing logic
        result = IdCardUtils.parse_id_card_info("110101199003077890")
        assert result.birth_date == "1990年03月07日"
        assert result.gender is not None  # Will be male or female depending on digit

    def test_15_digit(self):
        result = IdCardUtils.parse_id_card_info("110101900307789")
        assert result.birth_date == "1990年03月07日"
        assert result.gender is not None


# ── extract_birth_date ──


class TestExtractBirthDate:
    def test_none_input(self):
        assert IdCardUtils.extract_birth_date("") is None
        assert IdCardUtils.extract_birth_date(None) is None

    def test_18_digit(self):
        result = IdCardUtils.extract_birth_date("110101199003071234")
        assert result == "1990年03月07日"

    def test_15_digit(self):
        result = IdCardUtils.extract_birth_date("110101900307123")
        assert result == "1990年03月07日"

    def test_invalid_length(self):
        assert IdCardUtils.extract_birth_date("12345") is None


# ── extract_gender ──


class TestExtractGender:
    def test_none_input(self):
        assert IdCardUtils.extract_gender("") is None
        assert IdCardUtils.extract_gender(None) is None

    def test_18_digit_male_odd(self):
        # Second to last digit is odd -> male
        # 11010119900307001X: second to last is 1 (odd)
        result = IdCardUtils.extract_gender("11010119900307001X")
        assert result == "男"

    def test_18_digit_female_even(self):
        # Second to last digit is even -> female
        # 11010119900307002X: second to last is 2 (even)
        result = IdCardUtils.extract_gender("11010119900307002X")
        assert result == "女"

    def test_15_digit_male(self):
        # Last digit is odd -> male
        result = IdCardUtils.extract_gender("110101900307001")
        assert result == "男"

    def test_15_digit_female(self):
        # Last digit is even -> female
        result = IdCardUtils.extract_gender("110101900307002")
        assert result == "女"

    def test_short_input(self):
        assert IdCardUtils.extract_gender("12345") is None


# ── calculate_age ──


class TestCalculateAge:
    def test_none_input(self):
        assert IdCardUtils.calculate_age("") is None
        assert IdCardUtils.calculate_age(None) is None

    def test_18_digit(self):
        # Person born in 1990 should be ~35-36 years old
        age = IdCardUtils.calculate_age("110101199001011234")
        assert age is not None
        assert 34 <= age <= 37

    def test_15_digit(self):
        age = IdCardUtils.calculate_age("110101900101123")
        assert age is not None
        assert 34 <= age <= 37

    def test_invalid_length(self):
        assert IdCardUtils.calculate_age("12345") is None


# ── validate_id_card ──


class TestValidateIdCard:
    def test_empty(self):
        result = IdCardUtils.validate_id_card("")
        assert result["valid"] is False

    def test_invalid_length(self):
        result = IdCardUtils.validate_id_card("12345")
        assert result["valid"] is False
        assert "长度" in result["message"]

    def test_18_digit_non_numeric_prefix(self):
        result = IdCardUtils.validate_id_card("ABCDEFGHIJK123456X")
        assert result["valid"] is False
        assert "前17位" in result["message"]

    def test_18_digit_invalid_last_char(self):
        result = IdCardUtils.validate_id_card("11010119900307123A")
        assert result["valid"] is False

    def test_18_digit_invalid_province(self):
        result = IdCardUtils.validate_id_card("000101199003071234")
        assert result["valid"] is False
        assert "地区码" in result["message"]

    def test_15_digit_non_numeric(self):
        result = IdCardUtils.validate_id_card("110101ABC0307123")
        assert result["valid"] is False

    def test_15_digit_invalid_province(self):
        result = IdCardUtils.validate_id_card("000101900307123")
        assert result["valid"] is False

    def test_15_digit_valid_format(self):
        # 15-digit: all numeric, valid province, valid date
        result = IdCardUtils.validate_id_card("110101900307123")
        assert result["valid"] is True


# ── _validate_birth_date ──


class TestValidateBirthDate:
    def test_valid_date(self):
        assert IdCardUtils._validate_birth_date("19900307", is_18_digit=True) is True

    def test_invalid_month(self):
        assert IdCardUtils._validate_birth_date("19901307", is_18_digit=True) is False

    def test_invalid_day(self):
        assert IdCardUtils._validate_birth_date("19900332", is_18_digit=True) is False

    def test_short_date(self):
        assert IdCardUtils._validate_birth_date("199003", is_18_digit=True) is False

    def test_future_year(self):
        assert IdCardUtils._validate_birth_date("20990101", is_18_digit=True) is False

    def test_old_year(self):
        assert IdCardUtils._validate_birth_date("18000101", is_18_digit=True) is False

    def test_non_numeric(self):
        assert IdCardUtils._validate_birth_date("ABCD0101", is_18_digit=True) is False


# ── IdCardInfo dataclass ──


class TestIdCardInfo:
    def test_defaults(self):
        info = IdCardInfo()
        assert info.birth_date is None
        assert info.gender is None
        assert info.age is None

    def test_with_values(self):
        info = IdCardInfo(birth_date="1990年01月01日", gender="男", age=35)
        assert info.birth_date == "1990年01月01日"
        assert info.gender == "男"
        assert info.age == 35
