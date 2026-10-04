"""Contract Review Task Admin 测试 - 覆盖 ReviewTaskAdmin"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.contract_review.admin.review_task_admin import ReviewTaskAdmin
from apps.contract_review.models import ReviewTask, TaskStatus

User = get_user_model()


def _make_admin():
    return ReviewTaskAdmin(ReviewTask, AdminSite())


def _make_request(method="GET", path="/admin/"):
    factory = RequestFactory()
    if method == "GET":
        request = factory.get(path)
    else:
        request = factory.post(path)
    request.user = User(is_superuser=True, is_staff=True)
    return request


@pytest.mark.django_db
class TestReviewTaskAdminAttributes:
    """验证 Admin 配置属性"""

    def test_list_display(self):
        admin = _make_admin()
        assert "contract_title" in admin.list_display
        assert "user" in admin.list_display
        assert "status" in admin.list_display
        assert "current_step_display" in admin.list_display
        assert "created_at" in admin.list_display

    def test_list_filter(self):
        admin = _make_admin()
        assert "status" in admin.list_filter
        assert "represented_party" in admin.list_filter

    def test_search_fields(self):
        admin = _make_admin()
        assert "contract_title" in admin.search_fields
        assert "party_a" in admin.search_fields
        assert "party_b" in admin.search_fields

    def test_readonly_fields(self):
        admin = _make_admin()
        assert "id" in admin.readonly_fields
        assert "original_file_link" in admin.readonly_fields
        assert "output_file_link" in admin.readonly_fields
        assert "error_message" in admin.readonly_fields
        assert "current_step" in admin.readonly_fields
        assert "review_report_html" in admin.readonly_fields

    def test_ordering(self):
        admin = _make_admin()
        assert "-created_at" in admin.ordering

    def test_actions(self):
        admin = _make_admin()
        assert "retry_selected_tasks" in admin.actions
        assert "delete_selected_with_files" in admin.actions
        assert "normalize_format" in admin.actions

    def test_change_form_template(self):
        admin = _make_admin()
        assert "change_form" in admin.change_form_template


@pytest.mark.django_db
class TestReviewTaskAdminDisplayMethods:
    """测试 display 方法"""

    def test_current_step_display_completed(self):
        admin = _make_admin()
        obj = MagicMock()
        obj.status = "completed"
        result = admin.current_step_display(obj)
        assert "已完成" in result

    def test_current_step_display_failed(self):
        admin = _make_admin()
        obj = MagicMock()
        obj.status = "failed"
        result = admin.current_step_display(obj)
        assert "失败" in result

    def test_current_step_display_with_step(self):
        admin = _make_admin()
        obj = MagicMock()
        obj.status = "processing"
        obj.current_step = "contract_review"
        obj.get_current_step_display.return_value = "审查合同"
        result = admin.current_step_display(obj)
        assert "审查合同" in result

    def test_current_step_display_no_step(self):
        admin = _make_admin()
        obj = MagicMock()
        obj.status = "pending"
        obj.current_step = None
        result = admin.current_step_display(obj)
        assert result == "—"

    def test_selected_steps_display_empty(self):
        admin = _make_admin()
        obj = MagicMock()
        obj.selected_steps = []
        result = admin.selected_steps_display(obj)
        assert result == "全部"

    def test_selected_steps_display_with_steps(self):
        admin = _make_admin()
        obj = MagicMock()
        obj.selected_steps = ["typo_check", "contract_review"]
        result = admin.selected_steps_display(obj)
        assert "错别字校对" in result
        assert "审查合同" in result

    def test_selected_steps_display_unknown_step(self):
        admin = _make_admin()
        obj = MagicMock()
        obj.selected_steps = ["unknown_step"]
        result = admin.selected_steps_display(obj)
        assert "unknown_step" in result

    def test_original_file_link_no_file(self):
        admin = _make_admin()
        obj = MagicMock()
        obj.original_file = ""
        result = admin.original_file_link(obj)
        assert result == "—"

    def test_original_file_link_with_file(self):
        admin = _make_admin()
        obj = MagicMock()
        obj.pk = uuid4()
        obj.original_file = "/some/path/file.docx"
        result = str(admin.original_file_link(obj))
        assert "file.docx" in result

    def test_output_file_link_no_file(self):
        admin = _make_admin()
        obj = MagicMock()
        obj.output_file = ""
        result = admin.output_file_link(obj)
        assert result == "—"

    def test_output_file_link_with_file(self):
        admin = _make_admin()
        obj = MagicMock()
        obj.pk = uuid4()
        obj.output_file = "/some/path/output.docx"
        result = str(admin.output_file_link(obj))
        assert "output.docx" in result

    def test_review_report_html_no_report(self):
        admin = _make_admin()
        obj = MagicMock()
        obj.review_report = ""
        result = admin.review_report_html(obj)
        assert result == "—"

    def test_review_report_html_with_report(self):
        admin = _make_admin()
        obj = MagicMock()
        obj.pk = uuid4()
        obj.review_report = "## Report content"
        result = str(admin.review_report_html(obj))
        assert "评估报告" in result


@pytest.mark.django_db
class TestReviewTaskAdminGetReadonlyFields:
    """测试 get_readonly_fields"""

    def test_get_readonly_fields_add_mode(self):
        admin = _make_admin()
        request = _make_request()
        fields = admin.get_readonly_fields(request, obj=None)
        assert isinstance(fields, tuple)

    def test_get_readonly_fields_edit_completed(self):
        admin = _make_admin()
        request = _make_request()
        obj = MagicMock()
        obj.status = "completed"
        fields = admin.get_readonly_fields(request, obj=obj)
        assert "user" in fields
        assert "contract_title" in fields
        assert "status" in fields

    def test_get_readonly_fields_edit_pending(self):
        admin = _make_admin()
        request = _make_request()
        obj = MagicMock()
        obj.status = "pending"
        fields = admin.get_readonly_fields(request, obj=obj)
        assert "id" in fields


@pytest.mark.django_db
class TestReviewTaskAdminGetFieldsets:
    """测试 get_fieldsets"""

    def test_get_fieldsets_with_parties(self):
        admin = _make_admin()
        request = _make_request()
        obj = MagicMock()
        obj.party_a = "甲方"
        obj.party_b = "乙方"
        obj.party_c = ""
        obj.party_d = ""
        obj.review_report = ""
        fieldsets = admin.get_fieldsets(request, obj)
        assert isinstance(fieldsets, list)
        party_fieldset = next(f for f in fieldsets if f[0] == "当事人")
        assert "party_a" in party_fieldset[1]["fields"]

    def test_get_fieldsets_no_parties(self):
        admin = _make_admin()
        request = _make_request()
        obj = MagicMock()
        obj.party_a = ""
        obj.party_b = ""
        obj.party_c = ""
        obj.party_d = ""
        obj.review_report = ""
        fieldsets = admin.get_fieldsets(request, obj)
        assert isinstance(fieldsets, list)


@pytest.mark.django_db
class TestReviewTaskAdminFileLink:
    """测试 _file_link 静态方法"""

    def test_file_link_primary(self):
        obj = MagicMock()
        obj.pk = uuid4()
        result = str(ReviewTaskAdmin._file_link(obj, "/path/to/file.docx", primary=True))
        assert "file.docx" in result
        assert "download" in result

    def test_file_link_non_primary(self):
        obj = MagicMock()
        obj.pk = uuid4()
        result = str(ReviewTaskAdmin._file_link(obj, "/path/to/original.docx", primary=False))
        assert "original.docx" in result
        assert "download-original" in result


@pytest.mark.django_db
class TestReviewTaskAdminRedirectBack:
    """测试 _redirect_back"""

    def test_redirect_back_with_referer(self):
        admin = _make_admin()
        request = MagicMock()
        request.META = {"HTTP_REFERER": "/admin/contract_review/reviewtask/"}
        result = admin._redirect_back(request)
        assert result.status_code == 302
        # 有 Referer 时回到来源页
        assert result.url == "/admin/contract_review/reviewtask/"

    def test_redirect_back_without_referer(self):
        admin = _make_admin()
        request = MagicMock()
        request.META = {}
        result = admin._redirect_back(request)
        assert result.status_code == 302
        # 无 Referer 时回落到 changelist
        assert result.url == "/admin/contract_review/reviewtask/"


@pytest.mark.django_db
class TestReportViewSanitization:
    """评估报告视图 XSS 消毒：review_report 为 LLM 对用户合同的输出，可能回显恶意 HTML"""

    def _make_task_and_request(self, review_report: str, path: str):
        """创建任务 + 以真实已保存的 superuser 构造请求。

        不复用 _make_request 的未保存假用户：each_context 会按 request.user
        过滤 ToolFavorite，未保存实例在 queryset 过滤时抛 ValueError。
        """
        from apps.organization.models import LawFirm, Lawyer

        firm = LawFirm.objects.create(name="报告消毒测试律所")
        user = Lawyer.objects.create_user(
            username="sanuser",
            password="testpass123",  # pragma: allowlist secret
            law_firm=firm,
            is_staff=True,
            is_superuser=True,
        )
        task = ReviewTask.objects.create(
            user=user,
            original_file="恶意合同.docx",
            review_report=review_report,
        )
        factory = RequestFactory()
        request = factory.get(path)
        request.user = user
        return task, request

    def test_report_view_strips_script_and_event_attrs(self):
        """report_view 的 report_html 必须经白名单消毒（脚本/事件属性剥离）"""
        admin = _make_admin()
        task, request = self._make_task_and_request(
            "# 审查结论\n\n"
            '<script>alert("xss")</script>\n\n'
            '<img src="https://evil.example.com/a.png" onerror="alert(1)">\n\n'
            '<a href="javascript:alert(1)">点我</a>',
            path="/admin/contract_review/reviewtask/report/",
        )
        response = admin.report_view(request, task.id)
        html = str(response.context_data["report_html"])
        # script 标签剥离（内部文本保留为纯文本，不可执行）、事件属性剥离、危险协议剥离
        assert "<script" not in html
        assert "onerror" not in html
        assert "javascript:" not in html
        # 正常 markdown 输出保留
        assert "<h1>" in html

    def test_report_pdf_view_strips_script_and_event_attrs(self):
        """report_pdf_view 渲染 PDF 前同样消毒"""
        from unittest.mock import patch

        admin = _make_admin()
        task, request = self._make_task_and_request(
            '# 审查结论\n\n<script>alert("pdf-xss")</script>\n\n<p onclick="evil()">条款</p>',
            path="/admin/contract_review/reviewtask/report/pdf/",
        )
        with patch("weasyprint.HTML") as mock_html:
            mock_html.return_value.write_pdf.return_value = b"%PDF-1.4 fake"
            response = admin.report_pdf_view(request, task.id)
        assert response.status_code == 200
        rendered = str(mock_html.call_args.kwargs.get("string", ""))
        assert "<script>" not in rendered
        assert "onclick" not in rendered
        assert "<h1>" in rendered
