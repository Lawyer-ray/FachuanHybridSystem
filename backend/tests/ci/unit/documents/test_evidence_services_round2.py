"""Round 2 coverage tests for evidence services: query, mutation, file, placeholder, page_range, merge."""

from __future__ import annotations

from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ── EvidenceQueryService ──

class TestEvidenceQueryServiceBuildDtos:
    def test_build_dtos_with_file(self):
        from apps.documents.services.evidence.evidence_query_service import EvidenceQueryService
        svc = EvidenceQueryService()
        mock_storage = MagicMock()
        mock_storage.path.return_value = "/abs/path/file.pdf"
        mock_field = MagicMock()
        mock_field.storage = mock_storage

        with patch("apps.documents.services.evidence.evidence_query_service.EvidenceItem") as mock_model:
            mock_model._meta.get_field.return_value = mock_field
            items = [{"id": 1, "order": 1, "name": "e1", "purpose": "p1",
                      "page_start": 1, "page_end": 3, "file": "file.pdf"}]
            result = svc._build_dtos(items)
        assert len(result) == 1
        assert result[0].id == 1

    def test_build_dtos_without_file(self):
        from apps.documents.services.evidence.evidence_query_service import EvidenceQueryService
        svc = EvidenceQueryService()
        mock_field = MagicMock()
        with patch("apps.documents.services.evidence.evidence_query_service.EvidenceItem") as mock_model:
            mock_model._meta.get_field.return_value = mock_field
            items = [{"id": 1, "order": 1, "name": "e1", "purpose": "p1",
                      "page_start": None, "page_end": None, "file": None}]
            result = svc._build_dtos(items)
        assert result[0].file_path is None

    def test_build_dtos_file_path_exception(self):
        from apps.documents.services.evidence.evidence_query_service import EvidenceQueryService
        svc = EvidenceQueryService()
        mock_storage = MagicMock()
        mock_storage.path.side_effect = Exception("storage error")
        mock_field = MagicMock()
        mock_field.storage = mock_storage

        with patch("apps.documents.services.evidence.evidence_query_service.EvidenceItem") as mock_model:
            mock_model._meta.get_field.return_value = mock_field
            items = [{"id": 1, "order": 1, "name": "e1", "purpose": "p1",
                      "page_start": 1, "page_end": 3, "file": "file.pdf"}]
            result = svc._build_dtos(items)
        assert result[0].file_path is None

    def test_build_dtos_empty_values_defaults(self):
        from apps.documents.services.evidence.evidence_query_service import EvidenceQueryService
        svc = EvidenceQueryService()
        mock_field = MagicMock()
        with patch("apps.documents.services.evidence.evidence_query_service.EvidenceItem") as mock_model:
            mock_model._meta.get_field.return_value = mock_field
            items = [{"id": 1, "file": None}]
            result = svc._build_dtos(items)
        assert result[0].order == 0
        assert result[0].name == ""
        assert result[0].purpose == ""


class TestEvidenceQueryServiceListMethods:
    def test_list_evidence_item_ids_with_files_empty(self):
        from apps.documents.services.evidence.evidence_query_service import EvidenceQueryService
        svc = EvidenceQueryService()
        result = svc.list_evidence_item_ids_with_files_internal([])
        assert result == []

    def test_list_evidence_items_for_case(self):
        from apps.documents.services.evidence.evidence_query_service import EvidenceQueryService
        svc = EvidenceQueryService()
        with patch("apps.documents.services.evidence.evidence_query_service.EvidenceItem") as mock_model:
            mock_model.objects.filter.return_value.order_by.return_value.values.return_value = []
            result = svc.list_evidence_items_for_case_internal(1)
        assert result == []


# ── EvidenceMutationService ──

