"""JTNAdapter 薄委托行为单测（立案装配 / 盖章归档脚本委托 / open_page 会话登记 / 导入委托）。

adapter 不含 Playwright 逻辑——各 JtnXxxScript 门面全部 mock，
断言：构造参数（account/password/headless/progress_callback）、调用契约、
session 句柄登记进 _opened_sessions 与全局防-GC 列表并清理断连会话。
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.oa_filing.services.exceptions import ScriptExecutionError
from apps.oa_filing.services.oa_scripts.jtn import adapter as jtn_adapter_mod
from apps.oa_filing.services.oa_scripts.jtn.adapter import JTNAdapter


def _make_client(**overrides: Any) -> Any:
    base = {
        "name": "客户甲",
        "client_type": "legal",
        "id_number": "91310000MA1K31X000",
        "address": "上海市黄浦区",
        "phone": "021-63330000",
        "legal_representative": "张三",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _agen(items: list[Any]) -> Any:
    async def gen() -> Any:
        for item in items:
            yield item

    return gen()


def _make_session_handle(connected: bool = True) -> MagicMock:
    handle = MagicMock()
    handle.browser.is_connected.return_value = connected
    return handle


# ──────────── _cleanup_stale_sessions ────────────


class TestCleanupStaleSessions:
    def test_removes_disconnected_only(self, monkeypatch: pytest.MonkeyPatch):
        alive = _make_session_handle(connected=True)
        dead = _make_session_handle(connected=False)
        monkeypatch.setattr(jtn_adapter_mod, "_active_browser_sessions", [alive, dead])

        jtn_adapter_mod._cleanup_stale_sessions()

        assert jtn_adapter_mod._active_browser_sessions == [alive]


# ──────────── execute_filing（数据装配） ────────────


class TestExecuteFiling:
    @pytest.fixture
    def _models(self, monkeypatch: pytest.MonkeyPatch) -> dict[str, MagicMock]:
        principal = [MagicMock(client=_make_client())]
        opposing = [MagicMock(client=_make_client(name="对方乙", client_type="natural"))]

        contract_party_model = MagicMock()

        def party_filter(**kwargs: Any) -> MagicMock:
            chain = MagicMock()
            if kwargs.get("role") == "PRINCIPAL":
                chain.select_related.return_value.aiterator.return_value = _agen(principal)
                chain.values_list.return_value.aiterator.return_value = _agen([101])
            else:
                chain.select_related.return_value.aiterator.return_value = _agen(opposing)
            return chain

        contract_party_model.objects.filter.side_effect = party_filter

        assignment_model = MagicMock()

        def assignment_filter(**kwargs: Any) -> MagicMock:
            chain = MagicMock()
            if kwargs.get("is_primary"):
                chain.select_related.return_value.afirst = AsyncMock(return_value=None)
            else:
                chain.select_related.return_value.afirst = AsyncMock(
                    return_value=MagicMock(lawyer=SimpleNamespace(real_name="李主办"))
                )
            return chain

        assignment_model.objects.filter.side_effect = assignment_filter

        case_model = MagicMock()
        case_model.objects.aget = AsyncMock(
            return_value=SimpleNamespace(case_type="civil", current_stage="first_trial", start_date=date(2026, 3, 1))
        )
        contract_model = MagicMock()
        contract_model.objects.aget = AsyncMock(
            return_value=SimpleNamespace(
                name="法律服务合同",
                case_type="advisor",
                start_date=None,
                end_date=None,
                fixed_amount=None,
                fee_mode="FIXED",
            )
        )
        case_party_model = MagicMock()

        def case_party_filter(**kwargs: Any) -> MagicMock:
            chain = MagicMock()
            if "client_id__in" in kwargs:
                chain.afirst = AsyncMock(return_value=SimpleNamespace(legal_status="plaintiff"))
            else:
                chain.afirst = AsyncMock(return_value=SimpleNamespace(legal_status="defendant"))
            return chain

        case_party_model.objects.filter.side_effect = case_party_filter

        models = {
            "Case": case_model,
            "Contract": contract_model,
            "ContractParty": contract_party_model,
            "ContractAssignment": assignment_model,
            "CaseParty": case_party_model,
        }
        monkeypatch.setattr(
            jtn_adapter_mod,
            "django_apps",
            SimpleNamespace(get_model=MagicMock(side_effect=lambda app, name: models[name])),
        )
        return models

    @pytest.mark.asyncio
    async def test_assembles_and_runs_script_with_case(self, _models: dict[str, MagicMock]):
        adapter = JTNAdapter("acc", "pwd")
        with patch("apps.oa_filing.services.oa_scripts.jtn.filing.JtnFilingScript") as script_cls:
            script = script_cls.return_value
            script.run = AsyncMock()

            await adapter.execute_filing(session=None, credential="cred", contract_id=1, case_id=2)

        script_cls.assert_called_once_with(account="acc", password="p")
        script.run.assert_awaited_once()
        clients = script.run.await_args.args[0]
        kwargs = script.run.await_args.kwargs
        assert clients[0].name == "客户甲"
        case_info = kwargs["case_info"]
        assert case_info.category == "03"
        assert case_info.stage == "0301"
        assert case_info.which_side == "01"
        assert case_info.manager_name == "李主办"
        assert case_info.case_name == "法律服务合同"
        assert case_info.start_date == "2026-03-01"
        assert case_info.contact_name == "/"
        conflict_parties = kwargs["conflict_parties"]
        assert conflict_parties[0].name == "对方乙"
        assert conflict_parties[0].legal_position == "02"
        assert conflict_parties[0].customer_type == "11"
        contract_info = kwargs["contract_info"]
        assert contract_info.rec_type == "01"
        assert contract_info.amount == ""
        assert contract_info.stamp_count == 3  # 1 委托方 + 2
        assert contract_info.currency == "RMB"

    @pytest.mark.asyncio
    async def test_without_case_id_uses_contract_defaults(self, _models: dict[str, MagicMock]):
        adapter = JTNAdapter("acc", "pwd")
        with patch("apps.oa_filing.services.oa_scripts.jtn.filing.JtnFilingScript") as script_cls:
            script = script_cls.return_value
            script.run = AsyncMock()

            await adapter.execute_filing(session=None, credential="cred", contract_id=1, case_id=None)

        case_info = script.run.await_args.kwargs["case_info"]
        # 无案件 → 按合同类型映射（advisor→01），阶段为空，我方默认，日期取合同
        assert case_info.category == "01"
        assert case_info.stage == ""
        assert case_info.which_side == "01"
        assert case_info.start_date == ""
        assert case_info.kindtype == "KindType01_01"
        assert case_info.kindtype_sed == "KindType01_0103"

    @pytest.mark.asyncio
    async def test_no_principal_raises(self, monkeypatch: pytest.MonkeyPatch):
        contract_party_model = MagicMock()

        def party_filter(**kwargs: Any) -> MagicMock:
            chain = MagicMock()
            chain.select_related.return_value.aiterator.return_value = _agen([])
            chain.values_list.return_value.aiterator.return_value = _agen([])
            return chain

        contract_party_model.objects.filter.side_effect = party_filter
        monkeypatch.setattr(
            jtn_adapter_mod,
            "django_apps",
            SimpleNamespace(get_model=MagicMock(return_value=MagicMock(objects=contract_party_model.objects))),
        )
        adapter = JTNAdapter("acc", "pwd")
        with pytest.raises(ScriptExecutionError, match="合同没有委托方当事人"):
            await adapter.execute_filing(session=None, credential="cred", contract_id=1, case_id=None)


# ──────────── 盖章 / 归档委托 ────────────


class TestStampArchiveDelegation:
    @pytest.mark.asyncio
    async def test_execute_stamp_builds_form_and_runs(self):
        adapter = JTNAdapter("acc", "pwd")
        session = SimpleNamespace(
            credential=SimpleNamespace(account="acc", password="p"),
            oa_case_number="OA-66",
            file_path="/media/contracts/所函.pdf",
        )
        with patch("apps.oa_filing.services.oa_scripts.jtn.stamp.JtnStampScript") as script_cls:
            script = script_cls.return_value
            script.run = AsyncMock()
            await adapter.execute_stamp(session)

        script_cls.assert_called_once_with(account="acc", password="p")
        form = script.run.await_args.args[0]
        assert form.oa_case_number == "OA-66"
        assert form.file_path == "/media/contracts/所函.pdf"

    @pytest.mark.asyncio
    async def test_execute_stamp_without_credential_raises(self):
        adapter = JTNAdapter("acc", "pwd")
        session = SimpleNamespace(credential=None, oa_case_number="OA-1", file_path="/x.pdf")
        with pytest.raises(RuntimeError, match="盖章申请缺少 OA 登录凭证"):
            await adapter.execute_stamp(session)

    @pytest.mark.asyncio
    async def test_execute_archive_builds_form_and_runs(self):
        adapter = JTNAdapter("acc", "pwd")
        session = SimpleNamespace(
            credential=SimpleNamespace(account="acc", password="p"),
            oa_case_number="OA-77",
            file_paths=["/media/1.pdf", "/media/2.pdf"],
        )
        with patch("apps.oa_filing.services.oa_scripts.jtn.archive.JtnArchiveScript") as script_cls:
            script = script_cls.return_value
            script.run = AsyncMock()
            await adapter.execute_archive(session)

        script_cls.assert_called_once_with(account="acc", password="p")
        form = script.run.await_args.args[0]
        assert form.oa_case_number == "OA-77"
        assert form.file_paths == ["/media/1.pdf", "/media/2.pdf"]

    @pytest.mark.asyncio
    async def test_execute_archive_without_credential_raises(self):
        adapter = JTNAdapter("acc", "pwd")
        session = SimpleNamespace(credential=None, oa_case_number="OA-1", file_paths=[])
        with pytest.raises(RuntimeError, match="归档申请缺少 OA 登录凭证"):
            await adapter.execute_archive(session)


# ──────────── open_* 页面委托与会话登记 ────────────


class TestWaitOpenBrowsersClosedEdgeCases:
    @pytest.mark.asyncio
    async def test_wait_failure_and_stale_registry_entry_tolerated(self, monkeypatch: pytest.MonkeyPatch):
        """wait_user_closed 抛错与全局列表缺失项均不上抛，会话仍被回收。"""
        monkeypatch.setattr(jtn_adapter_mod, "_active_browser_sessions", [])
        adapter = JTNAdapter("acc", "pwd")
        handle = _make_session_handle(connected=True)
        handle.wait_user_closed = AsyncMock(side_effect=RuntimeError("wait failed"))
        adapter._opened_sessions.append(handle)  # 不进全局列表 → remove 触发 ValueError 分支

        with patch.object(jtn_adapter_mod, "close_browser_session", AsyncMock()) as close:
            await adapter.wait_open_browsers_closed()  # 不应抛

        handle.wait_user_closed.assert_awaited_once()
        close.assert_awaited_once_with(handle)
        assert adapter._opened_sessions == []


class TestOpenPages:
    @pytest.mark.parametrize(
        ("method_name", "script_path", "open_args"),
        [
            (
                "open_oa_page",
                "apps.oa_filing.services.oa_scripts.jtn.archive.JtnArchiveScript",
                ("OA-1", "小结", ["/f.pdf"]),
            ),
            ("open_invoice_page", "apps.oa_filing.services.oa_scripts.jtn.invoice.JtnInvoiceScript", ("OA-2",)),
            ("open_stamp_page", "apps.oa_filing.services.oa_scripts.jtn.stamp.JtnStampScript", ("OA-3",)),
            (
                "open_conflict_check_page",
                "apps.oa_filing.services.oa_scripts.jtn.conflict_check.JtnConflictCheckScript",
                ("当事人甲",),
            ),
        ],
    )
    @pytest.mark.asyncio
    async def test_open_page_registers_session(
        self,
        monkeypatch: pytest.MonkeyPatch,
        method_name: str,
        script_path: str,
        open_args: tuple[str, ...],
    ) -> None:
        stale = _make_session_handle(connected=False)
        monkeypatch.setattr(jtn_adapter_mod, "_active_browser_sessions", [stale])
        handle = _make_session_handle(connected=True)
        credential = SimpleNamespace(account="acc", password="p")
        adapter = JTNAdapter("acc", "pwd")

        with patch(script_path) as script_cls:
            script = script_cls.return_value
            script.open_page = AsyncMock(return_value=handle)
            await getattr(adapter, method_name)(credential, *open_args)

        script_cls.assert_called_once_with(account="acc", password="p")
        script.open_page.assert_awaited_once_with(*open_args)
        assert handle in adapter._opened_sessions
        assert handle in jtn_adapter_mod._active_browser_sessions
        assert stale not in jtn_adapter_mod._active_browser_sessions  # 断连会话被清理


# ──────────── 案件导入委托 ────────────


class TestCaseImportDelegation:
    @pytest.mark.asyncio
    async def test_execute_case_import_delegates_to_service(self):
        adapter = JTNAdapter("acc", "pwd")
        session = SimpleNamespace(result_data={"case_nos": ["A-1", "A-2"], "matched_case_nos": ["A-1"]})
        with patch("apps.oa_filing.services.case_import_service.CaseImportService") as svc_cls:
            svc_cls.return_value.run_import = MagicMock()
            await adapter.execute_case_import(session)

        svc_cls.assert_called_once_with(session)
        svc_cls.return_value.run_import.assert_called_once_with(case_nos=["A-1", "A-2"], matched_case_nos=["A-1"])

    @pytest.mark.asyncio
    async def test_fetch_case_detail_returns_script_result(self):
        adapter = JTNAdapter("acc", "pwd")
        credential = SimpleNamespace(account="acc", password="p")
        with patch("apps.oa_filing.services.oa_scripts.jtn.case_import.JtnCaseImportScript") as script_cls:
            script_cls.return_value.search_case = AsyncMock(return_value="oa-case-data")
            result = await adapter.fetch_case_detail("CASE-9", credential)

        assert result == "oa-case-data"
        script_cls.assert_called_once_with(account="acc", password="p")
        script_cls.return_value.search_case.assert_awaited_once_with("CASE-9")

    def test_search_cases_forwards_options(self):
        adapter = JTNAdapter("acc", "pwd")
        credential = SimpleNamespace(account="acc", password="p")
        progress = MagicMock()
        with patch("apps.oa_filing.services.oa_scripts.jtn.case_import.JtnCaseImportScript") as script_cls:
            script_cls.return_value.search_cases = MagicMock(return_value="gen")
            result = adapter.search_cases(
                ["A-1", "A-2", "A-3"], credential, workers=3, headless=False, progress_callback=progress
            )

        assert result == "gen"
        script_cls.assert_called_once_with(account="acc", password="p", headless=False, progress_callback=progress)
        script_cls.return_value.search_cases.assert_called_once_with(
            ["A-1", "A-2", "A-3"], workers=3, playwright_fallback=True
        )

    def test_build_case_detail_url(self):
        adapter = JTNAdapter("acc", "pwd")
        url = adapter.build_case_detail_url(SimpleNamespace(keyid="K123"))
        assert url == (
            "https://ims.jtn.com/project/projectView.aspx?keyid=K123&FirstModel=PROJECT&SecondModel=PROJECT002"
        )


# ──────────── 客户导入委托 ────────────


class TestClientImportDelegation:
    @pytest.mark.asyncio
    async def test_execute_client_import_delegates_to_service(self):
        adapter = JTNAdapter("acc", "pwd")
        session = SimpleNamespace()
        with patch("apps.oa_filing.services.client_import_service.ClientImportService") as svc_cls:
            svc_cls.return_value.run_import = MagicMock()
            await adapter.execute_client_import(session, headless=False, limit=5)

        svc_cls.assert_called_once_with(session)
        svc_cls.return_value.run_import.assert_called_once_with(headless=False, limit=5)

    def test_iter_customers_builds_script_and_runs(self):
        adapter = JTNAdapter("acc", "pwd")
        credential = SimpleNamespace(account="acc", password="p")
        session = SimpleNamespace(credential=credential)
        progress = MagicMock()
        with patch("apps.oa_filing.services.oa_scripts.jtn.client_import.JtnClientImportScript") as script_cls:
            script_cls.return_value.run = MagicMock(return_value="agen")
            result = adapter.iter_customers(session, headless=False, limit=7, progress_callback=progress)

        assert result == "agen"
        script_cls.assert_called_once_with(account="acc", password="p", headless=False, progress_callback=progress)
        script_cls.return_value.run.assert_called_once_with(limit=7)


# ──────────── 对方当事人诉讼地位映射 ────────────


class TestAsyncMapLegalPosition:
    @pytest.mark.asyncio
    async def test_mapping_by_legal_status(self, monkeypatch: pytest.MonkeyPatch):
        cases = [
            (SimpleNamespace(legal_status="plaintiff"), "01"),
            (SimpleNamespace(legal_status="defendant"), "02"),
            (SimpleNamespace(legal_status="third"), "09"),
            (SimpleNamespace(legal_status=None), "02"),
            (None, "02"),
        ]
        for case_party, expected in cases:
            case_party_model = MagicMock()
            case_party_model.objects.filter.return_value.afirst = AsyncMock(return_value=case_party)
            monkeypatch.setattr(
                jtn_adapter_mod, "django_apps", SimpleNamespace(get_model=MagicMock(return_value=case_party_model))
            )
            adapter = JTNAdapter("acc", "pwd")
            contract_party = SimpleNamespace(client_id=5)
            assert await adapter._async_map_legal_position(contract_party) == expected
            case_party_model.objects.filter.assert_called_once_with(client_id=5)
