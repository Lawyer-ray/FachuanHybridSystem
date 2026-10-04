"""ScriptExecutorService 调度链路单测（session 查询/凭证查找/线程分发/open_page）。

覆盖 script_executor_service 中未被既有用例覆盖的分支：
- _friendly_error_message / _ensure_*_access / session 属主过滤 / _find_credential
- 立案、盖章、归档的 execute_* 入口参数装配与 _run_*_in_thread 状态回写
- _dispatch_* 协程对 adapter 的调用契约
- _spawn_open_page_thread 线程生命周期（成功等待浏览器关闭、异常不上抛）
- open_oa_page / open_invoice_page / open_stamp_page / open_conflict_check_page
"""

from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.oa_filing.services import script_executor_service as mod
from apps.oa_filing.services.exceptions import ScriptExecutionError
from apps.oa_filing.services.script_executor_service import ScriptExecutorService

# ──────────── 工具 ────────────


def _bridge(monkeypatch: pytest.MonkeyPatch, error: Exception | None = None) -> dict[str, Any]:
    """替换 run_coro_sync：消费并关闭协程（避免 never-awaited 告警），可选抛错。"""
    captured: dict[str, Any] = {"coros": []}

    def fake(coro: Any, **kwargs: Any) -> Any:
        captured["coros"].append(coro)
        coro.close()
        if error is not None:
            raise error
        return None

    monkeypatch.setattr(mod, "run_coro_sync", fake)
    return captured


# ──────────── _friendly_error_message ────────────


class TestFriendlyErrorMessage:
    def test_timeout_keywords(self):
        assert "VPN" in mod._friendly_error_message(RuntimeError("Read timeout"))
        assert "超时" in mod._friendly_error_message(RuntimeError("ConnectTimeout expired"))
        assert "VPN" in mod._friendly_error_message(RuntimeError("Operation timed out"))

    def test_dns_failure(self):
        msg = mod._friendly_error_message(RuntimeError("Name or service not known"))
        assert "域名" in msg
        msg2 = mod._friendly_error_message(RuntimeError("getaddrinfo failed for ims.jtn.com"))
        assert "域名" in msg2

    def test_connection_refused(self):
        msg = mod._friendly_error_message(RuntimeError("Connection refused by host"))
        assert "拒绝连接" in msg
        msg2 = mod._friendly_error_message(RuntimeError("ConnectionResetError(104, 'Connection reset"))
        assert "拒绝连接" in msg2

    def test_passthrough_other_errors(self):
        assert mod._friendly_error_message(ValueError("普通业务错误")) == "普通业务错误"


# ──────────── 权限校验 ────────────


class TestEnsureAccess:
    def test_ensure_contract_access_delegates(self):
        with patch("apps.contracts.services.contract.domain.access_policy.ContractAccessPolicy") as policy_cls:
            policy_cls.return_value.ensure_access = MagicMock()
            user = MagicMock()
            mod._ensure_contract_access(33, user)
        policy_cls.return_value.ensure_access.assert_called_once_with(contract_id=33, user=user, org_access=None)

    def test_ensure_case_access_delegates(self):
        with patch("apps.cases.services.case.case_access_policy.CaseAccessPolicy") as policy_cls:
            policy_cls.return_value.ensure_access = MagicMock()
            user = MagicMock()
            mod._ensure_case_access(44, user)
        policy_cls.return_value.ensure_access.assert_called_once_with(case_id=44, user=user, org_access=None)


# ──────────── session 查询（属主过滤） ────────────


