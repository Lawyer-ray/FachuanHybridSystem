"""
属性测试：案号格式化幂等性

# Feature: cases-quality-uplift, Property 6: 案号格式化 round-trip

使用 Hypothesis 生成随机案号字符串，验证 normalize_case_number 的幂等性：
对已格式化的字符串再次调用应返回相同结果。
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from apps.cases.utils import normalize_case_number

# ---------------------------------------------------------------------------
# 生成策略：包含各种括号、空格、全角字符的案号字符串
# ---------------------------------------------------------------------------

# 常见案号组成字符
_BRACKET_CHARS: str = "()（）〔〕[]"
_SPACE_CHARS: str = " \u3000"  # 半角空格 + 全角空格
_DIGIT_CHARS: str = "0123456789"
_COMMON_CHARS: str = "京沪粤苏浙鲁民初终号字第刑行执破赔仲"

_CASE_NUMBER_ALPHABET: str = (
    _BRACKET_CHARS + _SPACE_CHARS + _DIGIT_CHARS + _COMMON_CHARS
)

case_number_strategy: st.SearchStrategy[str] = st.text(
    alphabet=_CASE_NUMBER_ALPHABET,
    min_size=0,
    max_size=60,
)


# ---------------------------------------------------------------------------
# Property 6: 案号格式化 round-trip（幂等性）
# Feature: cases-quality-uplift, Property 6: 案号格式化 round-trip
# ---------------------------------------------------------------------------


@given(raw=case_number_strategy, ensure_hao=st.booleans())
@settings(max_examples=200)
def test_property_normalize_case_number_idempotent(
    raw: str,
    ensure_hao: bool,
) -> None:
    """
    **Validates: Requirements 2.1**

    对任意案号字符串，normalize_case_number 应满足幂等性：
    normalize(normalize(x)) == normalize(x)
    """
    first: str = normalize_case_number(raw, ensure_hao=ensure_hao)
    second: str = normalize_case_number(first, ensure_hao=ensure_hao)

    assert second == first, (
        f"幂等性失败:\n"
        f"  原始输入: {raw!r}\n"
        f"  ensure_hao={ensure_hao}\n"
        f"  第一次: {first!r}\n"
        f"  第二次: {second!r}"
    )
