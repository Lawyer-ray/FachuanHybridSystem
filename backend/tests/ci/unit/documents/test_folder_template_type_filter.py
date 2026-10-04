"""第四轮审查修复回归测试：文件夹模板列表接通 template_type 过滤。

此前 API 层收到 template_type 参数但未下传查询层（静默丢弃），
列表固定只返回案件模板；现在参数贯通 query_service → usecases → service。
"""

from __future__ import annotations

from unittest.mock import MagicMock

from apps.documents.models import FolderTemplateType
from apps.documents.services.folder_template.query_service import FolderTemplateQueryService


def _make_service() -> tuple[FolderTemplateQueryService, MagicMock]:
    repo = MagicMock()
    repo.filter.return_value.order_by.return_value.all.return_value = []
    svc = FolderTemplateQueryService(repo=repo, id_service=MagicMock())
    return svc, repo


class TestListTemplatesTemplateType:
    def test_template_type_passed_to_repo(self):
        svc, repo = _make_service()
        svc.list_templates(template_type=FolderTemplateType.CONTRACT)
        repo.filter.assert_called_once_with(template_type=FolderTemplateType.CONTRACT)

    def test_default_falls_back_to_case(self):
        """未显式指定类型时维持既有口径：仅返回案件文件夹模板。"""
        svc, repo = _make_service()
        svc.list_templates()
        repo.filter.assert_called_once_with(template_type=FolderTemplateType.CASE)

    def test_other_filters_still_applied(self):
        svc, repo = _make_service()
        svc.list_templates(template_type=FolderTemplateType.CONTRACT, case_type="civil", is_active=True)
        # repo 层按类型过滤；case_type/is_active 在内存过滤（结果为空列表不触发）
        repo.filter.assert_called_once_with(template_type=FolderTemplateType.CONTRACT)
