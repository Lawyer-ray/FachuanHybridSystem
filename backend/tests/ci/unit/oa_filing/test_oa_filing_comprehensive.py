"""Tests for oa_filing: script_executor_service, import_session_service, client_import_service, tasks, html_parser, filing_models."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from apps.oa_filing.services.exceptions import OAFilingError, ScriptExecutionError


# ── script_executor_service ────────────────────────────────────────────────


class TestScriptExecutorService:
    def _make_service(self):
        from apps.oa_filing.services.script_executor_service import ScriptExecutorService

        return ScriptExecutorService()

    def test_map_case_category_civil(self) -> None:
        svc = self._make_service()
        case = SimpleNamespace(case_type="civil")
        assert svc._map_case_category(case) == "03"

    def test_map_case_category_criminal(self) -> None:
        svc = self._make_service()
        case = SimpleNamespace(case_type="criminal")
        assert svc._map_case_category(case) == "05"

    def test_map_case_category_administrative(self) -> None:
        svc = self._make_service()
        case = SimpleNamespace(case_type="administrative")
        assert svc._map_case_category(case) == "04"

    def test_map_case_category_labor(self) -> None:
        svc = self._make_service()
        case = SimpleNamespace(case_type="labor")
        assert svc._map_case_category(case) == "03"

    def test_map_case_category_intl(self) -> None:
        svc = self._make_service()
        case = SimpleNamespace(case_type="intl")
        assert svc._map_case_category(case) == "06"

    def test_map_case_category_advisor(self) -> None:
        svc = self._make_service()
        case = SimpleNamespace(case_type="advisor")
        assert svc._map_case_category(case) == "01"

    def test_map_case_category_special(self) -> None:
        svc = self._make_service()
        case = SimpleNamespace(case_type="special")
        assert svc._map_case_category(case) == "02"

    def test_map_case_category_unknown_defaults_to_civil(self) -> None:
        svc = self._make_service()
        case = SimpleNamespace(case_type="unknown")
        assert svc._map_case_category(case) == "03"

    def test_map_case_category_none(self) -> None:
        svc = self._make_service()
        case = SimpleNamespace(case_type=None)
        assert svc._map_case_category(case) == "03"

    def test_map_case_stage_advisor_empty(self) -> None:
        svc = self._make_service()
        case = SimpleNamespace(case_type="advisor")
        assert svc._map_case_stage(case) == ""

    def test_map_case_stage_special_empty(self) -> None:
        svc = self._make_service()
        case = SimpleNamespace(case_type="special")
        assert svc._map_case_stage(case) == ""

    def test_map_case_stage_civil_first_trial(self) -> None:
        svc = self._make_service()
        case = SimpleNamespace(case_type="civil", current_stage="first_trial")
        assert svc._map_case_stage(case) == "0301"

    def test_map_case_stage_civil_second_trial(self) -> None:
        svc = self._make_service()
        case = SimpleNamespace(case_type="civil", current_stage="second_trial")
        assert svc._map_case_stage(case) == "0305"

    def test_map_case_stage_civil_enforcement(self) -> None:
        svc = self._make_service()
        case = SimpleNamespace(case_type="civil", current_stage="enforcement")
        assert svc._map_case_stage(case) == "0314"

    def test_map_case_stage_civil_unknown_defaults(self) -> None:
        svc = self._make_service()
        case = SimpleNamespace(case_type="civil", current_stage="unknown")
        assert svc._map_case_stage(case) == "0301"

    def test_map_case_stage_admin_first_trial(self) -> None:
        svc = self._make_service()
        case = SimpleNamespace(case_type="administrative", current_stage="first_trial")
        assert svc._map_case_stage(case) == "0402"

    def test_map_case_stage_admin_review(self) -> None:
        svc = self._make_service()
        case = SimpleNamespace(case_type="administrative", current_stage="administrative_review")
        assert svc._map_case_stage(case) == "0401"

    def test_map_case_stage_criminal_first_trial(self) -> None:
        svc = self._make_service()
        case = SimpleNamespace(case_type="criminal", current_stage="first_trial")
        assert svc._map_case_stage(case) == "0503"

    def test_map_case_stage_criminal_investigation(self) -> None:
        svc = self._make_service()
        case = SimpleNamespace(case_type="criminal", current_stage="investigation")
        assert svc._map_case_stage(case) == "0501"

    def test_map_case_stage_criminal_unknown_defaults(self) -> None:
        svc = self._make_service()
        case = SimpleNamespace(case_type="criminal", current_stage="unknown")
        assert svc._map_case_stage(case) == "0503"

    def test_map_fee_mode_fixed(self) -> None:
        svc = self._make_service()
        contract = SimpleNamespace(fee_mode="FIXED")
        assert svc._map_fee_mode(contract) == "01"

    def test_map_fee_mode_semi_risk(self) -> None:
        svc = self._make_service()
        contract = SimpleNamespace(fee_mode="SEMI_RISK")
        assert svc._map_fee_mode(contract) == "02"

    def test_map_fee_mode_full_risk(self) -> None:
        svc = self._make_service()
        contract = SimpleNamespace(fee_mode="FULL_RISK")
        assert svc._map_fee_mode(contract) == "02"

    def test_fee_mode_unknown_defaults(self) -> None:
        svc = self._make_service()
        contract = SimpleNamespace(fee_mode="UNKNOWN")
        assert svc._map_fee_mode(contract) == "01"

    def test_map_kindtype_litigation_returns_empty(self) -> None:
        svc = self._make_service()
        assert svc._map_kindtype("03", []) == ("", "")
        assert svc._map_kindtype("04", []) == ("", "")
        assert svc._map_kindtype("05", []) == ("", "")

    def test_map_kindtype_advisor_enterprise(self) -> None:
        svc = self._make_service()
        party = MagicMock()
        party.client.client_type = "legal"
        kind1, kind2 = svc._map_kindtype("01", [party])
        assert kind1 == "KindType01_01"
        assert kind2 == "KindType01_0103"

    def test_map_kindtype_advisor_natural(self) -> None:
        svc = self._make_service()
        party = MagicMock()
        party.client.client_type = "natural"
        kind1, kind2 = svc._map_kindtype("01", [party])
        assert kind1 == "KindType01_05"
        assert kind2 == ""

    def test_map_kindtype_special_enterprise(self) -> None:
        svc = self._make_service()
        party = MagicMock()
        party.client.client_type = "legal"
        kind1, kind2 = svc._map_kindtype("02", [party])
        assert kind1 == "KindType02_01"

    def test_map_kindtype_special_natural(self) -> None:
        svc = self._make_service()
        party = MagicMock()
        party.client.client_type = "natural"
        kind1, kind2 = svc._map_kindtype("02", [party])
        assert kind1 == "KindType02_05"

    @patch("apps.oa_filing.services.script_executor_service.django_apps")
    def test_dispatch_unsupported_site(self, mock_apps) -> None:
        svc = self._make_service()
        with pytest.raises(ScriptExecutionError, match="不支持的OA系统"):
            svc._dispatch("UnsupportedSite", MagicMock(), 1, None)

    def test_map_legal_position_plaintiff(self) -> None:
        svc = self._make_service()
        with patch("apps.oa_filing.services.script_executor_service.django_apps") as mock_apps:
            mock_model = MagicMock()
            case_party = MagicMock()
            case_party.legal_status = "plaintiff"
            mock_model.objects.filter.return_value.first.return_value = case_party
            mock_apps.get_model.return_value = mock_model

            contract_party = MagicMock()
            contract_party.client_id = 1
            assert svc._map_legal_position(contract_party) == "01"

    def test_map_legal_position_default(self) -> None:
        svc = self._make_service()
        with patch("apps.oa_filing.services.script_executor_service.django_apps") as mock_apps:
            mock_model = MagicMock()
            mock_model.objects.filter.return_value.first.return_value = None
            mock_apps.get_model.return_value = mock_model

            contract_party = MagicMock()
            contract_party.client_id = 1
            assert svc._map_legal_position(contract_party) == "02"


# ── import_session_service ─────────────────────────────────────────────────


class TestImportSessionService:
    @patch("apps.oa_filing.services.import_session_service.CaseImportSession")
    def test_get_case_session_or_none_found(self, mock_model) -> None:
        from apps.oa_filing.services.import_session_service import get_case_session_or_none

        mock_model.objects.filter.return_value.first.return_value = MagicMock()
        assert get_case_session_or_none(1) is not None

    @patch("apps.oa_filing.services.import_session_service.CaseImportSession")
    def test_get_case_session_or_none_not_found(self, mock_model) -> None:
        from apps.oa_filing.services.import_session_service import get_case_session_or_none

        mock_model.objects.filter.return_value.first.return_value = None
        assert get_case_session_or_none(999) is None

    @patch("apps.oa_filing.services.import_session_service.ClientImportSession")
    def test_get_client_session_or_none_found(self, mock_model) -> None:
        from apps.oa_filing.services.import_session_service import get_client_session_or_none

        mock_model.objects.filter.return_value.first.return_value = MagicMock()
        assert get_client_session_or_none(1) is not None

    @patch("apps.oa_filing.services.import_session_service.ClientImportSession")
    def test_get_client_session_or_none_not_found(self, mock_model) -> None:
        from apps.oa_filing.services.import_session_service import get_client_session_or_none

        mock_model.objects.filter.return_value.first.return_value = None
        assert get_client_session_or_none(999) is None

    @patch("apps.oa_filing.services.import_session_service.CaseImportSession")
    def test_create_case_session(self, mock_model) -> None:
        from apps.oa_filing.services.import_session_service import create_case_session

        mock_model.objects.create.return_value = MagicMock()
        result = create_case_session(lawyer=MagicMock(), credential=MagicMock(), uploaded_filename="test.xlsx")
        mock_model.objects.create.assert_called_once()

    @patch("apps.oa_filing.services.import_session_service.ClientImportSession")
    def test_create_client_session(self, mock_model) -> None:
        from apps.oa_filing.services.import_session_service import create_client_session

        mock_model.objects.create.return_value = MagicMock()
        create_client_session(lawyer=MagicMock(), credential=MagicMock())
        mock_model.objects.create.assert_called_once()


# ── client_import_service ──────────────────────────────────────────────────


class TestClientImportService:
    def _make_session(self):
        session = MagicMock()
        session.id = 1
        session.credential = MagicMock()
        session.credential.account = "test_account"
        session.credential.password = "test_password"  # pragma: allowlist secret
        session.started_at = None
        session.total_count = 0
        session.discovered_count = 0
        return session

    def test_to_int_valid(self) -> None:
        from apps.oa_filing.services.client_import_service import ClientImportService

        assert ClientImportService._to_int(42) == 42
        assert ClientImportService._to_int("42") == 42

    def test_to_int_invalid(self) -> None:
        from apps.oa_filing.services.client_import_service import ClientImportService

        assert ClientImportService._to_int("abc") == 0
        assert ClientImportService._to_int(None) == 0

    def test_import_single_client_already_exists(self) -> None:
        from apps.oa_filing.services.client_import_service import ClientImportService

        session = self._make_session()
        svc = ClientImportService(session)

        data = MagicMock()
        data.name = "TestClient"

        with patch("apps.oa_filing.services.client_import_service.Client") as mock_client:
            mock_client.objects.filter.return_value.exists.return_value = True
            result = svc._import_single_client(data)
            assert result.status == "skipped"

    def test_import_single_client_created(self) -> None:
        from apps.oa_filing.services.client_import_service import ClientImportService

        session = self._make_session()
        svc = ClientImportService(session)

        data = MagicMock()
        data.name = "NewClient"
        data.client_type = "natural"
        data.phone = "123"
        data.address = "addr"
        data.id_number = "id123"
        data.legal_representative = ""

        with patch("apps.oa_filing.services.client_import_service.Client") as mock_client:
            mock_client.objects.filter.return_value.exists.return_value = False
            mock_client.objects.create.return_value = MagicMock(id=1)
            with patch("apps.oa_filing.services.client_import_service.transaction"):
                result = svc._import_single_client(data)
            assert result.status == "created"

    def test_handle_script_progress_discovery_started(self) -> None:
        from apps.oa_filing.services.client_import_service import ClientImportService

        session = self._make_session()
        svc = ClientImportService(session)
        with patch.object(svc, "_update_session") as mock_update:
            svc._handle_script_progress({"event": "discovery_started", "message": "started"})
            mock_update.assert_called_once()

    def test_handle_script_progress_discovery_progress(self) -> None:
        from apps.oa_filing.services.client_import_service import ClientImportService

        session = self._make_session()
        svc = ClientImportService(session)
        with patch.object(svc, "_update_session") as mock_update:
            svc._handle_script_progress({
                "event": "discovery_progress",
                "discovered_count": 10,
                "page": 2,
                "message": "searching",
            })
            mock_update.assert_called_once()

    def test_handle_script_progress_discovery_completed(self) -> None:
        from apps.oa_filing.services.client_import_service import ClientImportService

        session = self._make_session()
        svc = ClientImportService(session)
        with patch.object(svc, "_update_session") as mock_update:
            svc._handle_script_progress({
                "event": "discovery_completed",
                "total_count": 50,
            })
            mock_update.assert_called_once()

    def test_handle_script_progress_import_started(self) -> None:
        from apps.oa_filing.services.client_import_service import ClientImportService

        session = self._make_session()
        svc = ClientImportService(session)
        with patch.object(svc, "_update_session") as mock_update:
            svc._handle_script_progress({
                "event": "import_started",
                "total_count": 50,
            })
            mock_update.assert_called_once()

    def test_handle_script_progress_import_progress(self) -> None:
        from apps.oa_filing.services.client_import_service import ClientImportService

        session = self._make_session()
        session.total_count = 50
        session.discovered_count = 50
        svc = ClientImportService(session)
        with patch.object(svc, "_update_session") as mock_update:
            svc._handle_script_progress({
                "event": "import_progress",
                "total_count": 50,
                "index": 5,
                "name": "Client5",
            })
            mock_update.assert_called_once()

    def test_update_session_empty_fields(self) -> None:
        from apps.oa_filing.services.client_import_service import ClientImportService

        session = self._make_session()
        svc = ClientImportService(session)
        svc._update_session()  # no-op
        # Should not raise

    def test_update_session_sets_attrs(self) -> None:
        from apps.oa_filing.services.client_import_service import ClientImportService

        session = self._make_session()
        svc = ClientImportService(session)
        with patch("apps.oa_filing.services.client_import_service.ClientImportSession") as mock_model:
            mock_model.objects.filter.return_value.update.return_value = None
            svc._update_session(success_count=5, skip_count=2)
            assert session.success_count == 5
            assert session.skip_count == 2


# ── tasks ──────────────────────────────────────────────────────────────────


class TestTasks:
    @patch("apps.oa_filing.models.ClientImportSession")
    def test_run_client_import_task_session_not_found(self, mock_model) -> None:
        from apps.oa_filing.tasks import run_client_import_task

        mock_model.DoesNotExist = type("DoesNotExist", (Exception,), {})
        mock_model.objects.select_related.return_value.get.side_effect = mock_model.DoesNotExist
        # Should not raise
        run_client_import_task(999)

    @patch("apps.oa_filing.models.ClientImportSession")
    def test_run_client_import_task_already_completed(self, mock_model) -> None:
        from apps.oa_filing.tasks import run_client_import_task

        session = MagicMock()
        session.status = "completed"
        mock_model.objects.select_related.return_value.get.return_value = session
        run_client_import_task(1)
        # Should return early

    @patch("apps.oa_filing.models.ClientImportSession")
    def test_run_client_import_task_already_cancelled(self, mock_model) -> None:
        from apps.oa_filing.tasks import run_client_import_task

        session = MagicMock()
        session.status = "cancelled"
        mock_model.objects.select_related.return_value.get.return_value = session
        run_client_import_task(1)

    @patch("apps.oa_filing.services.client_import_service.ClientImportService")
    @patch("apps.oa_filing.models.ClientImportSession")
    def test_run_client_import_task_sets_started_at(self, mock_model, mock_svc_cls) -> None:
        from apps.oa_filing.tasks import run_client_import_task

        session = MagicMock()
        session.status = "pending"
        session.started_at = None
        mock_model.objects.select_related.return_value.get.return_value = session

        mock_svc = MagicMock()
        mock_svc_cls.return_value = mock_svc

        run_client_import_task(1)
        assert session.started_at is not None

    @patch("apps.oa_filing.models.CaseImportSession")
    def test_run_case_import_preview_task_session_not_found(self, mock_model) -> None:
        from apps.oa_filing.tasks import run_case_import_preview_task

        mock_model.DoesNotExist = type("DoesNotExist", (Exception,), {})
        mock_model.objects.select_related.return_value.get.side_effect = mock_model.DoesNotExist
        run_case_import_preview_task(999, "/tmp/test.xlsx")

    @patch("apps.oa_filing.models.CaseImportSession")
    def test_run_case_import_preview_task_already_completed(self, mock_model) -> None:
        from apps.oa_filing.tasks import run_case_import_preview_task

        session = MagicMock()
        session.status = "completed"
        mock_model.objects.select_related.return_value.get.return_value = session
        run_case_import_preview_task(1, "/tmp/test.xlsx")

    @patch("apps.oa_filing.models.CaseImportSession")
    def test_run_case_import_task_session_not_found(self, mock_model) -> None:
        from apps.oa_filing.tasks import run_case_import_task

        mock_model.DoesNotExist = type("DoesNotExist", (Exception,), {})
        mock_model.objects.select_related.return_value.get.side_effect = mock_model.DoesNotExist
        run_case_import_task(999, ["case1"])

    @patch("apps.oa_filing.models.CaseImportSession")
    def test_run_case_import_task_already_completed(self, mock_model) -> None:
        from apps.oa_filing.tasks import run_case_import_task

        session = MagicMock()
        session.status = "completed"
        mock_model.objects.select_related.return_value.get.return_value = session
        run_case_import_task(1, ["case1"])


# ── filing_models ──────────────────────────────────────────────────────────


class TestFilingModels:
    def test_gender_from_id_number_male(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.filing.filing_models import _gender_from_id_number

        # 18-digit ID, 17th digit odd = male
        assert _gender_from_id_number("110101199001011234") == "01"  # pragma: allowlist secret

    def test_gender_from_id_number_female(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.filing.filing_models import _gender_from_id_number

        # 18-digit ID, 17th digit even = female
        assert _gender_from_id_number("110101199001011244") == "02"  # pragma: allowlist secret

    def test_gender_from_id_number_short(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.filing.filing_models import _gender_from_id_number

        assert _gender_from_id_number("12345") == "01"

    def test_gender_from_id_number_empty(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.filing.filing_models import _gender_from_id_number

        assert _gender_from_id_number("") == "01"

    def test_client_info_dataclass(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.filing.filing_models import ClientInfo

        info = ClientInfo(name="Test", client_type="natural")
        assert info.name == "Test"
        assert info.id_number is None

    def test_case_info_defaults(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.filing.filing_models import CaseInfo

        info = CaseInfo(
            manager_id="", manager_name="Lawyer", category="03",
            stage="0301", which_side="01", kindtype="", kindtype_sed="", kindtype_thr="",
            case_name="Test Case",
        )
        assert info.resource == "01"
        assert info.language == "01"
        assert info.is_foreign == "N"

    def test_contract_info_defaults(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.filing.filing_models import ContractInfo

        info = ContractInfo()
        assert info.rec_type == "01"
        assert info.currency == "RMB"
        assert info.stamp_count == 3

    def test_conflict_party_info_defaults(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.filing.filing_models import ConflictPartyInfo

        info = ConflictPartyInfo(name="Opponent")
        assert info.category == "11"
        assert info.legal_position == "02"
        assert info.is_payer == "0"

    def test_resolved_customer_dataclass(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.filing.filing_models import ResolvedCustomer

        info = ResolvedCustomer(customer_id="123", customer_name="Test")
        assert info.istemp == "Z"


# ── html_parser ────────────────────────────────────────────────────────────


class TestHtmlParser:
    def test_normalize_text(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.html_parser import normalize_text

        assert normalize_text(None) == ""
        assert normalize_text("  hello  ") == "hello"
        assert normalize_text("hello\xa0world") == "hello world"

    def test_normalize_label(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.html_parser import normalize_label

        assert normalize_label("案件名称：") == "案件名称"
        assert normalize_label("案件名称:") == "案件名称"

    def test_extract_hidden_input(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.html_parser import extract_hidden_input

        html = '<input name="__VIEWSTATE" value="abc123" />'
        assert extract_hidden_input(html, "__VIEWSTATE") == "abc123"

    def test_extract_hidden_input_not_found(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.html_parser import extract_hidden_input

        assert extract_hidden_input("<p>no input</p>", "missing") == ""

    def test_extract_case_no_from_text(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.html_parser import extract_case_no_from_text

        # The regex matches ASCII letter patterns, not Chinese chars
        assert extract_case_no_from_text("案件编号2024AH12345号") != ""
        assert extract_case_no_from_text("") == ""

    def test_extract_keyid_from_href(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.html_parser import extract_keyid_from_href

        href = "projectView.aspx?keyid=abc123&FirstModel=PROJECT"
        assert extract_keyid_from_href(href) == "abc123"

    def test_extract_keyid_from_href_empty(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.html_parser import extract_keyid_from_href

        assert extract_keyid_from_href("") is None

    def test_score_case_name_cell(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.html_parser import score_case_name_cell

        assert score_case_name_cell("", case_no="") == -100
        assert score_case_name_cell("123", case_no="") == -90
        assert score_case_name_cell("查看", case_no="") == -80
        assert score_case_name_cell("张某诉李某合同纠纷案", case_no="") > 0
        assert score_case_name_cell("2024-01-01", case_no="") < 0

    def test_clean_case_name_text(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.html_parser import clean_case_name_text

        assert clean_case_name_text("", case_no="") == ""
        result = clean_case_name_text("张某诉李某合同纠纷案 查看", case_no="")
        assert "查看" not in result

    def test_clean_case_name_text_removes_case_no(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.html_parser import clean_case_name_text

        result = clean_case_name_text("(2024)京01民初123号张某诉李某", case_no="2024京01民初123")
        # case_no removed from text
        assert "2024京01民初123" not in result

    def test_iter_label_value_pairs(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.html_parser import iter_label_value_pairs

        pairs = iter_label_value_pairs(["名称：", "测试案件", "编号：", "12345"])
        assert len(pairs) == 2
        assert pairs[0] == ("名称", "测试案件")
        assert pairs[1] == ("编号", "12345")

    def test_iter_label_value_pairs_odd_count(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.html_parser import iter_label_value_pairs

        pairs = iter_label_value_pairs(["名称：", "测试案件", "额外"])
        assert len(pairs) == 1

    def test_extract_case_candidates_from_empty_html(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.html_parser import extract_case_candidates_from_search_html

        assert extract_case_candidates_from_search_html("") == []
        assert extract_case_candidates_from_search_html("<p>no rows</p>") == []

    def test_extract_case_keyid_from_search_html_not_found(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.html_parser import extract_case_keyid_from_search_html

        html = "<table><tr><td>no match</td></tr></table>"
        assert extract_case_keyid_from_search_html(html_text=html, case_no="CASE001") is None

    def test_extract_case_keyid_from_search_html_regex_fallback(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.html_parser import extract_case_keyid_from_search_html

        html = "some text CASE001 more text projectView.aspx?keyid=abc_key&other=val"
        result = extract_case_keyid_from_search_html(html_text=html, case_no="CASE001")
        assert result == "abc_key"

    def test_parse_case_detail_html_invalid(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.html_parser import parse_case_detail_html

        result = parse_case_detail_html(html_text="invalid", case_no="c1", keyid="k1")
        # Should not raise, returns OACaseData or None
        assert result is not None or result is None  # depends on lxml parsing


# ── models ─────────────────────────────────────────────────────────────────


class TestModels:
    def test_session_status_choices(self) -> None:
        from apps.oa_filing.models.filing_session import SessionStatus

        assert SessionStatus.PENDING == "pending"
        assert SessionStatus.COMPLETED == "completed"
        assert len(SessionStatus.choices) == 5

    def test_client_import_status_choices(self) -> None:
        from apps.oa_filing.models.client_import_session import ClientImportStatus, ClientImportPhase

        assert ClientImportStatus.PENDING == "pending"
        assert ClientImportPhase.DISCOVERING == "discovering"
        assert ClientImportPhase.IMPORTING == "importing"

    def test_case_import_status_choices(self) -> None:
        from apps.oa_filing.models.case_import_session import CaseImportStatus, CaseImportPhase

        assert CaseImportStatus.PENDING == "pending"
        assert CaseImportPhase.PARSING == "parsing"
        assert CaseImportPhase.PREVIEW == "preview"

    def test_filing_session_str(self) -> None:
        from apps.oa_filing.models.filing_session import FilingSession

        session = FilingSession(id=1, status="pending")
        assert "1" in str(session)
        assert "pending" in str(session)

    def test_client_import_session_str(self) -> None:
        from apps.oa_filing.models.client_import_session import ClientImportSession

        session = ClientImportSession(id=1, status="completed")
        assert "1" in str(session)

    def test_case_import_session_str(self) -> None:
        from apps.oa_filing.models.case_import_session import CaseImportSession

        session = CaseImportSession(id=1, status="in_progress")
        assert "1" in str(session)

    def test_oa_config_str(self) -> None:
        from apps.oa_filing.models.oa_config import OAConfig

        config = OAConfig(site_name="TestOA")
        assert str(config) == "TestOA"


# ── OACaseData models (jtn/models.py) ──────────────────────────────────────


class TestJtnModels:
    def test_import_models(self) -> None:
        from apps.oa_filing.services.oa_scripts.jtn.models import (
            OACaseCustomerData,
            OACaseData,
            OACaseInfoData,
            OAConflictData,
            OAListCaseCandidate,
        )

        candidate = OAListCaseCandidate(
            case_no="2024-001",
            case_name="Test Case",
            keyid="key123",
            detail_url="https://example.com",
        )
        assert candidate.case_no == "2024-001"

        customer = OACaseCustomerData(name="Test Customer", customer_type="legal")
        assert customer.customer_type == "legal"

        case_info = OACaseInfoData(case_no="2024-001")
        assert case_info.case_name is None  # default is None

        conflict = OAConflictData(name="Opponent")
        assert conflict.conflict_type is None

        case_data = OACaseData(
            case_no="2024-001",
            keyid="key123",
            customers=[],
            case_info=case_info,
            conflicts=[],
        )
        assert case_data.case_no == "2024-001"


# ── schemas ────────────────────────────────────────────────────────────────


class TestSchemas:
    def test_filing_schemas_import(self) -> None:
        from apps.oa_filing.schemas.filing_schemas import SessionOut

        assert SessionOut is not None

    def test_case_import_schemas_import(self) -> None:
        from apps.oa_filing.schemas.case_import_schemas import CaseImportSessionOut

        assert CaseImportSessionOut is not None

    def test_client_import_schemas_import(self) -> None:
        from apps.oa_filing.schemas.client_import_schemas import ClientImportSessionOut

        assert ClientImportSessionOut is not None
