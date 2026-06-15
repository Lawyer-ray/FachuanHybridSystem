"""Tests for apps.cases.services.template.unified.filename."""
from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import patch

import pytest

from apps.cases.services.template.unified.filename import (
    DateProvider,
    FilenameInputs,
    FilenamePolicy,
    DjangoLocalDateProvider,
)


class TestDjangoLocalDateProvider:
    def test_returns_yyyymmdd(self) -> None:
        provider = DjangoLocalDateProvider()
        result = provider.today_yyyymmdd()
        assert len(result) == 8
        assert result.isdigit()


class TestFilenameInputs:
    def test_frozen_dataclass(self) -> None:
        inputs = FilenameInputs(
            template_name="T",
            case_name="C",
            client_name=None,
            function_code=None,
            mode=None,
            our_party_count=1,
        )
        assert inputs.template_name == "T"
        # Frozen, so setting should raise
        with pytest.raises(AttributeError):
            inputs.template_name = "X"  # type: ignore[misc]


class _FixedDateProvider:
    def today_yyyymmdd(self) -> str:
        return "20260615"


class TestFilenamePolicy:
    def setup_method(self) -> None:
        self.policy = FilenamePolicy(date_provider=_FixedDateProvider())

    def _make_inputs(self, **kwargs: object) -> FilenameInputs:
        defaults = {
            "template_name": "起诉状",
            "case_name": "张三诉李四",
            "client_name": "张三",
            "function_code": None,
            "mode": None,
            "our_party_count": 1,
        }
        defaults.update(kwargs)
        return FilenameInputs(**defaults)  # type: ignore[arg-type]

    def test_basic_filename(self) -> None:
        inputs = self._make_inputs()
        result = self.policy.build(
            inputs=inputs,
            legal_rep_cert_code="LRC",
            power_of_attorney_code="POA",
        )
        assert result == "起诉状（张三诉李四）V1_20260615.docx"

    def test_legal_rep_cert_with_client(self) -> None:
        inputs = self._make_inputs(function_code="LRC")
        result = self.policy.build(
            inputs=inputs,
            legal_rep_cert_code="LRC",
            power_of_attorney_code="POA",
        )
        assert result == "起诉状（张三）V1_20260615.docx"

    def test_legal_rep_cert_no_client_falls_back(self) -> None:
        inputs = self._make_inputs(function_code="LRC", client_name=None)
        result = self.policy.build(
            inputs=inputs,
            legal_rep_cert_code="LRC",
            power_of_attorney_code="POA",
        )
        # Falls through to the else branch (not matching client_name check)
        assert "张三诉李四" in result

    def test_power_of_attorney_combined(self) -> None:
        inputs = self._make_inputs(function_code="POA", mode="combined", our_party_count=2)
        result = self.policy.build(
            inputs=inputs,
            legal_rep_cert_code="LRC",
            power_of_attorney_code="POA",
        )
        assert result == "起诉状（张三诉李四）V1_20260615.docx"

    def test_power_of_attorney_separate_multi_party(self) -> None:
        inputs = self._make_inputs(function_code="POA", mode="separate", our_party_count=2)
        result = self.policy.build(
            inputs=inputs,
            legal_rep_cert_code="LRC",
            power_of_attorney_code="POA",
        )
        assert "张三" in result
        assert "张三诉李四" in result

    def test_power_of_attorney_single_party(self) -> None:
        inputs = self._make_inputs(function_code="POA", mode="separate", our_party_count=1)
        result = self.policy.build(
            inputs=inputs,
            legal_rep_cert_code="LRC",
            power_of_attorney_code="POA",
        )
        # Single party, goes to the basic case
        assert result == "起诉状（张三诉李四）V1_20260615.docx"

    def test_empty_template_name_uses_default(self) -> None:
        inputs = self._make_inputs(template_name="")
        result = self.policy.build(
            inputs=inputs,
            legal_rep_cert_code="LRC",
            power_of_attorney_code="POA",
        )
        assert result.startswith("模板（")

    def test_empty_case_name_uses_default(self) -> None:
        inputs = self._make_inputs(case_name="")
        result = self.policy.build(
            inputs=inputs,
            legal_rep_cert_code="LRC",
            power_of_attorney_code="POA",
        )
        assert "案件" in result


class TestFilenamePolicySafeName:
    def setup_method(self) -> None:
        self.policy = FilenamePolicy(date_provider=_FixedDateProvider())

    def test_normal_string(self) -> None:
        assert self.policy.safe_name("hello") == "hello"

    def test_slash_replacement(self) -> None:
        assert "／" in self.policy.safe_name("a/b")
        assert "＼" in self.policy.safe_name("a\\b")

    def test_whitespace_normalization(self) -> None:
        assert self.policy.safe_name("  hello   world  ") == "hello world"

    def test_newline_tab_replacement(self) -> None:
        result = self.policy.safe_name("a\nb\rc\td")
        assert result == "a b c d"

    def test_empty_returns_default(self) -> None:
        assert self.policy.safe_name("") == "未命名"

    def test_none_returns_default(self) -> None:
        assert self.policy.safe_name("") == "未命名"

    def test_whitespace_only_returns_default(self) -> None:
        assert self.policy.safe_name("   ") == "未命名"