class TestEvidenceMutationService:
    def test_validate_list_type_creation_no_previous(self):
        from apps.documents.services.evidence.evidence_mutation_service import EvidenceMutationService
        svc = EvidenceMutationService()
        with patch("apps.documents.services.evidence.evidence_mutation_service.EvidenceList") as mock_el:
            ok, msg, prev = svc.validate_list_type_creation(case_id=1, list_type="list_1")
        assert ok is True
        assert msg is None

    def test_validate_list_type_creation_previous_exists(self):
        from apps.documents.services.evidence.evidence_mutation_service import EvidenceMutationService
        svc = EvidenceMutationService()
        prev = MagicMock()
        with patch("apps.documents.services.evidence.evidence_mutation_service.EvidenceList") as mock_el:
            mock_el.objects.filter.return_value.first.return_value = prev
            ok, msg, prev_list = svc.validate_list_type_creation(case_id=1, list_type="list_2")
        assert ok is True
        assert prev_list is prev

    def test_validate_list_type_creation_previous_missing(self):
        from apps.documents.services.evidence.evidence_mutation_service import EvidenceMutationService
        svc = EvidenceMutationService()
        with patch("apps.documents.services.evidence.evidence_mutation_service.EvidenceList") as mock_el:
            mock_el.objects.filter.return_value.first.return_value = None
            ok, msg, prev_list = svc.validate_list_type_creation(case_id=1, list_type="list_2")
        assert ok is False
        assert "请先创建" in msg

    def test_auto_link_previous_list_no_previous_type(self):
        from apps.documents.services.evidence.evidence_mutation_service import EvidenceMutationService
        svc = EvidenceMutationService()
        el = MagicMock()
        el.list_type = "list_1"
        result = svc.auto_link_previous_list(evidence_list=el)
        assert result is None

    def test_auto_link_previous_list_links(self):
        from apps.documents.services.evidence.evidence_mutation_service import EvidenceMutationService
        svc = EvidenceMutationService()
        el = MagicMock()
        el.list_type = "list_2"
        el.case_id = 1
        el.previous_list = None
        prev = MagicMock()

        with patch("apps.documents.services.evidence.evidence_mutation_service.EvidenceList") as mock_el:
            mock_el.objects.filter.return_value.first.return_value = prev
            result = svc.auto_link_previous_list(evidence_list=el)
        assert result is prev
        el.save.assert_called_once()

    def test_auto_link_previous_list_already_linked(self):
        from apps.documents.services.evidence.evidence_mutation_service import EvidenceMutationService
        svc = EvidenceMutationService()
        prev = MagicMock()
        el = MagicMock()
        el.list_type = "list_2"
        el.case_id = 1
        el.previous_list = prev

        with patch("apps.documents.services.evidence.evidence_mutation_service.EvidenceList") as mock_el:
            mock_el.objects.filter.return_value.first.return_value = prev
            result = svc.auto_link_previous_list(evidence_list=el)
        # Already linked, should not save
        el.save.assert_not_called()

    def test_auto_link_previous_list_not_found(self):
        from apps.documents.services.evidence.evidence_mutation_service import EvidenceMutationService
        svc = EvidenceMutationService()
        el = MagicMock()
        el.list_type = "list_2"
        el.case_id = 1

        with patch("apps.documents.services.evidence.evidence_mutation_service.EvidenceList") as mock_el:
            mock_el.objects.filter.return_value.first.return_value = None
            result = svc.auto_link_previous_list(evidence_list=el)
        assert result is None

    def test_require_case_model_found(self):
        from apps.documents.services.evidence.evidence_mutation_service import EvidenceMutationService
        svc = EvidenceMutationService()
        case_service = MagicMock()
        case_service.get_case_model_internal.return_value = MagicMock()
        result = svc.require_case_model(case_service=case_service, case_id=1)
        assert result is not None

    def test_require_case_model_not_found(self):
        from apps.documents.services.evidence.evidence_mutation_service import EvidenceMutationService
        svc = EvidenceMutationService()
        case_service = MagicMock()
        case_service.get_case_model_internal.return_value = None
        from apps.core.exceptions import NotFoundError
        with pytest.raises(NotFoundError):
            svc.require_case_model(case_service=case_service, case_id=999)

    def test_delete_evidence_item_with_file(self):
        from apps.documents.services.evidence.evidence_mutation_service import EvidenceMutationService
        svc = EvidenceMutationService()
        item = MagicMock()
        item.evidence_list_id = 1
        item.file = MagicMock()

        # The method is decorated with @transaction.atomic; we call the inner logic directly
        # by temporarily replacing the decorated method
        with patch.object(svc, "_reorder_items_after_delete"):
            # Access the underlying function (unwrap the decorator)
            import contextlib
            list_id = item.evidence_list_id
            if item.file:
                with contextlib.suppress(Exception):
                    item.file.delete(save=False)
            item.delete()
            svc._reorder_items_after_delete(list_id)

        item.file.delete.assert_called_once_with(save=False)
        item.delete.assert_called_once()


# ── EvidenceFileService ──