class TestSessionOwnerCheck:
    def test_can_view_all_sessions_superuser(self):
        assert mod.ScriptExecutorService._can_view_all_sessions(SimpleNamespace(is_superuser=True, is_admin=False))

    def test_can_view_all_sessions_admin_flag(self):
        assert mod.ScriptExecutorService._can_view_all_sessions(SimpleNamespace(is_superuser=False, is_admin=True))

    def test_regular_user_cannot_view_all(self):
        assert not mod.ScriptExecutorService._can_view_all_sessions(SimpleNamespace(is_superuser=False, is_admin=False))

    def test_owner_check_regular_user_filters_by_user_id(self):
        svc = ScriptExecutorService()
        model = MagicMock()
        qs = MagicMock()
        model.objects.filter.return_value = qs
        owned_qs = MagicMock()
        qs.filter.return_value = owned_qs
        owned_qs.get.return_value = "session-row"
        user = SimpleNamespace(is_superuser=False, is_admin=False, id=77)

        result = svc._get_session_with_owner_check(model, 5, user)

        assert result == "session-row"
        model.objects.filter.assert_called_once_with(pk=5)
        qs.filter.assert_called_once_with(user_id=77)

    def test_owner_check_admin_skips_user_filter(self):
        svc = ScriptExecutorService()
        model = MagicMock()
        qs = MagicMock()
        model.objects.filter.return_value = qs
        qs.get.return_value = "session-row"
        user = SimpleNamespace(is_superuser=True, id=1)

        result = svc._get_session_with_owner_check(model, 5, user)

        assert result == "session-row"
        qs.filter.assert_not_called()

    def test_owner_check_none_user_skips_filter(self):
        svc = ScriptExecutorService()
        model = MagicMock()
        qs = MagicMock()
        model.objects.filter.return_value = qs
        qs.get.return_value = "session-row"

        assert svc._get_session_with_owner_check(model, 5, None) == "session-row"
        qs.filter.assert_not_called()

    @pytest.mark.parametrize(
        ("method_name", "model_name"),
        [
            ("get_session", "FilingSession"),
            ("get_stamp_session", "StampSession"),
            ("get_archive_session", "ArchiveSession"),
        ],
    )
    def test_get_session_helpers_delegate(self, method_name: str, model_name: str):
        svc = ScriptExecutorService()
        with patch(f"apps.oa_filing.models.{model_name}") as model:
            model.objects.filter.return_value.get.return_value = "row"
            # admin 豁免属主过滤；常规用户的过滤路径已在 owner_check 用例覆盖
            result = getattr(svc, method_name)(9, SimpleNamespace(is_superuser=True, id=1))
        assert result == "row"
        model.objects.filter.assert_called_once_with(pk=9)


# ──────────── 凭证查找 ────────────


class TestFindCredential:
    def test_filters_by_lawyer_and_site(self, monkeypatch: pytest.MonkeyPatch):
        svc = ScriptExecutorService()
        model = MagicMock()
        model.objects.filter.return_value.first.return_value = "credential-row"
        monkeypatch.setattr(mod, "django_apps", SimpleNamespace(get_model=MagicMock(return_value=model)))
        user = MagicMock()

        result = svc._find_credential(user, "金诚同达OA")

        assert result == "credential-row"
        model.objects.filter.assert_called_once_with(lawyer=user, site_name="金诚同达OA")
        model.objects.filter.return_value.first.assert_called_once_with()

    def test_missing_credential_returns_none(self, monkeypatch: pytest.MonkeyPatch):
        svc = ScriptExecutorService()
        model = MagicMock()
        model.objects.filter.return_value.first.return_value = None
        monkeypatch.setattr(mod, "django_apps", SimpleNamespace(get_model=MagicMock(return_value=model)))

        assert svc._find_credential(MagicMock(), "其他OA") is None


# ──────────── 立案 ────────────


