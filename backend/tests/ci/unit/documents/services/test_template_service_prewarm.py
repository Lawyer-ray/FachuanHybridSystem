"""DocumentTemplateService prewarm / list_templates_prewarmed 单元测试。

覆盖预热查询的过滤口径（template_type / case_type / is_active）与
关系物化行为，ORM 以 mock 替代。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from apps.documents.services.template.template_service import DocumentTemplateService

MODULE = "apps.documents.services.template.template_service"


def _binding() -> MagicMock:
    binding = MagicMock()
    binding.folder_template_id = 1
    binding.folder_template.name = "民事 folder"
    return binding


def _template(bindings: list[MagicMock]) -> MagicMock:
    template = MagicMock()
    template.folder_bindings.all.return_value = bindings
    return template


def test_prewarm_template_uses_prefetch() -> None:
    service = DocumentTemplateService()
    with patch(f"{MODULE}.DocumentTemplate") as mock_model:
        mock_model.objects.prefetch_related.return_value.get.return_value = "prewarmed"  # type: ignore[return-value]
        obj = MagicMock()
        obj.pk = 5
        result = service.prewarm_template(obj)  # type: ignore[assignment]

    mock_model.objects.prefetch_related.assert_called_once_with("folder_bindings__folder_template")
    mock_model.objects.prefetch_related.return_value.get.assert_called_once_with(pk=5)
    assert result == "prewarmed"


def test_list_templates_prewarmed_applies_filters() -> None:
    service = DocumentTemplateService()
    binding = _binding()
    template = _template([binding])

    with patch(f"{MODULE}.DocumentTemplate") as mock_model:
        qs = MagicMock()
        qs.filter.return_value = qs
        qs.__iter__ = MagicMock(return_value=iter([template]))  # type: ignore[assignment]
        mock_model.objects.prefetch_related.return_value = qs

        result = service.list_templates_prewarmed(template_type="case", case_type="civil", is_active=True)

    assert result == [template]
    assert qs.filter.call_count == 3
    binding.folder_template.name  # 物化访问（不抛错即通过）


def test_list_templates_prewarmed_no_filters() -> None:
    service = DocumentTemplateService()
    with patch(f"{MODULE}.DocumentTemplate") as mock_model:
        qs = MagicMock()
        qs.__iter__ = MagicMock(return_value=iter([]))  # type: ignore[assignment]
        mock_model.objects.prefetch_related.return_value = qs

        result = service.list_templates_prewarmed()

    assert result == []
    qs.filter.assert_not_called()
