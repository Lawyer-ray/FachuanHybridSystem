"""Tests for documents.services.placeholders.supplementary.opposing_service.

Covers: generate, _get_opposing_parties, _strip_whitespace, format_opposing_party_clause
(natural person, legal entity, mixed, empty, exception paths).
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


class TestSupplementaryAgreementOpposingServiceGenerate:
    def _make_service(self):
        from apps.documents.services.placeholders.supplementary.opposing_service import (
            SupplementaryAgreementOpposingService,
        )
        return SupplementaryAgreementOpposingService()

    def test_generate_no_agreement(self):
        svc = self._make_service()
        result = svc.generate({})
        assert result == {"补充协议对方当事人主体信息条款": ""}

    def test_generate_none_agreement(self):
        svc = self._make_service()
        result = svc.generate({"supplementary_agreement": None})
        assert result == {"补充协议对方当事人主体信息条款": ""}

    def test_generate_with_agreement(self):
        svc = self._make_service()
        client = SimpleNamespace(name="张三", id_number="110101199001011234", client_type="natural")
        party = SimpleNamespace(role="OPPOSING", client=client)
        agreement = SimpleNamespace(parties=MagicMock(all=lambda: [party]))
        result = svc.generate({"supplementary_agreement": agreement})
        assert "张三" in result["补充协议对方当事人主体信息条款"]
        assert "姓名" in result["补充协议对方当事人主体信息条款"]


class TestGetOpposingParties:
    def _make_service(self):
        from apps.documents.services.placeholders.supplementary.opposing_service import (
            SupplementaryAgreementOpposingService,
        )
        return SupplementaryAgreementOpposingService()

    def test_basic(self):
        svc = self._make_service()
        client = SimpleNamespace(name="李四")
        party = SimpleNamespace(role="OPPOSING", client=client)
        agreement = SimpleNamespace(parties=MagicMock(all=lambda: [party]))
        result = svc._get_opposing_parties(agreement)
        assert len(result) == 1
        assert result[0].name == "李四"

    def test_no_opposing(self):
        svc = self._make_service()
        client = SimpleNamespace(name="王五")
        party = SimpleNamespace(role="OUR", client=client)
        agreement = SimpleNamespace(parties=MagicMock(all=lambda: [party]))
        result = svc._get_opposing_parties(agreement)
        assert result == []

    def test_exception_propagates(self):
        svc = self._make_service()
        agreement = SimpleNamespace(parties=MagicMock(all=lambda: (_ for _ in ()).throw(Exception("fail"))))
        with pytest.raises(Exception):
            svc._get_opposing_parties(agreement)


class TestStripWhitespace:
    def _make_service(self):
        from apps.documents.services.placeholders.supplementary.opposing_service import (
            SupplementaryAgreementOpposingService,
        )
        return SupplementaryAgreementOpposingService()

    def test_normal_text(self):
        svc = self._make_service()
        assert svc._strip_whitespace("hello world") == "helloworld"

    def test_empty_string(self):
        svc = self._make_service()
        assert svc._strip_whitespace("") == ""

    def test_none_input(self):
        svc = self._make_service()
        assert svc._strip_whitespace(None) == ""  # type: ignore[arg-type]

    def test_special_whitespace(self):
        svc = self._make_service()
        # zero width space, BOM, etc.
        text = "abc​def﻿ghi"
        result = svc._strip_whitespace(text)
        assert "​" not in result
        assert "﻿" not in result
        assert result == "abcdefghi"

    def test_tabs_and_newlines(self):
        svc = self._make_service()
        assert svc._strip_whitespace("a\t\nb") == "ab"


class TestFormatOpposingPartyClause:
    def _make_service(self):
        from apps.documents.services.placeholders.supplementary.opposing_service import (
            SupplementaryAgreementOpposingService,
        )
        return SupplementaryAgreementOpposingService()

    def test_empty_list(self):
        svc = self._make_service()
        assert svc.format_opposing_party_clause([]) == ""

    def test_natural_person(self):
        svc = self._make_service()
        client = SimpleNamespace(name="张三", id_number="110101199001011234", client_type="natural")
        result = svc.format_opposing_party_clause([client])
        assert "姓名：张三" in result
        assert "签名+指模" in result

    def test_legal_entity(self):
        svc = self._make_service()
        client = SimpleNamespace(name="公司A", id_number="91110108MA01ABC", client_type="legal")
        result = svc.format_opposing_party_clause([client])
        assert "名称：公司A" in result
        assert "统一社会信用代码" in result

    def test_no_id_number(self):
        svc = self._make_service()
        client = SimpleNamespace(name="张三", id_number=None, client_type="natural")
        result = svc.format_opposing_party_clause([client])
        assert "身份证号码：" in result

    def test_multiple_parties(self):
        svc = self._make_service()
        c1 = SimpleNamespace(name="张三", id_number="110", client_type="natural")
        c2 = SimpleNamespace(name="公司B", id_number="911", client_type="legal")
        result = svc.format_opposing_party_clause([c1, c2])
        assert "张三" in result
        assert "公司B" in result
        assert "；" in result

    def test_exception_in_party_formatting(self):
        svc = self._make_service()
        client = MagicMock()
        client.name = "张三"
        client.id_number = SimpleNamespace()
        # id_number is not a string, _strip_whitespace will get a weird value
        # hasattr(client, "client_type") -> True, but accessing it will raise
        del client.client_type  # no client_type attr
        # This will trigger the except branch
        result = svc.format_opposing_party_clause([client])
        assert "张三" in result