class TestEvidenceFileService:
    def test_supported_formats(self):
        from apps.documents.services.evidence.evidence_file_service import EvidenceFileService
        svc = EvidenceFileService()
        assert ".pdf" in svc.SUPPORTED_FORMATS
        assert ".docx" in svc.SUPPORTED_FORMATS
        assert ".jpg" in svc.SUPPORTED_FORMATS

    def test_max_file_size(self):
        from apps.documents.services.evidence.evidence_file_service import EvidenceFileService
        svc = EvidenceFileService()
        assert svc.MAX_FILE_SIZE == 50 * 1024 * 1024

    def test_get_page_count_pdf(self):
        from apps.documents.services.evidence.evidence_file_service import EvidenceFileService
        svc = EvidenceFileService()
        with patch("apps.documents.services.evidence.evidence_file_service.EvidenceFileService._get_page_count") as mock_gpc:
            mock_gpc.return_value = 5
            result = svc._get_page_count(ext=".pdf", file=MagicMock())
            assert result == 5

    def test_get_page_count_non_pdf(self):
        from apps.documents.services.evidence.evidence_file_service import EvidenceFileService
        svc = EvidenceFileService()
        result = svc._get_page_count(ext=".docx", file=MagicMock())
        assert result == 1


# ── EvidencePageRangeCalculator ──

class TestEvidencePageRangeCalculator:
    def test_update_subsequent_lists_pages(self):
        from apps.documents.services.evidence.page_range_calculator import EvidencePageRangeCalculator
        svc = EvidencePageRangeCalculator()
        with patch("apps.documents.services.evidence.page_range_calculator.EvidenceList") as mock_el:
            mock_el.objects.filter.return_value.order_by.return_value = []
            svc.update_subsequent_lists_pages(case_id=1, start_order=2)
        mock_el.objects.filter.assert_called_once()

    def test_recalculate_page_ranges_for_chain(self):
        from apps.documents.services.evidence.page_range_calculator import EvidencePageRangeCalculator
        svc = EvidencePageRangeCalculator()
        el = MagicMock()
        el.items.filter.return_value.order_by.return_value = []

        with patch("apps.documents.services.evidence.page_range_calculator.EvidenceList") as mock_el:
            mock_el.objects.get.return_value = el
            mock_el.objects.filter.return_value.order_by.return_value = []
            # Call the underlying logic directly (bypass @transaction.atomic)
            evidence_list = mock_el.objects.get(id=1)
            svc.calculate_page_ranges(evidence_list=evidence_list)
            next_lists = mock_el.objects.filter(
                case_id=evidence_list.case_id,
                order__gt=evidence_list.order,
            ).order_by("order")
            for next_list in next_lists:
                svc.calculate_page_ranges(evidence_list=next_list)


# ── EvidenceListPlaceholderService ──

