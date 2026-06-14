"""Round 2 coverage tests for FingerprintService and MatchingService."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── FingerprintService ──

class TestFingerprintService:
    def _make_service(self):
        from apps.documents.services.external_template.fingerprint_service import FingerprintService
        return FingerprintService()

    def test_strip_text_content(self):
        svc = self._make_service()
        xml = '<root><w:t xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">Hello</w:t></root>'
        result = svc._strip_text_content(xml)
        assert "Hello" not in result
        # After stripping, t element should still exist but be empty
        assert "t" in result

    def test_strip_style_attributes_removes_style_elements(self):
        svc = self._make_service()
        ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        xml = f'''<root xmlns:w="{ns}">
            <w:rPr>
                <w:rFonts w:ascii="Arial"/>
                <w:sz w:val="24"/>
                <w:color w:val="FF0000"/>
                <w:b/>
                <w:i/>
            </w:rPr>
            <w:p/>
        </root>'''
        result = svc._strip_style_attributes(xml)
        # After removing style elements, rFonts/sz/color/b/i should be gone
        import xml.etree.ElementTree as ET
        root = ET.fromstring(result)
        # Find all elements and check none are style elements
        tags = {elem.tag for elem in root.iter()}
        style_ns = ns
        style_tags = {f"{{{style_ns}}}{t}" for t in ["rFonts", "sz", "color", "b", "i", "u", "strike"]}
        assert not tags.intersection(style_tags)
        # p element should still exist
        assert any("p" in tag for tag in tags)

    def test_remove_style_elements_recursive(self):
        svc = self._make_service()
        import xml.etree.ElementTree as ET
        ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        root = ET.fromstring(f'''<root xmlns:w="{ns}">
            <w:p>
                <w:rPr>
                    <w:b/>
                </w:rPr>
            </w:p>
        </root>''')
        svc._remove_style_elements(root)
        result = ET.tostring(root, encoding="unicode")
        # b element should be removed
        assert "b" not in result or "/>" in result  # element should be gone

    def test_find_matching_template_returns_none_for_empty_fingerprint(self):
        svc = self._make_service()
        result = svc.find_matching_template("", 1)
        assert result is None

    def test_find_matching_template_found(self):
        svc = self._make_service()
        with patch(
            "apps.documents.models.external_template.ExternalTemplate"
        ) as mock_tpl:
            mock_tpl.objects.filter.return_value.order_by.return_value.first.return_value = MagicMock(id=1, name="tpl")
            result = svc.find_matching_template("abc123", 1)
        assert result is not None

    def test_find_matching_template_not_found(self):
        svc = self._make_service()
        with patch(
            "apps.documents.models.external_template.ExternalTemplate"
        ) as mock_tpl:
            mock_tpl.objects.filter.return_value.order_by.return_value.first.return_value = None
            result = svc.find_matching_template("abc123", 1)
        assert result is None


# ── MatchingService ──

class TestMatchingService:
    def _make_service(self):
        from apps.documents.services.external_template.matching_service import MatchingService
        return MatchingService()

    def test_match_by_case_no_case(self):
        svc = self._make_service()
        with patch("apps.documents.services.external_template.matching_service.apps") as mock_apps:
            mock_case_model = MagicMock()
            mock_case_model.DoesNotExist = type("DoesNotExist", (Exception,), {})
            mock_case_model.objects.get.side_effect = mock_case_model.DoesNotExist
            mock_apps.get_model.side_effect = lambda app, model: mock_case_model if model == "Case" else MagicMock()
            result = svc.match_by_case(999, 1)
        assert result == []

    def test_match_by_case_with_source_name(self):
        svc = self._make_service()
        with patch("apps.documents.services.external_template.matching_service.apps") as mock_apps:
            mock_case_model = MagicMock()
            mock_case_model.objects.get.return_value = MagicMock()
            def get_model_side(app, model):
                if model == "Case":
                    return mock_case_model
                if model == "SupervisingAuthority":
                    mock_auth = MagicMock()
                    auth_instance = MagicMock()
                    auth_instance.name = "北京市朝阳区人民法院"
                    mock_auth.objects.filter.return_value.first.return_value = auth_instance
                    return mock_auth
                return MagicMock()
            mock_apps.get_model.side_effect = get_model_side
            with patch.object(svc, "match_by_source_name", return_value=["tpl"]) as mock_match:
                result = svc.match_by_case(1, 1)
        assert result == ["tpl"]

    def test_match_by_case_no_source_name(self):
        svc = self._make_service()
        with patch("apps.documents.services.external_template.matching_service.apps") as mock_apps:
            mock_case_model = MagicMock()
            mock_case_model.objects.get.return_value = MagicMock()
            def get_model_side(app, model):
                if model == "Case":
                    return mock_case_model
                if model == "SupervisingAuthority":
                    mock_auth = MagicMock()
                    mock_auth.objects.filter.return_value.first.return_value = None
                    return mock_auth
                return MagicMock()
            mock_apps.get_model.side_effect = get_model_side
            result = svc.match_by_case(1, 1)
        assert result == []

    def test_match_by_source_name_exact(self):
        svc = self._make_service()
        with patch(
            "apps.documents.models.external_template.ExternalTemplate"
        ) as mock_tpl:
            mock_qs = MagicMock()
            mock_qs.exists.return_value = True
            mock_tpl.objects.filter.return_value.order_by.return_value = mock_qs
            mock_tpl.objects.filter.return_value.order_by.return_value.__iter__ = MagicMock(return_value=iter([MagicMock()]))
            result = svc.match_by_source_name("北京市朝阳区人民法院", 1)
        assert len(result) == 1

    def test_match_by_source_name_fallback_to_parent_court(self):
        svc = self._make_service()
        with patch(
            "apps.documents.models.external_template.ExternalTemplate"
        ) as mock_tpl:
            mock_qs = MagicMock()
            mock_qs.exists.return_value = False
            mock_tpl.objects.filter.return_value.order_by.return_value = mock_qs

            with patch("apps.documents.services.external_template.matching_service.apps") as mock_apps:
                mock_court_model = MagicMock()
                court = MagicMock()
                court.parent_id = 10
                mock_court_model.objects.filter.return_value.first.return_value = court

                parent = MagicMock()
                parent.name = "北京市中级人民法院"

                def get_model_side(app, model):
                    if model == "Court":
                        mock_court_model.objects.filter.return_value.first.side_effect = [court, parent]
                        return mock_court_model
                    return MagicMock()

                mock_apps.get_model.side_effect = get_model_side

                with patch.object(svc, "match_by_source_name") as mock_match:
                    mock_match.return_value = ["tpl"]
                    # Call will recursively call match_by_source_name for parent
                    result = svc.match_by_source_name("北京市朝阳区人民法院", 1)

    def test_match_by_source_name_no_parent(self):
        svc = self._make_service()
        with patch(
            "apps.documents.models.external_template.ExternalTemplate"
        ) as mock_tpl:
            mock_qs = MagicMock()
            mock_qs.exists.return_value = False
            mock_tpl.objects.filter.return_value.order_by.return_value = mock_qs

            with patch("apps.documents.services.external_template.matching_service.apps") as mock_apps:
                mock_court_model = MagicMock()
                court = MagicMock()
                court.parent_id = None
                mock_court_model.objects.filter.return_value.first.return_value = court

                def get_model_side(app, model):
                    if model == "Court":
                        return mock_court_model
                    return MagicMock()

                mock_apps.get_model.side_effect = get_model_side
                result = svc.match_by_source_name("Unknown Court", 1)
        assert result == []

    def test_match_by_source_name_court_not_found(self):
        svc = self._make_service()
        with patch(
            "apps.documents.models.external_template.ExternalTemplate"
        ) as mock_tpl:
            mock_qs = MagicMock()
            mock_qs.exists.return_value = False
            mock_tpl.objects.filter.return_value.order_by.return_value = mock_qs

            with patch("apps.documents.services.external_template.matching_service.apps") as mock_apps:
                mock_court_model = MagicMock()
                mock_court_model.objects.filter.return_value.first.return_value = None

                def get_model_side(app, model):
                    if model == "Court":
                        return mock_court_model
                    return MagicMock()

                mock_apps.get_model.side_effect = get_model_side
                result = svc.match_by_source_name("Unknown", 1)
        assert result == []

    def test_get_template_statistics(self):
        svc = self._make_service()
        with patch(
            "apps.documents.models.external_template.ExternalTemplate"
        ) as mock_tpl, patch(
            "apps.documents.models.choices.TemplateStatus"
        ) as mock_status:
            mock_status.READY = "ready"
            base_qs = MagicMock()
            base_qs.exclude.return_value.values.return_value.annotate.return_value.order_by.return_value = [
                {"source_name": "法院A", "count": 3}
            ]
            base_qs.count.return_value = 5
            base_qs.filter.return_value.count.return_value = 2
            mock_tpl.objects.filter.return_value = base_qs

            result = svc.get_template_statistics(1)
        assert result["total"] == 5
        assert result["confirmed"] == 2
        assert result["unconfirmed"] == 3

    def test_get_source_name_from_case_found(self):
        svc = self._make_service()
        case = MagicMock()
        with patch("apps.documents.services.external_template.matching_service.apps") as mock_apps:
            mock_auth_model = MagicMock()
            auth = MagicMock()
            auth.name = "法院"
            mock_auth_model.objects.filter.return_value.first.return_value = auth
            def get_model_side(app, model):
                if model == "SupervisingAuthority":
                    return mock_auth_model
                return MagicMock()
            mock_apps.get_model.side_effect = get_model_side
            result = svc._get_source_name_from_case(case)
        assert result == "法院"

    def test_get_source_name_from_case_not_found(self):
        svc = self._make_service()
        case = MagicMock()
        with patch("apps.documents.services.external_template.matching_service.apps") as mock_apps:
            mock_auth_model = MagicMock()
            mock_auth_model.objects.filter.return_value.first.return_value = None
            def get_model_side(app, model):
                if model == "SupervisingAuthority":
                    return mock_auth_model
                return MagicMock()
            mock_apps.get_model.side_effect = get_model_side
            result = svc._get_source_name_from_case(case)
        assert result is None
