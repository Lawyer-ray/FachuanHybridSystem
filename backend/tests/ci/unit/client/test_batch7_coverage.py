"""Batch7 coverage tests for apps.client."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.client.services.text_parser import (
    _determine_client_type,
    _empty_result,
    _extract_address,
    _extract_credit_code,
    _extract_id_number,
    _extract_phone,
    _extract_legal_representative,
    _is_valid_name_candidate,
    _normalize_text,
    _clean_name_candidate,
    parse_client_text,
    parse_multiple_clients_text,
)
from apps.client.services.id_card_merge.validation import (
    validate_corners,
    order_corners,
    is_convex_quadrilateral,
    validate_image_size,
)
import numpy as np


# ── parse_client_text ───────────────────────────────────────────────────────


class TestParseClientText:
    def test_empty_text(self) -> None:
        result = parse_client_text("")
        assert result["name"] == ""

    def test_none_text(self) -> None:
        result = parse_client_text(None)
        assert result["name"] == ""

    def test_legal_entity_text(self) -> None:
        text = "原告：佛山市某某有限公司\n统一社会信用代码：91440000MA5EXAMPLE\n法定代表人：张三"
        result = parse_client_text(text)
        assert result["name"] != ""
        assert result["client_type"] == "legal"

    def test_natural_person_text(self) -> None:
        text = "被告：张三，男，身份证号码：440101199001011234，地址：广东省广州市天河区"
        result = parse_client_text(text)
        assert result["name"] != ""

    def test_multiple_clients(self) -> None:
        text = "原告：张三\n被告：李四"
        results = parse_multiple_clients_text(text)
        assert len(results) >= 1

    def test_multiple_clients_empty(self) -> None:
        assert parse_multiple_clients_text("") == []

    def test_multiple_clients_none(self) -> None:
        assert parse_multiple_clients_text(None) == []


# ── _normalize_text ─────────────────────────────────────────────────────────


class TestNormalizeText:
    def test_semicolons_to_newlines(self) -> None:
        result = _normalize_text("a;b")
        assert "\n" in result

    def test_chinese_semicolons(self) -> None:
        result = _normalize_text("a；b")
        assert "\n" in result

    def test_periods_to_newlines(self) -> None:
        result = _normalize_text("a。b")
        assert "\n" in result


# ── _extract_credit_code ────────────────────────────────────────────────────


class TestExtractCreditCode:
    def test_with_label(self) -> None:
        text = "统一社会信用代码：91440000MA5FHGT30X"
        result = _extract_credit_code(text)
        assert result is not None
        assert len(result) == 18

    def test_no_code(self) -> None:
        assert _extract_credit_code("no credit code here") is None


# ── _extract_id_number ──────────────────────────────────────────────────────


class TestExtractIdNumber:
    def test_with_label(self) -> None:
        text = "身份证号码：440101199001011234"
        result = _extract_id_number(text)
        assert result is not None
        assert len(result) == 18

    def test_no_id_number(self) -> None:
        assert _extract_id_number("no id here") is None


# ── _extract_address ────────────────────────────────────────────────────────


class TestExtractAddress:
    def test_with_label(self) -> None:
        text = "地址：广东省广州市天河区某某路100号"
        result = _extract_address(text)
        assert result is not None
        assert "广东省" in result

    def test_no_address(self) -> None:
        assert _extract_address("no address here") is None

    def test_address_line_fallback(self) -> None:
        text = "中国广东省广州市天河区某某路100号"
        result = _extract_address(text)
        assert result is not None


# ── _extract_phone ──────────────────────────────────────────────────────────


class TestExtractPhone:
    def test_with_label(self) -> None:
        text = "联系电话：13800138000"
        result = _extract_phone(text)
        assert result is not None
        assert "13800138000" in result

    def test_mobile_fallback(self) -> None:
        text = "联系人13800138000"
        result = _extract_phone(text)
        assert result is not None

    def test_no_phone(self) -> None:
        assert _extract_phone("no phone") is None


# ── _extract_legal_representative ───────────────────────────────────────────


class TestExtractLegalRep:
    def test_with_label(self) -> None:
        text = "法定代表人：张三"
        result = _extract_legal_representative(text)
        assert result is not None
        assert "张三" in result

    def test_no_legal_rep(self) -> None:
        assert _extract_legal_representative("no legal rep") is None


# ── _is_valid_name_candidate ────────────────────────────────────────────────


class TestIsValidNameCandidate:
    def test_valid_name(self) -> None:
        assert _is_valid_name_candidate("张三") is True

    def test_too_short(self) -> None:
        assert _is_valid_name_candidate("张") is False

    def test_contains_non_name_keyword(self) -> None:
        assert _is_valid_name_candidate("身份证号码") is False

    def test_pure_digits(self) -> None:
        assert _is_valid_name_candidate("12345") is False

    def test_empty(self) -> None:
        assert _is_valid_name_candidate("") is False


# ── _determine_client_type ──────────────────────────────────────────────────


class TestDetermineClientType:
    def test_legal_keywords(self) -> None:
        assert _determine_client_type("某某有限公司", "") == "legal"

    def test_natural_default(self) -> None:
        assert _determine_client_type("张三", "") == "natural"

    def test_with_credit_code(self) -> None:
        assert _determine_client_type("公司", "统一社会信用代码：91440000MA5FHGT30X") == "legal"


# ── id_card_merge validation ────────────────────────────────────────────────


class TestIdCardMergeValidation:
    def test_order_corners(self) -> None:
        corners = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float32)
        ordered = order_corners(corners)
        assert ordered.shape == (4, 2)

    def test_validate_corners_wrong_count(self) -> None:
        result = validate_corners([[0, 0], [1, 0], [1, 1]])
        assert result is not None
        assert "4" in result

    def test_validate_corners_valid(self) -> None:
        corners = [[0, 0], [100, 0], [100, 100], [0, 100]]
        result = validate_corners(corners)
        assert result is None

    def test_validate_corners_negative(self) -> None:
        corners = [[-1, 0], [100, 0], [100, 100], [0, 100]]
        result = validate_corners(corners)
        assert result is not None
        assert "负数" in result

    def test_validate_corners_non_numeric(self) -> None:
        corners = [["a", 0], [100, 0], [100, 100], [0, 100]]
        result = validate_corners(corners)
        assert result is not None

    def test_is_convex_quadrilateral_true(self) -> None:
        corners = np.array([[0, 0], [100, 0], [100, 100], [0, 100]], dtype=np.float32)
        assert is_convex_quadrilateral(corners) is True

    def test_is_convex_quadrilateral_too_few_points(self) -> None:
        corners = np.array([[0, 0], [100, 0], [100, 100]], dtype=np.float32)
        assert is_convex_quadrilateral(corners) is False

    def test_validate_image_size_too_small(self) -> None:
        img = np.zeros((50, 50, 3), dtype=np.uint8)
        result = validate_image_size(img, "test", min_image_size=100)
        assert result is not None
        assert "太低" in result["message"]

    def test_validate_image_size_ok(self) -> None:
        img = np.zeros((200, 200, 3), dtype=np.uint8)
        result = validate_image_size(img, "test", min_image_size=100)
        assert result is None
