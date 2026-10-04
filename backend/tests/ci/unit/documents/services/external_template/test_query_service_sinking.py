"""外部模板 query_service 下沉能力单元测试。

覆盖 ensure_templates_owned（superuser 豁免 / 跨律所拒绝 / 全部自有）
与 update_mapping_fields（非空字段更新 + updated_at 恒参与）。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import PermissionDenied
from apps.documents.services.external_template.query_service import ensure_templates_owned, update_mapping_fields

MODULE = "apps.documents.services.external_template.query_service"


def _user(*, is_superuser: bool = False, law_firm_id: int | None = 1) -> SimpleNamespace:
    return SimpleNamespace(is_superuser=is_superuser, law_firm_id=law_firm_id)


def _manager_owning(own_ids: set[int]) -> MagicMock:
    manager = MagicMock()
    qs = MagicMock()
    qs.values_list.return_value = list(own_ids)
    manager.filter.return_value = qs
    return manager


# ── ensure_templates_owned ──────────────────────────────────────────────────


def test_superuser_bypasses_query() -> None:
    with patch(f"{MODULE}.ExternalTemplate") as mock_model:
        ensure_templates_owned([1, 2, 3], _user(is_superuser=True))
    mock_model.objects.filter.assert_not_called()


def test_all_owned_passes() -> None:
    with patch(f"{MODULE}.ExternalTemplate") as mock_model:
        mock_model.objects = _manager_owning({1, 2})
        assert ensure_templates_owned([1, 2], _user()) is None  # 不抛异常
        mock_model.objects.filter.assert_called_once()


def test_foreign_templates_rejected() -> None:
    with patch(f"{MODULE}.ExternalTemplate") as mock_model:
        mock_model.objects = _manager_owning({1})
        with pytest.raises(PermissionDenied) as exc_info:
            ensure_templates_owned([1, 2, 3], _user())
    assert exc_info.value.code == "TEMPLATE_FIRM_FORBIDDEN"
    assert exc_info.value.errors == {"template_ids": [2, 3]}


# ── update_mapping_fields ───────────────────────────────────────────────────


def test_update_mapping_fields_partial_update() -> None:
    mapping = MagicMock()
    mapping.semantic_label = "原标签"  # 预置值：None 入参不应覆盖
    update_mapping_fields(mapping, semantic_label=None, fill_type="date", position_description="首部")
    assert mapping.semantic_label == "原标签"  # None 字段不覆盖
    assert mapping.fill_type == "date"
    assert mapping.position_description == "首部"
    mapping.save.assert_called_once_with(update_fields=["updated_at", "fill_type", "position_description"])


def test_update_mapping_fields_all_none_still_saves() -> None:
    mapping = MagicMock()
    update_mapping_fields(mapping, semantic_label=None, fill_type=None, position_description=None)
    mapping.save.assert_called_once_with(update_fields=["updated_at"])