class TestExecuteFiling:
    def test_execute_without_credential_raises(self, monkeypatch: pytest.MonkeyPatch):
        svc = ScriptExecutorService()
        monkeypatch.setattr(mod, "_ensure_contract_access", MagicMock())
        monkeypatch.setattr(mod, "_ensure_case_access", MagicMock())
        monkeypatch.setattr(mod.ScriptExecutorService, "_find_credential", staticmethod(lambda user, site: None))
        with pytest.raises(ScriptExecutionError, match="未找到匹配凭证"):
            svc.execute("金诚同达OA", contract_id=1, case_id=None, user=MagicMock())

    def test_execute_with_case_id_checks_case_access(self, monkeypatch: pytest.MonkeyPatch):
        svc = ScriptExecutorService()
        ensure_contract = MagicMock()
        ensure_case = MagicMock()
        monkeypatch.setattr(mod, "_ensure_contract_access", ensure_contract)
        monkeypatch.setattr(mod, "_ensure_case_access", ensure_case)
        monkeypatch.setattr(mod.ScriptExecutorService, "_find_credential", staticmethod(lambda user, site: None))
        user = MagicMock()
        with pytest.raises(ScriptExecutionError):
            svc.execute("金诚同达OA", contract_id=1, case_id=8, user=user)
        ensure_contract.assert_called_once_with(1, user)
        ensure_case.assert_called_once_with(8, user)


class TestRunInThread:
    def test_success_marks_completed(self, monkeypatch: pytest.MonkeyPatch):
        _bridge(monkeypatch)
        with patch("apps.oa_filing.models.FilingSession") as model:
            from apps.oa_filing.models import SessionStatus

            mod.ScriptExecutorService()._run_in_thread(6, "金诚同达OA", MagicMock(), 1, None)
            kwargs = model.objects.filter.return_value.update.call_args.kwargs
        assert kwargs["status"] == SessionStatus.COMPLETED

    def test_failure_marks_failed_with_friendly_message(self, monkeypatch: pytest.MonkeyPatch):
        _bridge(monkeypatch, error=RuntimeError("Connection timed out"))
        with patch("apps.oa_filing.models.FilingSession") as model:
            from apps.oa_filing.models import SessionStatus

            mod.ScriptExecutorService()._run_in_thread(6, "金诚同达OA", MagicMock(), 1, 2)
            kwargs = model.objects.filter.return_value.update.call_args.kwargs
        assert kwargs["status"] == SessionStatus.FAILED
        assert "VPN" in kwargs["error_message"]
        model.objects.filter.assert_called_with(pk=6)


class TestDispatchFiling:
    @pytest.mark.asyncio
    async def test_dispatch_creates_adapter_and_runs(self, monkeypatch: pytest.MonkeyPatch):
        adapter = MagicMock()
        adapter.execute_filing = AsyncMock()
        create = MagicMock(return_value=adapter)
        monkeypatch.setattr(mod, "create_adapter", create)
        credential = SimpleNamespace(account="acc", password="pwd")

        await ScriptExecutorService()._dispatch_filing("金诚同达OA", credential, 12, 34)

        create.assert_called_once_with("金诚同达OA", "acc", "pwd")
        adapter.execute_filing.assert_awaited_once_with(session=None, credential=credential, contract_id=12, case_id=34)


# ──────────── 盖章 ────────────


class TestExecuteStamp:
    def _run(self, monkeypatch: pytest.MonkeyPatch, lookup: Any, credential: Any) -> dict[str, Any]:
        monkeypatch.setattr(mod, "_ensure_contract_access", MagicMock())
        monkeypatch.setattr(mod.ScriptExecutorService, "_find_credential", staticmethod(lambda user, site: credential))
        submit = MagicMock()
        monkeypatch.setattr(mod, "_submit_session_job", submit)
        user = MagicMock()
        svc = ScriptExecutorService()
        with (
            patch("apps.oa_filing.services.stamp_lookup_service.StampLookupService") as lookup_svc,
            patch("apps.oa_filing.models.StampSession") as model,
        ):
            from apps.oa_filing.models import StampSessionStatus

            lookup_svc.lookup_by_file_path.return_value = lookup
            model.objects.create.return_value = SimpleNamespace(id=21, pk=21)
            model.objects.get.return_value = "stamp-session"
            result = svc.execute_stamp("/media/contracts/a.pdf", user)
            create_kwargs = model.objects.create.call_args.kwargs
            submit_args = submit.call_args.args
        assert result == "stamp-session"
        assert create_kwargs["contract_id"] == lookup.contract_id
        assert create_kwargs["oa_case_number"] == lookup.oa_case_number
        assert create_kwargs["file_path"] == "/media/contracts/a.pdf"
        assert create_kwargs["status"] == StampSessionStatus.IN_PROGRESS
        assert submit_args[0] is model
        assert submit_args[1] == 21
        assert submit_args[2] == StampSessionStatus.FAILED
        assert submit_args[3] == "盖章"
        assert submit_args[4] == svc._run_stamp_in_thread
        assert submit_args[5:] == (21, "金诚同达OA")
        return create_kwargs

    def test_execute_stamp_assembles_session(self, monkeypatch: pytest.MonkeyPatch):
        lookup = SimpleNamespace(contract_id=3, oa_case_number="OA-77")
        credential = SimpleNamespace(account="a", password="b")
        kwargs = self._run(monkeypatch, lookup, credential)
        assert kwargs["credential"] is credential


