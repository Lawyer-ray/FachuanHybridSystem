"""LegalResearchTask 数据源（source）与 credential 可空 行为测试。

覆盖 YU2 配置 lane 的三个契约：
- `source` 有封闭取值（weike / yuandian），默认仍是 weike；
- 元典任务的 credential 允许为空（元典 Key 是律所级的，存在 SystemConfig）；
- Admin 新增表单里 credential 是否必填由 source 决定，且「只有一个威科账号」时
  不会误报必填（该分支下字段被 get_fields() 移出表单，由 save_model 兜底填默认账号）。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.core.exceptions import PermissionDenied
from apps.legal_research.admin.task_admin import LegalResearchTaskAdmin
from apps.legal_research.models import CaseDownloadTask, LegalResearchTask
from apps.legal_research.models.task import LegalResearchTaskSource
from apps.legal_research.services.task import executor as executor_module
from apps.legal_research.services.task.executor import LegalResearchExecutor
from apps.legal_research.services.task.service import _check_permission
from apps.organization.models.credential import AccountCredential
from apps.organization.models.law_firm import LawFirm
from apps.testing.factories import LawyerFactory

User = get_user_model()

#: 新增任务表单的最小合法数据集（必填项）。
_ADD_FORM_DATA = {
    "keyword": "逾期利息",
    "case_summary": "借款合同纠纷，主张逾期利息。",
    "target_count": 3,
    "max_candidates": 100,
    "min_similarity_score": 0.9,
    "llm_scoring_concurrency": 5,
}


def _make_admin() -> LegalResearchTaskAdmin:
    return LegalResearchTaskAdmin(LegalResearchTask, AdminSite())


def _make_request():
    request = RequestFactory().post("/admin/legal_research/legalresearchtask/add/")
    request.user = User(is_superuser=True, is_staff=True)
    return request


def _make_weike_credential(account: str, lawyer=None) -> AccountCredential:
    return AccountCredential.objects.create(
        lawyer=lawyer or LawyerFactory(),
        site_name="wkxx",
        account=account,
        password="test_password",  # pragma: allowlist secret
    )


def _build_add_form(admin: LegalResearchTaskAdmin, **overrides):
    form_class = admin.get_form(_make_request(), obj=None)
    data = {**_ADD_FORM_DATA, **overrides}
    return form_class(data=data)


@pytest.mark.django_db
class TestYuandianSystemConfigDefaults:
    """元典只有 API Key 进 SystemConfig（无新表），且 secret 默认值绝不预置真实 Key。

    平台地址 / MCP Server 清单 / 每 key 并发上限是**代码常量**
    （``apps.core.services.yuandian_settings``）：它们不随部署变，落库只会多出一个
    「没点过初始化就是空」的失败面。所以这里只允许出现 API Key 一条。
    """

    def test_only_api_keys_is_seeded(self):
        from apps.core.admin._system_config_data import get_default_configs

        configs = {item["key"]: item for item in get_default_configs()}
        yuandian_keys = sorted(key for key in configs if key.startswith("YUANDIAN_"))
        assert yuandian_keys == ["YUANDIAN_API_KEYS"], "元典只该有 API Key 一个配置项"

        assert configs["YUANDIAN_API_KEYS"]["category"] == "enterprise_data"
        assert configs["YUANDIAN_API_KEYS"]["is_secret"] is True
        assert configs["YUANDIAN_API_KEYS"]["value"] == ""

    def test_api_keys_registered_as_multi_key(self):
        from apps.core.admin.forms.system_config_admin_form import _MULTI_KEY_CONFIGS

        assert "YUANDIAN_API_KEYS" in _MULTI_KEY_CONFIGS


@pytest.mark.django_db
class TestLegalResearchTaskSource:
    """source 的取值集合与默认值"""

    def test_source_choices(self):
        assert dict(LegalResearchTaskSource.choices) == {"weike": "威科先行", "yuandian": "元典"}

    def test_source_default_is_weike(self):
        task = LegalResearchTask.objects.create(keyword="逾期利息", case_summary="借款合同纠纷")
        assert task.source == "weike"
        assert task.get_source_display() == "威科先行"

    def test_weike_task_keeps_credential(self):
        credential = _make_weike_credential("weike_account")
        task = LegalResearchTask.objects.create(
            credential=credential,
            source=LegalResearchTaskSource.WEIKE,
            keyword="逾期利息",
            case_summary="借款合同纠纷",
        )
        task.refresh_from_db()
        assert task.credential_id == credential.id

    def test_yuandian_task_credential_nullable(self):
        task = LegalResearchTask.objects.create(
            source=LegalResearchTaskSource.YUANDIAN,
            keyword="逾期利息",
            case_summary="借款合同纠纷",
        )
        task.refresh_from_db()
        assert task.credential is None
        assert task.source == "yuandian"
        assert task.get_source_display() == "元典"

    def test_case_download_credential_still_required(self):
        """按案号批量下载 PDF 是威科专属功能，credential 保持必填（不被本次改动放宽）。"""
        field = CaseDownloadTask._meta.get_field("credential")
        assert field.null is False
        assert field.blank is False


@pytest.mark.django_db
class TestTaskAdminCredentialBySource:
    """Admin 新增表单：credential 是否必填由 source 决定"""

    def test_source_and_credential_in_add_fields(self):
        _make_weike_credential("wkxx_1")
        _make_weike_credential("wkxx_2")
        admin = _make_admin()
        fields = admin.get_fields(_make_request(), obj=None)
        assert "source" in fields
        assert "credential" in fields

    def test_credential_field_not_required(self):
        _make_weike_credential("wkxx_1")
        _make_weike_credential("wkxx_2")
        admin = _make_admin()
        form_class = admin.get_form(_make_request(), obj=None)
        assert form_class.base_fields["credential"].required is False

    def test_credential_help_text_mentions_yuandian(self):
        _make_weike_credential("wkxx_1")
        _make_weike_credential("wkxx_2")
        admin = _make_admin()
        form_class = admin.get_form(_make_request(), obj=None)
        assert "元典" in form_class.base_fields["credential"].help_text

    def test_weike_without_credential_rejected(self):
        _make_weike_credential("wkxx_1")
        _make_weike_credential("wkxx_2")
        admin = _make_admin()
        form = _build_add_form(admin, source=LegalResearchTaskSource.WEIKE.value)
        assert form.is_valid() is False
        assert "威科先行需要选择站点账号" in form.errors["credential"]

    def test_weike_with_credential_accepted(self):
        _make_weike_credential("wkxx_1")
        credential = _make_weike_credential("wkxx_2")
        admin = _make_admin()
        form = _build_add_form(
            admin, source=LegalResearchTaskSource.WEIKE.value, credential=str(credential.id)
        )
        assert form.is_valid() is True, form.errors
        assert form.cleaned_data["credential"] == credential

    def test_yuandian_without_credential_accepted(self):
        _make_weike_credential("wkxx_1")
        _make_weike_credential("wkxx_2")
        admin = _make_admin()
        form = _build_add_form(admin, source=LegalResearchTaskSource.YUANDIAN.value)
        assert form.is_valid() is True, form.errors
        assert form.cleaned_data["credential"] is None

    def test_no_weike_credential_at_all_still_allows_yuandian(self):
        """库里连一个威科账号都没有时，元典任务仍应能建（Key 在系统配置里）。"""
        admin = _make_admin()
        form = _build_add_form(admin, source=LegalResearchTaskSource.YUANDIAN.value)
        assert form.is_valid() is True, form.errors
        assert form.cleaned_data["credential"] is None

    def test_single_weike_credential_hidden_field_does_not_block_weike(self):
        """只有一个威科账号时 credential 被移出表单（HIDDEN 优化），不能因此误报必填。"""
        _make_weike_credential("only_weike")
        admin = _make_admin()
        form = _build_add_form(admin, source=LegalResearchTaskSource.WEIKE.value)
        assert "credential" not in form.fields
        assert form.is_valid() is True, form.errors


@pytest.mark.django_db
class TestCheckPermissionWithNullCredential:
    """credential 为空的元典任务：权限判定不得抛 AttributeError（原先会 500）。"""

    def test_same_firm_lawyer_denied_without_crash(self):
        firm = LawFirm.objects.create(name="元典测试律所甲")
        creator = LawyerFactory(law_firm=firm)
        requester = LawyerFactory(law_firm=firm)
        task = LegalResearchTask.objects.create(
            created_by=creator,
            source=LegalResearchTaskSource.YUANDIAN,
            keyword="逾期利息",
            case_summary="借款合同纠纷",
        )
        assert task.credential is None
        with pytest.raises(PermissionDenied):
            _check_permission(task=task, user=requester)

    def test_same_firm_lawyer_still_allowed_by_credential_owner(self):
        """本次只加判空，不改变原来的「凭证归属同所即可见」规则。"""
        firm = LawFirm.objects.create(name="元典测试律所乙")
        creator = LawyerFactory(law_firm=firm)
        requester = LawyerFactory(law_firm=firm)
        task = LegalResearchTask.objects.create(
            created_by=creator,
            credential=_make_weike_credential("wkxx_firm", lawyer=creator),
            keyword="逾期利息",
            case_summary="借款合同纠纷",
        )
        _check_permission(task=task, user=requester)


class _StopAfterOpenSession(Exception):
    """哨兵异常：断言完 open_session 立即中断 run()，避免继续走检索 / LLM。"""


@pytest.mark.django_db
class TestExecutorOpenSessionWithNullCredential:
    """credential 为空的元典任务：open_session 收到三个空值，不 AttributeError。"""

    def test_yuandian_task_passes_empty_credentials(self):
        task = LegalResearchTask.objects.create(
            source=LegalResearchTaskSource.YUANDIAN,
            keyword="逾期利息",
            case_summary="借款合同纠纷",
        )
        fake_client = MagicMock()
        fake_client.open_session.side_effect = _StopAfterOpenSession("stop-after-open-session")
        with (
            patch.object(executor_module, "_acquire_task", return_value=(task, None)),
            patch.object(executor_module, "get_case_source_client", return_value=fake_client),
        ):
            result = LegalResearchExecutor().run(task_id=str(task.id))

        fake_client.open_session.assert_called_once_with(username="", password="", login_url=None)
        assert result["status"] == "failed"
        assert result["error"] == "stop-after-open-session"