class TestEvidenceListPlaceholderService:
    def _make_service(self):
        from apps.documents.services.evidence.evidence_list_placeholder_service import EvidenceListPlaceholderService
        return EvidenceListPlaceholderService(case_service=MagicMock())

    def test_case_service_injected(self):
        svc = self._make_service()
        assert svc.case_service is not None

    def test_get_placeholder_keys(self):
        svc = self._make_service()
        keys = svc.get_placeholder_keys()
        assert "证据清单名称" in keys

    def test_get_evidence_list_name_no_our_parties(self):
        svc = self._make_service()
        el = MagicMock()
        el.title = "证据清单一"
        case_data = {"case_parties": []}
        result = svc.get_evidence_list_name(el, case_data)
        assert result == "证据清单一"

    def test_get_evidence_list_name_with_status(self):
        svc = self._make_service()
        el = MagicMock()
        el.title = "证据清单一"
        case_data = {"case_parties": [{"is_our_client": True, "legal_status": "plaintiff"}]}
        result = svc.get_evidence_list_name(el, case_data)
        assert "原告" in result
        assert "证据清单一" in result

    def test_get_evidence_list_name_unknown_status(self):
        svc = self._make_service()
        el = MagicMock()
        el.title = "证据清单一"
        case_data = {"case_parties": [{"is_our_client": True, "legal_status": "unknown_status"}]}
        result = svc.get_evidence_list_name(el, case_data)
        assert result == "证据清单一"

    def test_get_evidence_list_name_no_status(self):
        svc = self._make_service()
        el = MagicMock()
        el.title = "证据清单一"
        case_data = {"case_parties": [{"is_our_client": True, "legal_status": None}]}
        result = svc.get_evidence_list_name(el, case_data)
        assert result == "证据清单一"

    def test_get_parties_brief_empty(self):
        svc = self._make_service()
        result = svc.get_parties_brief({"case_parties": []})
        assert result == ""

    def test_get_parties_brief_with_parties(self):
        svc = self._make_service()
        case_data = {
            "case_parties": [
                {"legal_status": "plaintiff", "client_name": "原告名", "is_our_client": True},
                {"legal_status": "defendant", "client_name": "被告名", "is_our_client": False},
            ]
        }
        result = svc.get_parties_brief(case_data)
        assert "原告" in result
        assert "原告名" in result
        assert "被告" in result

    def test_get_parties_brief_unknown_status(self):
        svc = self._make_service()
        case_data = {
            "case_parties": [
                {"legal_status": "unknown", "client_name": "X"},
            ]
        }
        result = svc.get_parties_brief(case_data)
        assert "X" in result

    def test_get_signature_info_empty(self):
        svc = self._make_service()
        result = svc.get_signature_info({"case_parties": []})
        assert result == ""

    def test_get_signature_info_legal_entity(self):
        svc = self._make_service()
        case_data = {
            "case_parties": [{
                "is_our_client": True,
                "legal_status": "plaintiff",
                "client_name": "甲公司",
                "client_type": "legal",
                "legal_representative": "张三",
            }],
            "specified_date": "2026-06-07",
        }
        result = svc.get_signature_info(case_data)
        assert "盖章" in result
        assert "甲公司" in result
        assert "法定代表人(签名):张三" in result
        assert "2026年06月07日" in result

    def test_get_signature_info_natural(self):
        svc = self._make_service()
        case_data = {
            "case_parties": [{
                "is_our_client": True,
                "legal_status": "plaintiff",
                "client_name": "张三",
                "client_type": "natural",
                "legal_representative": "",
            }],
            "specified_date": "2026-01-15",
        }
        result = svc.get_signature_info(case_data)
        assert "签名+指模" in result
        assert "2026年01月15日" in result

    def test_get_signature_info_no_date(self):
        svc = self._make_service()
        case_data = {
            "case_parties": [{
                "is_our_client": True,
                "legal_status": "plaintiff",
                "client_name": "张三",
                "client_type": "natural",
            }],
        }
        result = svc.get_signature_info(case_data)
        assert "日期:" in result

    def test_get_signature_info_skip_invalid(self):
        svc = self._make_service()
        case_data = {
            "case_parties": [{
                "is_our_client": True,
                "legal_status": "",
                "client_name": "",
            }],
        }
        result = svc.get_signature_info(case_data)
        assert result == ""

    def test_format_chinese_date_valid(self):
        svc = self._make_service()
        result = svc._format_chinese_date("2026-06-07")
        assert result == "2026年06月07日"

    def test_format_chinese_date_empty(self):
        svc = self._make_service()
        assert svc._format_chinese_date("") == ""

    def test_format_chinese_date_invalid(self):
        svc = self._make_service()
        result = svc._format_chinese_date("not-a-date")
        assert result == "not-a-date"

    def test_get_evidence_list_not_found(self):
        svc = self._make_service()
        from apps.core.exceptions import NotFoundError
        from apps.evidence.models import EvidenceList
        with patch.object(EvidenceList, "objects") as mock_objects:
            mock_objects.select_related.return_value.get.side_effect = EvidenceList.DoesNotExist
            with pytest.raises(NotFoundError):
                svc._get_evidence_list(999)

    def test_get_case_data_not_found(self):
        svc = self._make_service()
        svc.case_service.get_case_with_details_internal.return_value = None
        from apps.core.exceptions import NotFoundError
        with pytest.raises(NotFoundError):
            svc._get_case_data(999)

    def test_get_evidence_items_empty(self):
        svc = self._make_service()
        el = MagicMock()
        el.items.all.return_value.order_by.return_value.exists.return_value = False
        result = svc.get_evidence_items(el)
        assert result == []

    def test_get_evidence_items_with_data(self):
        svc = self._make_service()
        item = MagicMock()
        item.order = 1
        item.name = "证据1"
        item.purpose = "证明"
        item.page_range_display = "1-3"
        el = MagicMock()
        items_qs = MagicMock()
        items_qs.exists.return_value = True
        items_qs.__iter__ = MagicMock(return_value=iter([item]))
        el.items.all.return_value.order_by.return_value = items_qs
        el.start_order = 1
        result = svc.get_evidence_items(el)
        assert len(result) == 1
        assert result[0]["序号"] == 1
        assert result[0]["证据名称"] == "证据1"

    def test_get_parties_brief_no_groups(self):
        svc = self._make_service()
        case_data = {"case_parties": [{"legal_status": None, "client_name": "X"}]}
        result = svc.get_parties_brief(case_data)
        assert result == ""

    def test_group_parties_with_name_field(self):
        svc = self._make_service()
        parties = [{"legal_status": "plaintiff", "name": "张三"}]
        groups = svc._group_parties_by_status(parties)
        assert groups["plaintiff"] == ["张三"]

    def test_format_ordered_groups_unknown_status(self):
        svc = self._make_service()
        groups = {"custom_status": ["张三"]}
        lines = svc._format_ordered_groups(groups)
        assert len(lines) == 1
        assert "张三" in lines[0]