class TestRunStampInThread:
    def test_success_and_failure_paths(self, monkeypatch: pytest.MonkeyPatch):
        with patch("apps.oa_filing.models.StampSession") as model:
            from apps.oa_filing.models import StampSessionStatus

            _bridge(monkeypatch)
            ScriptExecutorService()._run_stamp_in_thread(31, "金诚同达OA")
            ok_kwargs = model.objects.filter.return_value.update.call_args.kwargs
            assert ok_kwargs["status"] == StampSessionStatus.COMPLETED

            _bridge(monkeypatch, error=RuntimeError("getaddrinfo failed"))
            ScriptExecutorService()._run_stamp_in_thread(31, "金诚同达OA")
            fail_kwargs = model.objects.filter.return_value.update.call_args.kwargs
            assert fail_kwargs["status"] == StampSessionStatus.FAILED
            assert "域名" in fail_kwargs["error_message"]


class TestDispatchStamp:
    @pytest.mark.asyncio
    async def test_dispatch_prefetches_session_and_runs(self, monkeypatch: pytest.MonkeyPatch):
        adapter = MagicMock()
        adapter.execute_stamp = AsyncMock()
        create = MagicMock(return_value=adapter)
        monkeypatch.setattr(mod, "create_adapter", create)
        session = SimpleNamespace(credential=SimpleNamespace(account="acc", password="pwd"), pk=5)
        with patch("apps.oa_filing.models.StampSession") as model:
            model.objects.select_related.return_value.aget = AsyncMock(return_value=session)

            await ScriptExecutorService()._dispatch_stamp(5, "金诚同达OA")

        model.objects.select_related.assert_called_once_with("credential")
        model.objects.select_related.return_value.aget.assert_awaited_once_with(pk=5)
        create.assert_called_once_with("金诚同达OA", "acc", "pwd")
        adapter.execute_stamp.assert_awaited_once_with(session)


# ──────────── 归档 ────────────


