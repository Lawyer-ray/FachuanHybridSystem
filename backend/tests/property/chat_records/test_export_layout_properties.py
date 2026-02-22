"""
Property-Based Tests for ExportLayout.from_payload Fallback Logic

# Feature: chat-records-quality-uplift, Property 2: ExportLayout.from_payload 回退值

**Validates: Requirements 6.3**

对任意 payload 字典和 default_header_text 字符串，当 payload 中 header_text
为空或缺失时，from_payload 返回的 header_text 应等于 default_header_text；
当 payload 中 header_text 非空时，应使用 payload 中的值。
"""

from __future__ import annotations

from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.chat_records.services.export_types import ExportLayout

# ========== Strategies ==========

export_type_st = st.sampled_from(["pdf", "docx"])
images_per_page_st = st.sampled_from([1, 2])
show_page_number_st = st.booleans()
header_text_st = st.text(
    min_size=0,
    max_size=200,
    alphabet=st.characters(categories=("L", "N", "Z", "P")),
)
default_header_text_st = st.text(
    min_size=1,
    max_size=200,
    alphabet=st.characters(categories=("L", "N", "Z", "P")),
)


def _build_payload(
    images_per_page: int,
    show_page_number: bool,
    header_text: str | None,
) -> dict[str, Any]:
    """构建合法的 payload 字典。"""
    payload: dict[str, Any] = {
        "images_per_page": images_per_page,
        "show_page_number": show_page_number,
    }
    if header_text is not None:
        payload["header_text"] = header_text
    return payload


# ========== Property Tests ==========


@settings(max_examples=100)
@given(
    export_type=export_type_st,
    images_per_page=images_per_page_st,
    show_page_number=show_page_number_st,
    default_header_text=default_header_text_st,
)
def test_missing_header_text_falls_back_to_default(
    export_type: str,
    images_per_page: int,
    show_page_number: bool,
    default_header_text: str,
) -> None:
    """
    # Feature: chat-records-quality-uplift, Property 2: ExportLayout.from_payload 回退值

    当 payload 中 header_text 缺失时，结果应使用 default_header_text。
    **Validates: Requirements 6.3**
    """
    payload = _build_payload(images_per_page, show_page_number, header_text=None)
    layout = ExportLayout.from_payload(
        export_type, payload, default_header_text=default_header_text,
    )
    assert layout.header_text == default_header_text


@settings(max_examples=100)
@given(
    export_type=export_type_st,
    images_per_page=images_per_page_st,
    show_page_number=show_page_number_st,
    empty_header=st.sampled_from(["", "  ", "\t", "\n", "   \n\t  "]),
    default_header_text=default_header_text_st,
)
def test_empty_header_text_falls_back_to_default(
    export_type: str,
    images_per_page: int,
    show_page_number: bool,
    empty_header: str,
    default_header_text: str,
) -> None:
    """
    # Feature: chat-records-quality-uplift, Property 2: ExportLayout.from_payload 回退值

    当 payload 中 header_text 为空白字符串时，结果应使用 default_header_text。
    **Validates: Requirements 6.3**
    """
    payload = _build_payload(images_per_page, show_page_number, header_text=empty_header)
    layout = ExportLayout.from_payload(
        export_type, payload, default_header_text=default_header_text,
    )
    assert layout.header_text == default_header_text


@settings(max_examples=100)
@given(
    export_type=export_type_st,
    images_per_page=images_per_page_st,
    show_page_number=show_page_number_st,
    header_text=header_text_st.filter(lambda s: s.strip() != ""),
    default_header_text=default_header_text_st,
)
def test_nonempty_header_text_uses_payload_value(
    export_type: str,
    images_per_page: int,
    show_page_number: bool,
    header_text: str,
    default_header_text: str,
) -> None:
    """
    # Feature: chat-records-quality-uplift, Property 2: ExportLayout.from_payload 回退值

    当 payload 中 header_text 非空时，结果应使用 payload 中的值（strip 后）。
    **Validates: Requirements 6.3**
    """
    payload = _build_payload(images_per_page, show_page_number, header_text=header_text)
    layout = ExportLayout.from_payload(
        export_type, payload, default_header_text=default_header_text,
    )
    assert layout.header_text == header_text.strip()
