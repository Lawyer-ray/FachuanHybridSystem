"""
Automation 模块属性测试

**Feature: backend-perfect-score**

覆盖以下属性：
- Property A1: 案号规范化幂等性
- Property A2: 指数退避延迟单调性
- Property A3: 文本清洗不增加内容

**Validates: Requirements 8.1**
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.automation.tasking.retry_policy import ExponentialBackoffRetryPolicy
from apps.automation.utils.text_utils import TextUtils

# ── 策略 ──────────────────────────────────────────────────────────────────────

# 合法案号样本（用于测试规范化幂等性）
valid_case_numbers = st.sampled_from(
    [
        "（2025）粤0606执保38607号",
        "(2024)沪0101民初12345号",
        "〔2023〕京01民终999号",
        "[2022]苏0102执1234号",
        "（2021）浙0102刑初56号",
    ]
)

# 任意字符串（用于测试 clean_text 不增加内容）
arbitrary_text = st.text(max_size=500)

# 重试次数策略
retry_count_strategy = st.integers(min_value=0, max_value=20)

# 退避参数策略
backoff_params = st.fixed_dictionaries(
    {
        "base_seconds": st.integers(min_value=1, max_value=300),
        "max_seconds": st.integers(min_value=300, max_value=7200),
    }
)


# ── Property A1: 案号规范化幂等性 ─────────────────────────────────────────────


@given(case_number=valid_case_numbers)
@settings(max_examples=100)
def test_property_case_number_normalization_idempotent(case_number: str) -> None:
    """
    **Feature: backend-perfect-score, Property A1: 案号规范化幂等性**

    对任意案号字符串，normalize_case_number 应满足幂等性：
    连续调用两次的结果与调用一次相同。

    **Validates: Requirements 8.1**
    """
    once = TextUtils.normalize_case_number(case_number)
    twice = TextUtils.normalize_case_number(once)

    # 幂等性：f(f(x)) == f(x)
    assert once == twice, f"规范化不幂等: f('{case_number}') = '{once}', f(f(x)) = '{twice}'"


@given(case_number=valid_case_numbers)
@settings(max_examples=100)
def test_property_normalized_case_number_ends_with_hao(case_number: str) -> None:
    """
    **Feature: backend-perfect-score, Property A1: 案号规范化幂等性**

    规范化后的案号必须以"号"结尾（非空时）。

    **Validates: Requirements 8.1**
    """
    result = TextUtils.normalize_case_number(case_number)
    if result:
        assert result.endswith("号"), f"规范化案号未以'号'结尾: '{result}'"


# ── Property A2: 指数退避延迟单调性 ──────────────────────────────────────────


@given(
    base_seconds=st.integers(min_value=1, max_value=60),
    max_seconds=st.integers(min_value=60, max_value=3600),
    retry_count=retry_count_strategy,
)
@settings(max_examples=100)
def test_property_exponential_backoff_monotonic(base_seconds: int, max_seconds: int, retry_count: int) -> None:
    """
    **Feature: backend-perfect-score, Property A2: 指数退避延迟单调性**

    对任意合法参数，ExponentialBackoffRetryPolicy 的延迟应满足：
    1. 延迟 >= base_seconds
    2. 延迟 <= max_seconds
    3. 随 retry_count 增加，延迟不减少（单调非递减）

    **Validates: Requirements 8.1**
    """
    policy = ExponentialBackoffRetryPolicy(
        base_seconds=base_seconds,
        max_seconds=max_seconds,
    )

    delay = policy.compute_delay_seconds(retry_count=retry_count)

    # 延迟在合法范围内
    assert delay >= base_seconds, f"延迟 {delay} < base_seconds {base_seconds}"
    assert delay <= max_seconds, f"延迟 {delay} > max_seconds {max_seconds}"


@given(
    base_seconds=st.integers(min_value=1, max_value=60),
    max_seconds=st.integers(min_value=60, max_value=3600),
    n=st.integers(min_value=1, max_value=15),
)
@settings(max_examples=100)
def test_property_exponential_backoff_non_decreasing(base_seconds: int, max_seconds: int, n: int) -> None:
    """
    **Feature: backend-perfect-score, Property A2: 指数退避延迟单调性**

    retry_count 增加时，延迟不减少（单调非递减）。

    **Validates: Requirements 8.1**
    """
    policy = ExponentialBackoffRetryPolicy(
        base_seconds=base_seconds,
        max_seconds=max_seconds,
    )

    prev_delay = policy.compute_delay_seconds(retry_count=0)
    for i in range(1, n + 1):
        curr_delay = policy.compute_delay_seconds(retry_count=i)
        assert (
            curr_delay >= prev_delay
        ), f"retry_count={i} 的延迟 {curr_delay} < retry_count={i - 1} 的延迟 {prev_delay}"
        prev_delay = curr_delay


# ── Property A3: 文本清洗不增加内容 ──────────────────────────────────────────


@given(text=arbitrary_text)
@settings(max_examples=100)
def test_property_clean_text_does_not_increase_length(text: str) -> None:
    """
    **Feature: backend-perfect-score, Property A3: 文本清洗不增加内容**

    对任意文本，clean_text 的结果长度不超过原始文本长度。
    清洗只能减少或保持内容，不能增加。

    **Validates: Requirements 8.1**
    """
    result = TextUtils.clean_text(text)
    assert len(result) <= len(text), f"clean_text 增加了内容: 原始长度={len(text)}, 结果长度={len(result)}"


@given(text=arbitrary_text)
@settings(max_examples=100)
def test_property_clean_text_idempotent(text: str) -> None:
    """
    **Feature: backend-perfect-score, Property A3: 文本清洗不增加内容**

    clean_text 满足幂等性：连续调用两次结果相同。

    **Validates: Requirements 8.1**
    """
    once = TextUtils.clean_text(text)
    twice = TextUtils.clean_text(once)
    assert once == twice, "clean_text 不幂等: f(f(x)) != f(x)"