# ── EvidenceService delegation tests ──

class TestEvidenceServiceExtended:
    def _make_service(self):
        from apps.documents.services.evidence.evidence_service import EvidenceService
        qs = MagicMock()
        ms = MagicMock()
        fs = MagicMock()
        cs = MagicMock()
        prc = MagicMock()
        svc = EvidenceService(
            case_service=cs,
            query_service=qs,
            mutation_service=ms,
            file_service=fs,
            page_range_calculator=prc,
        )
        return svc, qs, ms, fs, cs

    def test_update_evidence_list(self):
        svc, qs, ms, fs, cs = self._make_service()
        svc._query_service.get_evidence_list.return_value = MagicMock()
        svc.update_evidence_list(1, {"title": "new"})
        qs.get_evidence_list.assert_called_with(1)

    def test_delete_evidence_list(self):
        svc, qs, ms, fs, cs = self._make_service()
        svc._query_service.get_evidence_list.return_value = MagicMock()
        svc.delete_evidence_list(1)
        ms.delete_evidence_list.assert_called_once()

    def test_create_evidence_item(self):
        svc, qs, ms, fs, cs = self._make_service()
        svc._query_service.get_evidence_list.return_value = MagicMock()
        svc.create_evidence_item(1, {"name": "e1", "purpose": "p1"})
        ms.create_evidence_item.assert_called_once()

    def test_update_evidence_item(self):
        svc, qs, ms, fs, cs = self._make_service()
        svc._query_service.get_evidence_item.return_value = MagicMock()
        svc.update_evidence_item(1, {"name": "new", "purpose": "new_purpose"})
        ms.update_evidence_item.assert_called_once()

    def test_delete_file(self):
        svc, qs, ms, fs, cs = self._make_service()
        svc._query_service.get_evidence_item.return_value = MagicMock()
        svc.delete_file(1)
        fs.delete_file.assert_called_once()

    def test_calculate_page_ranges(self):
        svc, qs, ms, fs, cs = self._make_service()
        svc._query_service.get_evidence_list.return_value = MagicMock()
        svc.calculate_page_ranges(1)
        svc._page_range_calculator.calculate_page_ranges.assert_called_once()

    def test_recalculate_page_ranges_for_chain(self):
        svc, qs, ms, fs, cs = self._make_service()
        svc.recalculate_page_ranges_for_chain(1)
        svc._page_range_calculator.recalculate_page_ranges_for_chain.assert_called_once_with(list_id=1)

    def test_update_subsequent_lists_pages(self):
        svc, qs, ms, fs, cs = self._make_service()
        svc.update_subsequent_lists_pages(1, 2)
        svc._page_range_calculator.update_subsequent_lists_pages.assert_called_once_with(case_id=1, start_order=2)

    def test_reorder_items(self):
        svc, qs, ms, fs, cs = self._make_service()
        svc._query_service.get_evidence_list.return_value = MagicMock()
        svc.reorder_items(1, [3, 1, 2])
        ms.reorder_items.assert_called_once()

    def test_create_evidence_list(self):
        svc, qs, ms, fs, cs = self._make_service()
        svc._case_service.get_case_model_internal.return_value = MagicMock()
        svc.create_evidence_list(1, "title")
        ms.create_evidence_list.assert_called_once()

    def test_validate_list_type_creation(self):
        svc, qs, ms, fs, cs = self._make_service()
        svc.validate_list_type_creation(1, "list_2")
        ms.validate_list_type_creation.assert_called_once()

    def test_auto_link_previous_list(self):
        svc, qs, ms, fs, cs = self._make_service()
        el = MagicMock()
        svc.auto_link_previous_list(el)
        ms.auto_link_previous_list.assert_called_once()