class TestExecuteArchive:
    def _patch_common(self, monkeypatch: pytest.MonkeyPatch, lookups: list[Any]):
        monkeypatch.setattr(mod, "_ensure_contract_access", MagicMock())
        monkeypatch.setattr(mod.ScriptExecutorService, "_find_credential", staticmethod(lambda user, site: "cred"))
        submit = MagicMock()
        monkeypatch.setattr(mod, "_submit_session_job", submit)
        lookup_svc = MagicMock()
        lookup_svc.lookup_by_file_path.side_effect = lookups
        return lookup_svc, submit

    def test_mixed_contracts_rejected(self, monkeypatch: pytest.MonkeyPatch):
        lookups = [
            SimpleNamespace(contract_id=1, oa_case_number="OA-1"),
            SimpleNamespace(contract_id=2, oa_case_number="OA-2"),
        ]
        lookup_svc, _ = self._patch_common(monkeypatch, lookups)
        with patch("apps.oa_filing.services.stamp_lookup_service.StampLookupService", lookup_svc):
            with pytest.raises(ScriptExecutionError, match="分属不同合同"):
                ScriptExecutorService().execute_archive(["/a.pdf", "/b.pdf"], MagicMock())

    def test_success_assembles_session(self, monkeypatch: pytest.MonkeyPatch):
        lookups = [
            SimpleNamespace(contract_id=7, oa_case_number="OA-7"),
            SimpleNamespace(contract_id=7, oa_case_number="OA-7"),
        ]
        lookup_svc, submit = self._patch_common(monkeypatch, lookups)
        user = MagicMock()
        with (
            patch("apps.oa_filing.services.stamp_lookup_service.StampLookupService", lookup_svc),
            patch("apps.oa_filing.models.ArchiveSession") as model,
        ):
            from apps.oa_filing.models import ArchiveSessionStatus

            model.objects.create.return_value = SimpleNamespace(id=41, pk=41)
            model.objects.get.return_value = "archive-session"
            result = ScriptExecutorService().execute_archive(["/a.pdf", "/b.pdf"], user)
            create_kwargs = model.objects.create.call_args.kwargs

        assert result == "archive-session"
        assert create_kwargs["contract_id"] == 7
        assert create_kwargs["oa_case_number"] == "OA-7"
        assert create_kwargs["file_paths"] == ["/a.pdf", "/b.pdf"]
        assert create_kwargs["status"] == ArchiveSessionStatus.IN_PROGRESS
        assert submit.call_args.args[1] == 41
        assert submit.call_args.args[3] == "归档"


class TestRunArchiveInThread:
    def test_success_and_failure_paths(self, monkeypatch: pytest.MonkeyPatch):
        with patch("apps.oa_filing.models.ArchiveSession") as model:
            from apps.oa_filing.models import ArchiveSessionStatus

            _bridge(monkeypatch)
            ScriptExecutorService()._run_archive_in_thread(51, "金诚同达OA")
            assert model.objects.filter.return_value.update.call_args.kwargs["status"] == ArchiveSessionStatus.COMPLETED

            _bridge(monkeypatch, error=RuntimeError("Connection refused"))
            ScriptExecutorService()._run_archive_in_thread(51, "金诚同达OA")
            fail_kwargs = model.objects.filter.return_value.update.call_args.kwargs
            assert fail_kwargs["status"] == ArchiveSessionStatus.FAILED
            assert "拒绝连接" in fail_kwargs["error_message"]


class TestDispatchArchive:
    @pytest.mark.asyncio
    async def test_dispatch_prefetches_session_and_runs(self, monkeypatch: pytest.MonkeyPatch):
        adapter = MagicMock()
        adapter.execute_archive = AsyncMock()
        create = MagicMock(return_value=adapter)
        monkeypatch.setattr(mod, "create_adapter", create)
        session = SimpleNamespace(credential=SimpleNamespace(account="a", password="b"), pk=9)
        with patch("apps.oa_filing.models.ArchiveSession") as model:
            model.objects.select_related.return_value.aget = AsyncMock(return_value=session)

            await ScriptExecutorService()._dispatch_archive(9, "金诚同达OA")

        model.objects.select_related.assert_called_once_with("credential")
        adapter.execute_archive.assert_awaited_once_with(session)


# ──────────── 半自动 open_page 线程 ────────────


