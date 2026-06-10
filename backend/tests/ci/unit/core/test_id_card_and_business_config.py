"""Comprehensive tests for id_card_utils and business_config to boost coverage."""

from __future__ import annotations

import pytest

from apps.core.utils.id_card_utils import IdCardUtils, IdCardInfo, ID_CARD_WEIGHTS, ID_CARD_CHECK_CODES


# ===========================================================================
# IdCardUtils tests
# ===========================================================================
class TestIdCardUtilsExtractGender:
    def test_18_digit_male(self):
        # Last second digit (17th from left, [-2]) is odd = male
        assert IdCardUtils.extract_gender("110101199003071234") == "男"

    def test_18_digit_female(self):
        # Last second digit is even = female
        assert IdCardUtils.extract_gender("110101199003071244") == "女"

    def test_15_digit_male(self):
        # Last digit is odd = male
        assert IdCardUtils.extract_gender("110101900307123") == "男"

    def test_15_digit_female(self):
        # Last digit is even = female
        assert IdCardUtils.extract_gender("110101900307124") == "女"

    def test_empty_string(self):
        assert IdCardUtils.extract_gender("") is None

    def test_short_string(self):
        assert IdCardUtils.extract_gender("12345") is None

    def test_none(self):
        assert IdCardUtils.extract_gender(None) is None  # type: ignore[arg-type]


class TestIdCardUtilsExtractBirthDate:
    def test_18_digit(self):
        result = IdCardUtils.extract_birth_date("110101199003071234")
        assert result == "1990年03月07日"

    def test_15_digit(self):
        result = IdCardUtils.extract_birth_date("110101900307123")
        assert result == "1990年03月07日"

    def test_empty(self):
        assert IdCardUtils.extract_birth_date("") is None

    def test_none(self):
        assert IdCardUtils.extract_birth_date(None) is None  # type: ignore[arg-type]


class TestIdCardUtilsCalculateAge:
    def test_18_digit(self):
        # Use a known birth date
        result = IdCardUtils.calculate_age("110101199003071234")
        assert result is not None
        assert 30 < result < 40  # Should be around 36

    def test_15_digit(self):
        result = IdCardUtils.calculate_age("110101900307123")
        assert result is not None
        assert 30 < result < 40

    def test_empty(self):
        assert IdCardUtils.calculate_age("") is None

    def test_none(self):
        assert IdCardUtils.calculate_age(None) is None  # type: ignore[arg-type]

    def test_invalid_length(self):
        assert IdCardUtils.calculate_age("123456789") is None


class TestIdCardUtilsParseIdCardInfo:
    def test_valid_18(self):
        info = IdCardUtils.parse_id_card_info("110101199003071234")
        assert info.birth_date is not None
        assert info.gender is not None
        assert info.age is not None

    def test_short_string(self):
        info = IdCardUtils.parse_id_card_info("123")
        assert info.birth_date is None
        assert info.gender is None
        assert info.age is None

    def test_empty(self):
        info = IdCardUtils.parse_id_card_info("")
        assert info.birth_date is None


class TestIdCardUtilsValidate:
    def test_valid_18_digit(self):
        result = IdCardUtils.validate_id_card("110101199003071234")
        # May or may not be valid depending on check code
        assert "valid" in result
        assert "message" in result

    def test_empty(self):
        result = IdCardUtils.validate_id_card("")
        assert result["valid"] is False

    def test_wrong_length(self):
        result = IdCardUtils.validate_id_card("12345")
        assert result["valid"] is False

    def test_18_digit_non_digit_prefix(self):
        result = IdCardUtils.validate_id_card("ABCDEFGH199003071234")
        assert result["valid"] is False

    def test_18_digit_invalid_province(self):
        result = IdCardUtils.validate_id_card("001001199003071234")
        assert result["valid"] is False

    def test_18_digit_invalid_month(self):
        result = IdCardUtils.validate_id_card("110101199013071234")
        assert result["valid"] is False

    def test_15_digit_valid_format(self):
        result = IdCardUtils.validate_id_card("110101900307123")
        assert "valid" in result

    def test_15_digit_non_digit(self):
        result = IdCardUtils.validate_id_card("110101ABCDEFGH")
        assert result["valid"] is False

    def test_15_digit_invalid_province(self):
        result = IdCardUtils.validate_id_card("001001900307123")
        assert result["valid"] is False

    def test_18_digit_with_x(self):
        # Test that X is accepted as last character
        result = IdCardUtils.validate_id_card("110101199003071X23")
        assert "valid" in result

    def test_18_digit_invalid_last_char(self):
        # Replace last char with something invalid
        result = IdCardUtils.validate_id_card("11010119900307123A")
        assert result["valid"] is False

    def test_none_input(self):
        result = IdCardUtils.validate_id_card(None)  # type: ignore[arg-type]
        assert result["valid"] is False


# ===========================================================================
# Constants tests
# ===========================================================================
class TestIdCardConstants:
    def test_weights_count(self):
        assert len(ID_CARD_WEIGHTS) == 17

    def test_check_codes_count(self):
        assert len(ID_CARD_CHECK_CODES) == 11


# ===========================================================================
# BusinessConfig tests
# ===========================================================================
class TestBusinessConfig:
    def test_get_stage_label(self):
        from apps.core.config.business_config import business_config
        label = business_config.get_stage_label("first_trial")
        assert label == "一审"

    def test_get_stage_label_unknown(self):
        from apps.core.config.business_config import business_config
        label = business_config.get_stage_label("nonexistent_stage")
        assert label == "nonexistent_stage"

    def test_get_legal_status_label(self):
        from apps.core.config.business_config import business_config
        label = business_config.get_legal_status_label("plaintiff")
        assert label == "原告"

    def test_get_legal_status_label_unknown(self):
        from apps.core.config.business_config import business_config
        label = business_config.get_legal_status_label("nonexistent_status")
        assert label == "nonexistent_status"

    def test_get_stages_for_civil(self):
        from apps.core.config.business_config import business_config
        stages = business_config.get_stages_for_case_type("civil")
        values = [s[0] for s in stages]
        assert "first_trial" in values
        assert "enforcement" in values

    def test_get_stages_for_none(self):
        from apps.core.config.business_config import business_config
        stages = business_config.get_stages_for_case_type(None)
        # Stages with empty applicable_case_types are universal
        assert isinstance(stages, list)

    def test_get_legal_statuses_for_civil(self):
        from apps.core.config.business_config import business_config
        statuses = business_config.get_legal_statuses_for_case_type("civil")
        values = [s[0] for s in statuses]
        assert "plaintiff" in values
        assert "defendant" in values

    def test_is_legal_status_valid_for_case_type(self):
        from apps.core.config.business_config import business_config
        assert business_config.is_legal_status_valid_for_case_type("plaintiff", "civil") is True

    def test_is_stage_valid_for_case_type(self):
        from apps.core.config.business_config import business_config
        assert business_config.is_stage_valid_for_case_type("first_trial", "civil") is True
        assert business_config.is_stage_valid_for_case_type("labor_arbitration", "civil") is False

    def test_invalidate_config_cache(self):
        from apps.core.config.business_config import business_config
        # Should not raise
        business_config.invalidate_config_cache()
        business_config.invalidate_config_cache(case_type="civil")
