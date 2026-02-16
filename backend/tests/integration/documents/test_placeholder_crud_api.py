"""
替换词 CRUD API 集成测试

通过直接调用 API 函数测试完整的 CRUD 流程。

Requirements: 5.3
"""
from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest

from apps.documents.api.placeholder_api import (
    create_placeholder,
    delete_placeholder,
    get_placeholder,
    get_placeholder_by_key,
    list_placeholders,
    update_placeholder,
)
from apps.documents.models import Placeholder
from apps.documents.schemas import PlaceholderIn, PlaceholderUpdate
from apps.core.exceptions import NotFoundError, ValidationException
from tests.factories.organization_factories import LawyerFactory


def _make_request(user: Any = None) -> Mock:
    """构造模拟 request 对象。"""
    request = Mock()
    request.user = user
    return request


@pytest.mark.django_db
@pytest.mark.integration
class TestPlaceholderCreateAPI:
    """替换词创建 API 测试"""

    def test_create_placeholder_minimal(self) -> None:
        """最小字段创建替换词"""
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        payload = PlaceholderIn(
            key="case_name",
            display_name="案件名称",
        )
        result = create_placeholder(request, payload)

        assert result.id is not None
        assert result.key == "case_name"
        assert result.display_name == "案件名称"
        assert result.is_active is True

    def test_create_placeholder_with_full_fields(self) -> None:
        """完整字段创建替换词"""
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        payload = PlaceholderIn(
            key="contract_amount",
            display_name="合同金额",
            example_value="50000.00",
            description="合同约定的总金额",
            is_active=True,
        )
        result = create_placeholder(request, payload)

        assert result.key == "contract_amount"
        assert result.display_name == "合同金额"
        assert result.example_value == "50000.00"
        assert result.description == "合同约定的总金额"

    def test_create_placeholder_duplicate_key(self) -> None:
        """重复键创建失败"""
        Placeholder.objects.create(key="dup_key", display_name="已存在")
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        payload = PlaceholderIn(key="dup_key", display_name="重复")
        with pytest.raises(ValidationException):
            create_placeholder(request, payload)


@pytest.mark.django_db
@pytest.mark.integration
class TestPlaceholderListAPI:
    """替换词列表查询 API 测试"""

    def test_list_placeholders_empty(self) -> None:
        """空列表查询"""
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        result = list_placeholders(request)
        assert len(list(result)) == 0

    def test_list_placeholders_returns_active(self) -> None:
        """默认只返回活跃的替换词"""
        Placeholder.objects.create(
            key="active_key", display_name="活跃", is_active=True
        )
        Placeholder.objects.create(
            key="inactive_key", display_name="禁用", is_active=False
        )
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        result = list_placeholders(request)
        keys = [p.key for p in result]
        assert "active_key" in keys
        assert "inactive_key" not in keys

    def test_list_placeholders_filter_inactive(self) -> None:
        """过滤禁用的替换词"""
        Placeholder.objects.create(
            key="a_key", display_name="活跃", is_active=True
        )
        Placeholder.objects.create(
            key="b_key", display_name="禁用", is_active=False
        )
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        result = list_placeholders(request, is_active=False)
        keys = [p.key for p in result]
        assert "b_key" in keys
        assert "a_key" not in keys


@pytest.mark.django_db
@pytest.mark.integration
class TestPlaceholderGetAPI:
    """替换词详情查询 API 测试"""

    def test_get_placeholder_by_id_success(self) -> None:
        """根据 ID 获取替换词"""
        ph = Placeholder.objects.create(
            key="test_key", display_name="测试"
        )
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        result = get_placeholder(request, ph.id)
        assert result.key == "test_key"

    def test_get_placeholder_by_id_not_found(self) -> None:
        """获取不存在的替换词"""
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        with pytest.raises(NotFoundError):
            get_placeholder(request, 999999)

    def test_get_placeholder_by_key_success(self) -> None:
        """根据键获取替换词"""
        Placeholder.objects.create(
            key="lookup_key", display_name="查找测试"
        )
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        result = get_placeholder_by_key(request, "lookup_key")
        assert result.display_name == "查找测试"

    def test_get_placeholder_by_key_not_found(self) -> None:
        """根据不存在的键查找"""
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        with pytest.raises(NotFoundError):
            get_placeholder_by_key(request, "nonexistent_key")


@pytest.mark.django_db
@pytest.mark.integration
class TestPlaceholderUpdateAPI:
    """替换词更新 API 测试"""

    def test_update_placeholder_display_name(self) -> None:
        """更新显示名称"""
        ph = Placeholder.objects.create(
            key="upd_key", display_name="旧名称"
        )
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        payload = PlaceholderUpdate(display_name="新名称")
        result = update_placeholder(request, ph.id, payload)

        assert result.display_name == "新名称"
        ph.refresh_from_db()
        assert ph.display_name == "新名称"

    def test_update_placeholder_not_found(self) -> None:
        """更新不存在的替换词"""
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        payload = PlaceholderUpdate(display_name="新名称")
        with pytest.raises(NotFoundError):
            update_placeholder(request, 999999, payload)


@pytest.mark.django_db
@pytest.mark.integration
class TestPlaceholderDeleteAPI:
    """替换词删除 API 测试（软删除）"""

    def test_delete_placeholder_success(self) -> None:
        """软删除替换词"""
        ph = Placeholder.objects.create(
            key="del_key", display_name="待删除"
        )
        ph_id = ph.id
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        result = delete_placeholder(request, ph_id)

        assert result["success"] is True
        ph.refresh_from_db()
        assert ph.is_active is False

    def test_delete_placeholder_not_found(self) -> None:
        """删除不存在的替换词"""
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        with pytest.raises(NotFoundError):
            delete_placeholder(request, 999999)
