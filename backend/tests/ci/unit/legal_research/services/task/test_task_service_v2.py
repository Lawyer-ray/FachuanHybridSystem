"""LegalResearchTaskService and related service tests."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import NotFoundError, PermissionDenied, ValidationException


def _make_credential(*, site_name: str = "wkxx", url: str = "", lawyer=None, lawyer_firm_id: int = 1):
    cred = MagicMock()
    cred.id = 1
    cred.site_name = site_name
    cred.url = url
    cred.lawyer = lawyer or _make_lawyer(firm_id=lawyer_firm_id)
    return cred


def _make_lawyer(*, firm_id: int = 1, user_id: int = 10, is_superuser: bool = False):
    lawyer = MagicMock()
    lawyer.id = user_id
    lawyer.law_firm_id = firm_id
    lawyer.is_superuser = is_superuser
    return lawyer


def _make_user(*, user_id: int = 10, firm_id: int = 1, is_superuser: bool = False):
    user = MagicMock()
    user.id = user_id
    user.law_firm_id = firm_id
    user.is_superuser = is_superuser
    return user


def _make_payload(*, keyword: str = "合同纠纷", credential_id: int = 1, case_summary: str = "测试", **kwargs):
    payload = SimpleNamespace(
        keyword=keyword,
        credential_id=credential_id,
        case_summary=case_summary,
        search_url=kwargs.get("search_url", ""),
        search_mode=kwargs.get("search_mode"),
        target_count=kwargs.get("target_count", 5),
        max_candidates=kwargs.get("max_candidates", 100),
        min_similarity_score=kwargs.get("min_similarity_score", 0.6),
        llm_model=kwargs.get("llm_model", ""),
        llm_scoring_concurrency=kwargs.get("llm_scoring_concurrency", 5),
    )
    return payload


# ── _is_weike_credential ──────────────────────────────────────────────────


class TestIsWeikeCredential:
    def test_wkxx_in_site_name(self) -> None:
        from apps.legal_research.services.task.service import LegalResearchTaskService

        cred = _make_credential(site_name="wkxx")
        assert LegalResearchTaskService._is_weike_credential(cred) is True

    def test_wk_exact_site_name(self) -> None:
        from apps.legal_research.services.task.service import LegalResearchTaskService

        cred = _make_credential(site_name="wk")
        assert LegalResearchTaskService._is_weike_credential(cred) is True

    def test_weike_in_site_name(self) -> None:
        from apps.legal_research.services.task.service import LegalResearchTaskService

        cred = _make_credential(site_name="WeikeSearch")
        assert LegalResearchTaskService._is_weike_credential(cred) is True

    def test_wkinfo_in_site_name(self) -> None:
        from apps.legal_research.services.task.service import LegalResearchTaskService

        cred = _make_credential(site_name="wkinfo")
        assert LegalResearchTaskService._is_weike_credential(cred) is True

    def test_wkinfo_url_keyword(self) -> None:
        from apps.legal_research.services.task.service import LegalResearchTaskService

        cred = _make_credential(site_name="other", url="https://wkinfo.com.cn/search")
        assert LegalResearchTaskService._is_weike_credential(cred) is True

    def test_not_weike(self) -> None:
        from apps.legal_research.services.task.service import LegalResearchTaskService

        cred = _make_credential(site_name="google", url="https://google.com")
        assert LegalResearchTaskService._is_weike_credential(cred) is False

    def test_empty_site_name_and_url(self) -> None:
        from apps.legal_research.services.task.service import LegalResearchTaskService

        cred = _make_credential(site_name="", url="")
        assert LegalResearchTaskService._is_weike_credential(cred) is False

    def test_case_insensitive(self) -> None:
        from apps.legal_research.services.task.service import LegalResearchTaskService

        cred = _make_credential(site_name="WKXX")
        assert LegalResearchTaskService._is_weike_credential(cred) is True


# ── _check_permission ─────────────────────────────────────────────────────


class TestCheckPermission:
    def test_none_user_raises(self) -> None:
        from apps.legal_research.services.task.service import LegalResearchTaskService

        task = MagicMock()
        with pytest.raises(PermissionDenied):
            LegalResearchTaskService._check_permission(task=task, user=None)

    def test_superuser_allowed(self) -> None:
        from apps.legal_research.services.task.service import LegalResearchTaskService

        task = MagicMock()
        task.created_by_id = 99
        task.credential.lawyer.law_firm_id = 99
        user = _make_user(is_superuser=True)
        LegalResearchTaskService._check_permission(task=task, user=user)

    def test_creator_allowed(self) -> None:
        from apps.legal_research.services.task.service import LegalResearchTaskService

        task = MagicMock()
        task.created_by_id = 10
        task.credential.lawyer.law_firm_id = 99
        user = _make_user(user_id=10, firm_id=1)
        LegalResearchTaskService._check_permission(task=task, user=user)

    def test_same_firm_allowed(self) -> None:
        from apps.legal_research.services.task.service import LegalResearchTaskService

        task = MagicMock()
        task.created_by_id = 99
        task.credential.lawyer.law_firm_id = 5
        user = _make_user(user_id=10, firm_id=5)
        LegalResearchTaskService._check_permission(task=task, user=user)

    def test_different_firm_denied(self) -> None:
        from apps.legal_research.services.task.service import LegalResearchTaskService

        task = MagicMock()
        task.created_by_id = 99
        task.credential.lawyer.law_firm_id = 5
        user = _make_user(user_id=10, firm_id=1)
        with pytest.raises(PermissionDenied):
            LegalResearchTaskService._check_permission(task=task, user=user)


# ── create_task ────────────────────────────────────────────────────────────


class TestCreateTask:
    @patch("apps.legal_research.services.task.service.LLMConfig")
    @patch("apps.legal_research.services.task.service.normalize_keyword_query", return_value="合同纠纷")
    @patch("apps.legal_research.services.task.service._get_account_credential_model")
    def test_credential_not_found(self, mock_get_model, mock_norm, mock_llm) -> None:
        from apps.legal_research.services.task.service import LegalResearchTaskService

        mock_model = MagicMock()
        mock_model.objects.select_related.return_value.filter.return_value.first.return_value = None
        mock_get_model.return_value = mock_model

        svc = LegalResearchTaskService()
        with pytest.raises(NotFoundError, match="账号凭证不存在"):
            svc.create_task(payload=_make_payload(), user=_make_user())

    @patch("apps.legal_research.services.task.service.LLMConfig")
    @patch("apps.legal_research.services.task.service.normalize_keyword_query", return_value="合同纠纷")
    @patch("apps.legal_research.services.task.service._get_account_credential_model")
    def test_none_user_raises(self, mock_get_model, mock_norm, mock_llm) -> None:
        from apps.legal_research.services.task.service import LegalResearchTaskService

        mock_model = MagicMock()
        mock_model.objects.select_related.return_value.filter.return_value.first.return_value = _make_credential()
        mock_get_model.return_value = mock_model

        svc = LegalResearchTaskService()
        with pytest.raises(PermissionDenied):
            svc.create_task(payload=_make_payload(), user=None)

    @patch("apps.legal_research.services.task.service.LLMConfig")
    @patch("apps.legal_research.services.task.service.normalize_keyword_query", return_value="合同纠纷")
    @patch("apps.legal_research.services.task.service._get_account_credential_model")
    def test_non_weike_credential_raises(self, mock_get_model, mock_norm, mock_llm) -> None:
        from apps.legal_research.services.task.service import LegalResearchTaskService

        mock_model = MagicMock()
        cred = _make_credential(site_name="google", url="https://google.com")
        mock_model.objects.select_related.return_value.filter.return_value.first.return_value = cred
        mock_get_model.return_value = mock_model

        svc = LegalResearchTaskService()
        with pytest.raises(ValidationException, match="仅支持wkxx"):
            svc.create_task(payload=_make_payload(), user=_make_user(firm_id=1))

    @patch("apps.legal_research.services.task.service.LLMConfig")
    @patch("apps.legal_research.services.task.service.normalize_keyword_query", return_value="")
    @patch("apps.legal_research.services.task.service._get_account_credential_model")
    def test_empty_keyword_and_no_url_raises(self, mock_get_model, mock_norm, mock_llm) -> None:
        from apps.legal_research.services.task.service import LegalResearchTaskService

        mock_model = MagicMock()
        cred = _make_credential(site_name="wkxx", lawyer=_make_lawyer(firm_id=1))
        mock_model.objects.select_related.return_value.filter.return_value.first.return_value = cred
        mock_get_model.return_value = mock_model

        svc = LegalResearchTaskService()
        payload = _make_payload(keyword="", search_url="")
        with pytest.raises(ValidationException, match="至少输入一个有效检索关键词"):
            svc.create_task(payload=payload, user=_make_user(firm_id=1))


# ── dispatch_task ──────────────────────────────────────────────────────────


class TestDispatchTask:
    def test_precheck_failure_marks_task(self) -> None:
        from apps.legal_research.services.task.service import LegalResearchTaskService

        svc = LegalResearchTaskService()
        task = MagicMock()
        task.id = 1
        task.llm_model = "test-model"

        def precheck_fail(**kwargs):
            raise ValidationException("模型不可用")

        result = svc.dispatch_task(task=task, precheck=precheck_fail)
        assert result is False
        assert task.status == "failed"

    @patch("apps.legal_research.services.task.service.LLMConfig")
    @patch("apps.legal_research.services.task.service.ServiceLocator")
    def test_submit_success(self, mock_locator, mock_llm) -> None:
        from apps.legal_research.services.task.service import LegalResearchTaskService

        svc = LegalResearchTaskService()
        task = MagicMock()
        task.id = 1
        task.llm_model = "test-model"

        mock_submit = MagicMock()
        mock_submit.return_value.submit.return_value = "q-123"
        mock_locator.get_task_submission_service.return_value = mock_submit.return_value

        def precheck_ok(**kwargs):
            pass

        result = svc.dispatch_task(task=task, precheck=precheck_ok)
        assert result is True
        assert task.q_task_id == "q-123"

    @patch("apps.legal_research.services.task.service.LLMConfig")
    @patch("apps.legal_research.services.task.service.ServiceLocator")
    def test_submit_failure_raises_on_flag(self, mock_locator, mock_llm) -> None:
        from apps.legal_research.services.task.service import LegalResearchTaskService

        svc = LegalResearchTaskService()
        task = MagicMock()
        task.id = 1
        task.llm_model = "test-model"

        mock_submit = MagicMock()
        mock_submit.return_value.submit.side_effect = RuntimeError("queue down")
        mock_locator.get_task_submission_service.return_value = mock_submit.return_value

        def precheck_ok(**kwargs):
            pass

        with pytest.raises(RuntimeError, match="queue down"):
            svc.dispatch_task(task=task, precheck=precheck_ok, raise_on_submit_error=True)


# ── reset_task_for_dispatch ────────────────────────────────────────────────


class TestResetTask:
    @patch("apps.legal_research.services.task.service.LLMConfig")
    def test_resets_fields(self, mock_llm) -> None:
        from apps.legal_research.services.task.service import LegalResearchTaskService

        mock_llm.get_default_backend.return_value = "openai_compatible"
        mock_llm.get_default_model.return_value = "default-model"

        svc = LegalResearchTaskService()
        task = MagicMock()
        task.llm_model = "old-model"

        svc.reset_task_for_dispatch(task=task, pending_message="test msg")
        assert task.status == "pending"
        assert task.progress == 0
        assert task.error == ""
        task.save.assert_called_once()


# ── get_task / list_results / get_result ────────────────────────────────────


class TestGetTaskAndResults:
    @patch("apps.legal_research.services.task.service.sync_failed_queue_state")
    @patch("apps.legal_research.services.task.service.LegalResearchTask")
    def test_task_not_found(self, mock_task_model, mock_sync) -> None:
        from apps.legal_research.services.task.service import LegalResearchTaskService

        mock_task_model.objects.select_related.return_value.filter.return_value.first.return_value = None
        svc = LegalResearchTaskService()
        with pytest.raises(NotFoundError, match="任务不存在"):
            svc.get_task(task_id=1, user=_make_user())

    @patch("apps.legal_research.services.task.service.sync_failed_queue_state")
    @patch("apps.legal_research.services.task.service.LegalResearchTask")
    def test_get_result_not_found(self, mock_task_model, mock_sync) -> None:
        from apps.legal_research.services.task.service import LegalResearchTaskService

        task = MagicMock()
        task.results.filter.return_value.first.return_value = None
        mock_task_model.objects.select_related.return_value.filter.return_value.first.return_value = task

        svc = LegalResearchTaskService()
        with pytest.raises(NotFoundError, match="检索结果不存在"):
            svc.get_result(task_id=1, result_id=99, user=_make_user(is_superuser=True))


# ── ensure_task_ready_for_download ─────────────────────────────────────────


class TestEnsureTaskReadyForDownload:
    @patch("apps.legal_research.services.task.service.sync_failed_queue_state")
    @patch("apps.legal_research.services.task.service.LegalResearchTask")
    def test_pending_task_raises(self, mock_task_model, mock_sync) -> None:
        from apps.legal_research.models import LegalResearchTaskStatus
        from apps.legal_research.services.task.service import LegalResearchTaskService

        task = MagicMock()
        task.status = LegalResearchTaskStatus.PENDING
        mock_task_model.objects.select_related.return_value.filter.return_value.first.return_value = task

        svc = LegalResearchTaskService()
        with pytest.raises(ValidationException, match="尚未生成可下载结果"):
            svc.ensure_task_ready_for_download(task_id=1, user=_make_user(is_superuser=True))
