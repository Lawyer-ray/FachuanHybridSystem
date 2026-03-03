"""
BusinessConfig.is_stage_valid_for_case_type 边界条件测试

Requirements: 5.7
"""

import pytest

from apps.core.business_config import BusinessConfig, CaseTypeCode


@pytest.fixture
def config() -> BusinessConfig:
    return BusinessConfig()


# ==================== 正常路径 ====================


def test_valid_stage_for_matching_case_type(config: BusinessConfig) -> None:
    """有效阶段 + 匹配的案件类型 → True"""
    assert config.is_stage_valid_for_case_type("first_trial", CaseTypeCode.CIVIL) is True


def test_valid_stage_for_non_matching_case_type(config: BusinessConfig) -> None:
    """有效阶段 + 不匹配的案件类型 → False"""
    # labor_arbitration 只适用于 labor
    assert config.is_stage_valid_for_case_type("labor_arbitration", CaseTypeCode.CIVIL) is False


def test_valid_stage_for_correct_case_type(config: BusinessConfig) -> None:
    """有效阶段 + 正确案件类型 → True"""
    assert config.is_stage_valid_for_case_type("labor_arbitration", CaseTypeCode.LABOR) is True


def test_criminal_only_stage_for_civil(config: BusinessConfig) -> None:
    """刑事专用阶段 + 民事类型 → False"""
    assert config.is_stage_valid_for_case_type("investigation", CaseTypeCode.CIVIL) is False


def test_criminal_only_stage_for_criminal(config: BusinessConfig) -> None:
    """刑事专用阶段 + 刑事类型 → True"""
    assert config.is_stage_valid_for_case_type("investigation", CaseTypeCode.CRIMINAL) is True


# ==================== 边界条件 ====================


def test_invalid_stage_value(config: BusinessConfig) -> None:
    """不存在的阶段值 → False"""
    assert config.is_stage_valid_for_case_type("nonexistent_stage", CaseTypeCode.CIVIL) is False


def test_empty_string_stage(config: BusinessConfig) -> None:
    """空字符串阶段 → False"""
    assert config.is_stage_valid_for_case_type("", CaseTypeCode.CIVIL) is False


def test_none_case_type(config: BusinessConfig) -> None:
    """有效阶段 + None case_type → True（不限制类型时返回 True）"""
    assert config.is_stage_valid_for_case_type("first_trial", None) is True


def test_invalid_stage_with_none_case_type(config: BusinessConfig) -> None:
    """不存在的阶段 + None case_type → False"""
    assert config.is_stage_valid_for_case_type("nonexistent_stage", None) is False


def test_empty_string_case_type(config: BusinessConfig) -> None:
    """有效阶段 + 空字符串 case_type → True（空字符串是 falsy，等同于 None，不限制类型）"""
    assert config.is_stage_valid_for_case_type("first_trial", "") is True


def test_unknown_case_type(config: BusinessConfig) -> None:
    """有效阶段 + 未知 case_type → False"""
    assert config.is_stage_valid_for_case_type("first_trial", "unknown_type") is False


def test_all_valid_stages_for_civil(config: BusinessConfig) -> None:
    """civil 类型的所有有效阶段都应返回 True"""
    civil_stages = [s for s, _ in config.get_stages_for_case_type(CaseTypeCode.CIVIL)]
    for stage in civil_stages:
        assert (
            config.is_stage_valid_for_case_type(stage, CaseTypeCode.CIVIL) is True
        ), f"Stage {stage} should be valid for civil"


def test_enforcement_not_valid_for_criminal(config: BusinessConfig) -> None:
    """执行阶段不适用于刑事"""
    assert config.is_stage_valid_for_case_type("enforcement", CaseTypeCode.CRIMINAL) is False


def test_enforcement_valid_for_civil(config: BusinessConfig) -> None:
    """执行阶段适用于民事"""
    assert config.is_stage_valid_for_case_type("enforcement", CaseTypeCode.CIVIL) is True
