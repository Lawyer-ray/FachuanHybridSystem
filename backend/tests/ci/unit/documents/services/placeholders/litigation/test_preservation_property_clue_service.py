"""Tests for documents.services.placeholders.litigation.preservation_property_clue_service.

Covers: generate, _get_chinese_number, _parse_clue_content,
generate_property_clue_info, get_respondents_without_clues.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


class TestPreservationPropertyClueServiceGenerate:
    def _make_service(self):
        from apps.documents.services.placeholders.litigation.preservation_property_clue_service import (
            PreservationPropertyClueService,
        )
        return PreservationPropertyClueService()

    def test_generate_no_case_id(self):
        svc = self._make_service()
        result = svc.generate({})
        assert result == {"财产保全申请书财产线索": ""}

    def test_generate_with_case_id(self):
        svc = self._make_service()
        with patch.object(svc, "generate_property_clue_info", return_value="clue_info") as mock:
            result = svc.generate({"case_id": 1})
            mock.assert_called_once_with(1)
            assert result["财产保全申请书财产线索"] == "clue_info"

    def test_generate_with_case_object(self):
        svc = self._make_service()
        case = SimpleNamespace(id=42)
        with patch.object(svc, "generate_property_clue_info", return_value="info") as mock:
            result = svc.generate({"case": case})
            mock.assert_called_once_with(42)
            assert result["财产保全申请书财产线索"] == "info"

    def test_generate_none_case_id(self):
        svc = self._make_service()
        with patch.object(svc, "generate_property_clue_info", return_value="info"):
            result = svc.generate({"case_id": None, "case": None})
            assert result["财产保全申请书财产线索"] == ""


class TestGetChineseNumber:
    def _make_service(self):
        from apps.documents.services.placeholders.litigation.preservation_property_clue_service import (
            PreservationPropertyClueService,
        )
        return PreservationPropertyClueService()

    def test_within_range(self):
        svc = self._make_service()
        assert svc._get_chinese_number(0) == "一"
        assert svc._get_chinese_number(4) == "五"
        assert svc._get_chinese_number(19) == "二十"

    def test_out_of_range(self):
        svc = self._make_service()
        assert svc._get_chinese_number(20) == "21"
        assert svc._get_chinese_number(99) == "100"


class TestParseClueContent:
    def _make_service(self):
        from apps.documents.services.placeholders.litigation.preservation_property_clue_service import (
            PreservationPropertyClueService,
        )
        return PreservationPropertyClueService()

    def test_empty_content(self):
        svc = self._make_service()
        assert svc._parse_clue_content("bank", "") == []

    def test_none_content(self):
        svc = self._make_service()
        assert svc._parse_clue_content("bank", None) == []  # type: ignore[arg-type]

    def test_lines_with_colon(self):
        svc = self._make_service()
        content = "开户行: 工商银行\n账号: 12345"
        result = svc._parse_clue_content("bank", content)
        assert len(result) == 2
        assert "开户行" in result[0]

    def test_lines_without_colon(self):
        svc = self._make_service()
        content = "普通内容"
        result = svc._parse_clue_content("bank", content)
        assert len(result) == 1
        assert result[0] == "普通内容"


class TestGeneratePropertyClueInfo:
    def _make_service(self):
        from apps.documents.services.placeholders.litigation.preservation_property_clue_service import (
            PreservationPropertyClueService,
        )
        return PreservationPropertyClueService()

    def test_no_respondents(self):
        svc = self._make_service()
        with patch("apps.documents.services.infrastructure.wiring.get_case_service") as mock_cs, \
             patch("apps.documents.services.infrastructure.wiring.get_client_service") as mock_cls:
            mock_cs.return_value.get_case_parties_internal.return_value = []
            result = svc.generate_property_clue_info(1)
            assert result == ""

    def test_respondent_no_clues(self):
        svc = self._make_service()
        party_dto = SimpleNamespace(client_name="李四", client_id=1)
        with patch("apps.documents.services.infrastructure.wiring.get_case_service") as mock_cs, \
             patch("apps.documents.services.infrastructure.wiring.get_client_service") as mock_cls:
            mock_cs.return_value.get_case_parties_internal.return_value = [party_dto]
            mock_cls.return_value.get_property_clues_by_client_internal.return_value = []
            result = svc.generate_property_clue_info(1)
            assert "李四" in result
            assert "暂无财产线索" in result

    def test_respondent_with_clues(self):
        svc = self._make_service()
        party_dto = SimpleNamespace(client_name="王五", client_id=2)
        clue_dto = SimpleNamespace(clue_type="bank", content="开户行: 建行\n账号: 622")
        with patch("apps.documents.services.infrastructure.wiring.get_case_service") as mock_cs, \
             patch("apps.documents.services.infrastructure.wiring.get_client_service") as mock_cls:
            mock_cs.return_value.get_case_parties_internal.return_value = [party_dto]
            mock_cls.return_value.get_property_clues_by_client_internal.return_value = [clue_dto]
            result = svc.generate_property_clue_info(1)
            assert "王五" in result
            assert "银行账户" in result


class TestGetRespondentsWithoutClues:
    def _make_service(self):
        from apps.documents.services.placeholders.litigation.preservation_property_clue_service import (
            PreservationPropertyClueService,
        )
        return PreservationPropertyClueService()

    def test_all_have_clues(self):
        svc = self._make_service()
        party_dto = SimpleNamespace(client_name="张三", client_id=1)
        clue_dto = SimpleNamespace(clue_type="bank", content="info")
        with patch("apps.documents.services.infrastructure.wiring.get_case_service") as mock_cs, \
             patch("apps.documents.services.infrastructure.wiring.get_client_service") as mock_cls:
            mock_cs.return_value.get_case_parties_internal.return_value = [party_dto]
            mock_cls.return_value.get_property_clues_by_client_internal.return_value = [clue_dto]
            result = svc.get_respondents_without_clues(1)
            assert result == []

    def test_some_missing_clues(self):
        svc = self._make_service()
        p1 = SimpleNamespace(client_name="张三", client_id=1)
        p2 = SimpleNamespace(client_name="李四", client_id=2)
        with patch("apps.documents.services.infrastructure.wiring.get_case_service") as mock_cs, \
             patch("apps.documents.services.infrastructure.wiring.get_client_service") as mock_cls:
            mock_cs.return_value.get_case_parties_internal.return_value = [p1, p2]
            def fake_get_clues(client_id):
                if client_id == 1:
                    return [SimpleNamespace(clue_type="bank", content="info")]
                return []
            mock_cls.return_value.get_property_clues_by_client_internal.side_effect = fake_get_clues
            result = svc.get_respondents_without_clues(1)
            assert "李四" in result
            assert "张三" not in result