class TestSpawnOpenPageThread:
    def _record_threads(self, monkeypatch: pytest.MonkeyPatch) -> list[threading.Thread]:
        created: list[threading.Thread] = []
        real_thread = threading.Thread

        class RecordingThread(real_thread):  # type: ignore[misc,valid-type]
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                super().__init__(*args, **kwargs)
                created.append(self)

        monkeypatch.setattr(mod.threading, "Thread", RecordingThread)
        return created

    def test_success_waits_browser_closed(self, monkeypatch: pytest.MonkeyPatch):
        created = self._record_threads(monkeypatch)
        adapter = MagicMock()
        adapter.open_invoice_page = AsyncMock()
        adapter.wait_open_browsers_closed = AsyncMock()
        monkeypatch.setattr(mod, "create_adapter", MagicMock(return_value=adapter))
        monkeypatch.setattr(mod, "run_coro_sync", lambda coro, **kw: asyncio.run(coro))
        credential = SimpleNamespace(account="a", password="b")

        ScriptExecutorService()._spawn_open_page_thread("open_invoice_page", "金诚同达OA", credential, "OA-9")

        assert created, "必须创建 daemon 线程"
        thread = created[0]
        assert thread.daemon is True
        assert "open_invoice_page" in thread.name
        thread.join(timeout=10)
        assert not thread.is_alive()
        adapter.open_invoice_page.assert_awaited_once_with(credential, "OA-9")
        adapter.wait_open_browsers_closed.assert_awaited_once()

    def test_adapter_failure_skips_wait_but_thread_exits(self, monkeypatch: pytest.MonkeyPatch):
        created = self._record_threads(monkeypatch)
        adapter = MagicMock()
        adapter.open_oa_page = AsyncMock(side_effect=RuntimeError("sso failed"))
        adapter.wait_open_browsers_closed = AsyncMock()
        monkeypatch.setattr(mod, "create_adapter", MagicMock(return_value=adapter))
        monkeypatch.setattr(mod, "run_coro_sync", lambda coro, **kw: asyncio.run(coro))

        ScriptExecutorService()._spawn_open_page_thread(
            "open_oa_page", "金诚同达OA", SimpleNamespace(account="a", password="b"), "OA-1", "小结", []
        )

        created[0].join(timeout=10)
        assert not created[0].is_alive()
        adapter.wait_open_browsers_closed.assert_not_awaited()


# ──────────── open_* 页面入口 ────────────


def _patch_open_common(monkeypatch: pytest.MonkeyPatch, credential: Any) -> MagicMock:
    monkeypatch.setattr(mod, "_ensure_contract_access", MagicMock())
    monkeypatch.setattr(mod, "_ensure_case_access", MagicMock())
    monkeypatch.setattr(mod.ScriptExecutorService, "_find_credential", staticmethod(lambda user, site: credential))
    spawn = MagicMock()
    monkeypatch.setattr(mod.ScriptExecutorService, "_spawn_open_page_thread", spawn)
    return spawn


class TestOpenOaPage:
    def test_missing_credential_raises(self, monkeypatch: pytest.MonkeyPatch):
        _patch_open_common(monkeypatch, None)
        with pytest.raises(RuntimeError, match="未找到匹配凭证"):
            ScriptExecutorService().open_oa_page(1, MagicMock())

    def test_no_final_archive_file_omits_upload(self, monkeypatch: pytest.MonkeyPatch):
        spawn = _patch_open_common(monkeypatch, "cred")
        contract = SimpleNamespace(law_firm_oa_case_number="OA-3")
        with (
            patch("apps.contracts.models.Contract") as contract_model,
            patch("apps.contracts.services.archive.generation.service.ArchiveGenerationService") as gen_svc,
        ):
            contract_model.objects.filter.return_value.first.return_value = contract
            gen_svc.return_value.resolve_latest_final_archive_file.return_value = None

            ScriptExecutorService().open_oa_page(9, MagicMock(), description="详见卷宗")

        gen_svc.return_value.resolve_latest_final_archive_file.assert_called_once_with(contract)
        spawn.assert_called_once_with("open_oa_page", "金诚同达OA", "cred", "OA-3", "详见卷宗", [])

    def test_final_archive_file_attached(self, monkeypatch: pytest.MonkeyPatch):
        spawn = _patch_open_common(monkeypatch, "cred")
        contract = SimpleNamespace(law_firm_oa_case_number="OA-4")
        with (
            patch("apps.contracts.models.Contract") as contract_model,
            patch("apps.contracts.services.archive.generation.service.ArchiveGenerationService") as gen_svc,
        ):
            contract_model.objects.filter.return_value.first.return_value = contract
            gen_svc.return_value.resolve_latest_final_archive_file.return_value = "/media/5-Final.zip"

            ScriptExecutorService().open_oa_page(9, MagicMock())

        spawn.assert_called_once_with("open_oa_page", "金诚同达OA", "cred", "OA-4", "详见卷宗", ["/media/5-Final.zip"])

    def test_missing_contract_uses_empty_number(self, monkeypatch: pytest.MonkeyPatch):
        spawn = _patch_open_common(monkeypatch, "cred")
        with patch("apps.contracts.models.Contract") as contract_model:
            contract_model.objects.filter.return_value.first.return_value = None

            ScriptExecutorService().open_oa_page(9, MagicMock())

        spawn.assert_called_once_with("open_oa_page", "金诚同达OA", "cred", "", "详见卷宗", [])


