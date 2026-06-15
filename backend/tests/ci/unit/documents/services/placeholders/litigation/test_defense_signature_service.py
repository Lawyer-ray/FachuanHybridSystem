"""Tests for documents.services.placeholders.litigation.defense_signature_service.

Covers: generate, _format_date, generate_signature_info (natural person,
legal entity, mixed, no parties, multiple parties).
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


class TestDefenseSignatureServiceGenerate:
    def _make_service(self):
        with patch("apps.documents.services.placeholders.litigation.defense_signature_service.PartyFormatter"), \
             patch("apps.documents.services.placeholders.litigation.defense_signature_service.LitigationCaseDetailsAccessor"):
            from apps.documents.services.placeholders.litigation.defense_signature_service import (
                DefenseSignatureService,
            )
            return DefenseSignatureService()

    def test_no_case_id(self):
        svc = self._make_service()
        result = svc.generate({})
        assert result == {}

    def test_with_case_id(self):
        svc = self._make_service()
        with patch.object(svc, "generate_signature_info", return_value="sig_info") as mock:
            result = svc.generate({"case_id": 1})
            mock.assert_called_once_with(1)
            from apps.litigation_ai.placeholders.spec import LitigationPlaceholderKeys
            assert LitigationPlaceholderKeys.DEFENSE_SIGNATURE in result
            assert result[LitigationPlaceholderKeys.DEFENSE_SIGNATURE] == "sig_info"

    def test_with_case_object(self):
        svc = self._make_service()
        case = SimpleNamespace(id=42)
        with patch.object(svc, "generate_signature_info", return_value="sig") as mock:
            result = svc.generate({"case": case})
            mock.assert_called_once_with(42)

    def test_none_case_id(self):
        svc = self._make_service()
        result = svc.generate({"case_id": None, "case": None})
        assert result == {}


class TestDefenseSignatureInfoNoParties:
    def _make_service(self):
        with patch("apps.documents.services.placeholders.litigation.defense_signature_service.PartyFormatter") as MockFmt, \
             patch("apps.documents.services.placeholders.litigation.defense_signature_service.LitigationCaseDetailsAccessor") as MockAcc:
            from apps.documents.services.placeholders.litigation.defense_signature_service import (
                DefenseSignatureService,
            )
            svc = DefenseSignatureService()
            return svc

    def test_no_eligible_parties(self):
        svc = self._make_service()
        with patch("apps.documents.services.placeholders.litigation.defense_signature_service.LegalStatus") as MockLegal:
            MockLegal.DEFENDANT = "defendant"
            MockLegal.THIRD = "third"
            svc.case_details_accessor.get_case_parties.return_value = [
                {"is_our_client": False, "legal_status": "plaintiff", "client_name": "原告"}
            ]
            result = svc.generate_signature_info(1)
            assert result == ""


class TestDefenseSignatureInfoNaturalPerson:
    def _make_service(self):
        with patch("apps.documents.services.placeholders.litigation.defense_signature_service.PartyFormatter") as MockFmt, \
             patch("apps.documents.services.placeholders.litigation.defense_signature_service.LitigationCaseDetailsAccessor") as MockAcc:
            from apps.documents.services.placeholders.litigation.defense_signature_service import (
                DefenseSignatureService,
            )
            svc = DefenseSignatureService()
            svc.formatter = MockFmt.return_value
            svc.case_details_accessor = MockAcc.return_value
            return svc

    def test_single_natural_person(self):
        svc = self._make_service()
        svc.formatter.is_natural_person_from_dict.return_value = True
        with patch("apps.documents.services.placeholders.litigation.defense_signature_service.LegalStatus") as MockLegal:
            MockLegal.DEFENDANT = "defendant"
            party_dict = {"is_our_client": True, "legal_status": "defendant", "client_name": "张三"}
            svc.case_details_accessor.get_case_parties.return_value = [party_dict]
            svc.case_details_accessor.get_formatted_date.return_value = "2024年01月01日"
            result = svc.generate_signature_info(1)
            assert "答辩人" in result
            assert "张三" in result
            assert "签名+指模" in result
            assert "2024年01月01日" in result


class TestDefenseSignatureInfoLegalEntity:
    def _make_service(self):
        with patch("apps.documents.services.placeholders.litigation.defense_signature_service.PartyFormatter") as MockFmt, \
             patch("apps.documents.services.placeholders.litigation.defense_signature_service.LitigationCaseDetailsAccessor") as MockAcc:
            from apps.documents.services.placeholders.litigation.defense_signature_service import (
                DefenseSignatureService,
            )
            svc = DefenseSignatureService()
            svc.formatter = MockFmt.return_value
            svc.case_details_accessor = MockAcc.return_value
            return svc

    def test_single_legal_entity(self):
        svc = self._make_service()
        svc.formatter.is_natural_person_from_dict.return_value = False
        with patch("apps.documents.services.placeholders.litigation.defense_signature_service.LegalStatus") as MockLegal:
            MockLegal.DEFENDANT = "defendant"
            party_dict = {
                "is_our_client": True,
                "legal_status": "defendant",
                "client_name": "公司A",
                "legal_representative": "李总",
            }
            svc.case_details_accessor.get_case_parties.return_value = [party_dict]
            svc.case_details_accessor.get_formatted_date.return_value = "2024年06月15日"
            result = svc.generate_signature_info(1)
            assert "答辩人" in result
            assert "公司A" in result
            assert "盖章" in result
            assert "李总" in result
            assert "法定代表人（签名）" in result


class TestDefenseSignatureInfoMultipleParties:
    def _make_service(self):
        with patch("apps.documents.services.placeholders.litigation.defense_signature_service.PartyFormatter") as MockFmt, \
             patch("apps.documents.services.placeholders.litigation.defense_signature_service.LitigationCaseDetailsAccessor") as MockAcc:
            from apps.documents.services.placeholders.litigation.defense_signature_service import (
                DefenseSignatureService,
            )
            svc = DefenseSignatureService()
            svc.formatter = MockFmt.return_value
            svc.case_details_accessor = MockAcc.return_value
            return svc

    def test_two_parties(self):
        svc = self._make_service()
        svc.formatter.is_natural_person_from_dict.side_effect = [True, False]
        with patch("apps.documents.services.placeholders.litigation.defense_signature_service.LegalStatus") as MockLegal:
            MockLegal.DEFENDANT = "defendant"
            parties = [
                {"is_our_client": True, "legal_status": "defendant", "client_name": "张三"},
                {"is_our_client": True, "legal_status": "defendant", "client_name": "公司B", "legal_representative": "王总"},
            ]
            svc.case_details_accessor.get_case_parties.return_value = parties
            svc.case_details_accessor.get_formatted_date.return_value = "2024年06月15日"
            result = svc.generate_signature_info(1)
            assert "答辩人一" in result
            assert "答辩人二" in result
            assert "张三" in result
            assert "公司B" in result
