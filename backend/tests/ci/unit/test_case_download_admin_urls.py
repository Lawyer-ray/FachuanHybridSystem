from __future__ import annotations

from types import SimpleNamespace

from django.urls import reverse

from apps.legal_research.admin.case_download_admin import CaseDownloadResultInline


def test_case_download_result_admin_reverse_registered() -> None:
    url = reverse("admin:legal_research_casedownloadresult_download", args=[7])
    assert url.endswith("/admin/legal_research/casedownloadtask/result/7/download/")


def test_case_download_result_inline_download_link_works() -> None:
    obj = SimpleNamespace(status="success", pk=7)
    link_html = CaseDownloadResultInline.download_link(SimpleNamespace(), obj)
    assert "result/7/download/" in link_html