class TestOpenInvoicePage:
    def test_missing_credential_raises(self, monkeypatch: pytest.MonkeyPatch):
        _patch_open_common(monkeypatch, None)
        with pytest.raises(RuntimeError, match="未找到匹配凭证"):
            ScriptExecutorService().open_invoice_page(1, MagicMock())

    def test_uses_contract_oa_number(self, monkeypatch: pytest.MonkeyPatch):
        spawn = _patch_open_common(monkeypatch, "cred")
        with patch("apps.contracts.models.Contract") as contract_model:
            contract_model.objects.filter.return_value.first.return_value = SimpleNamespace(
                law_firm_oa_case_number="OA-8"
            )
            ScriptExecutorService().open_invoice_page(3, MagicMock())
        spawn.assert_called_once_with("open_invoice_page", "金诚同达OA", "cred", "OA-8")


class TestOpenStampPage:
    def test_missing_credential_raises(self, monkeypatch: pytest.MonkeyPatch):
        _patch_open_common(monkeypatch, None)
        with pytest.raises(RuntimeError, match="未找到匹配凭证"):
            ScriptExecutorService().open_stamp_page(1, MagicMock())

    def test_case_with_contract_uses_oa_number(self, monkeypatch: pytest.MonkeyPatch):
        spawn = _patch_open_common(monkeypatch, "cred")
        case = SimpleNamespace(contract=SimpleNamespace(law_firm_oa_case_number="OA-6"))
        with patch("apps.cases.models.Case") as case_model:
            case_model.objects.filter.return_value.first.return_value = case
            ScriptExecutorService().open_stamp_page(15, MagicMock())
        spawn.assert_called_once_with("open_stamp_page", "金诚同达OA", "cred", "OA-6")

    def test_case_without_contract_uses_empty_number(self, monkeypatch: pytest.MonkeyPatch):
        spawn = _patch_open_common(monkeypatch, "cred")
        with patch("apps.cases.models.Case") as case_model:
            case_model.objects.filter.return_value.first.return_value = SimpleNamespace(contract=None)
            ScriptExecutorService().open_stamp_page(15, MagicMock())
        spawn.assert_called_once_with("open_stamp_page", "金诚同达OA", "cred", "")


class TestOpenConflictCheckPage:
    def test_missing_credential_raises(self, monkeypatch: pytest.MonkeyPatch):
        _patch_open_common(monkeypatch, None)
        with pytest.raises(RuntimeError, match="未找到匹配凭证"):
            ScriptExecutorService().open_conflict_check_page("某公司", MagicMock())

    def test_spawns_with_keyword(self, monkeypatch: pytest.MonkeyPatch):
        spawn = _patch_open_common(monkeypatch, "cred")
        ScriptExecutorService().open_conflict_check_page("当事人甲", MagicMock())
        spawn.assert_called_once_with("open_conflict_check_page", "金诚同达OA", "cred", "当事人甲")
