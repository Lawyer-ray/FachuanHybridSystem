"""
文书模板 CRUD API 集成测试

通过直接调用 API 函数测试完整的 CRUD 流程。
使用 factories 创建测试数据。

Requirements: 5.3
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest

from apps.core.exceptions import NotFoundError
from apps.documents.api.document_api import (
    create_document_template,
    delete_document_template,
    get_document_template,
    list_document_templates,
    update_document_template,
)
from apps.documents.models import DocumentTemplate, DocumentTemplateType
from apps.documents.schemas import DocumentTemplateIn, DocumentTemplateUpdate
from tests.factories.document_factories import DocumentTemplateFactory
from tests.factories.organization_factories import LawyerFactory


def _make_request(user: Any = None) -> Mock:
    """构造模拟 request 对象。"""
    request = Mock()
    request.user = user
    return request


@pytest.mark.django_db
@pytest.mark.integration
class TestDocumentTemplateCreateAPI:
    """文书模板创建 API 测试"""

    def test_create_template_minimal(self) -> None:
        """最小字段创建文书模板（无文件路径）"""
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        payload = DocumentTemplateIn(
            name="测试合同模板",
        )
        result = create_document_template(request, payload)

        assert result.id is not None
        assert result.name == "测试合同模板"
        assert result.is_active is True

    def test_create_template_with_full_fields(self) -> None:
        """完整字段创建文书模板"""
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        payload = DocumentTemplateIn(
            name="完整模板",
            description="测试描述",
            template_type=DocumentTemplateType.CASE,
            is_active=True,
        )
        result = create_document_template(request, payload)

        assert result.name == "完整模板"
        assert result.description == "测试描述"
        assert result.template_type == DocumentTemplateType.CASE


@pytest.mark.django_db
@pytest.mark.integration
class TestDocumentTemplateListAPI:
    """文书模板列表查询 API 测试"""

    def test_list_templates_empty(self) -> None:
        """空列表查询"""
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        result = list_document_templates(request)
        assert len(list(result)) == 0

    def test_list_templates_returns_all(self) -> None:
        """查询所有模板"""
        DocumentTemplateFactory.create_batch(3)
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        result = list_document_templates(request)
        assert len(list(result)) == 3

    def test_list_templates_filter_by_type(self) -> None:
        """按模板类型过滤"""
        DocumentTemplateFactory.create_batch(2, template_type=DocumentTemplateType.CONTRACT)
        DocumentTemplateFactory(template_type=DocumentTemplateType.CASE)
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        result = list_document_templates(request, template_type=DocumentTemplateType.CONTRACT)
        assert len(list(result)) == 2

    def test_list_templates_filter_by_active(self) -> None:
        """按启用状态过滤"""
        DocumentTemplateFactory.create_batch(2, is_active=True)
        DocumentTemplateFactory(is_active=False)
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        result = list_document_templates(request, is_active=True)
        assert len(list(result)) == 2


@pytest.mark.django_db
@pytest.mark.integration
class TestDocumentTemplateGetAPI:
    """文书模板详情查询 API 测试"""

    def test_get_template_success(self) -> None:
        """获取模板详情"""
        template = DocumentTemplateFactory(name="详情测试模板")
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        result = get_document_template(request, template.id)  # type: ignore[attr-defined]

        assert result.id == template.id  # type: ignore[attr-defined]
        assert result.name == "详情测试模板"

    def test_get_template_not_found(self) -> None:
        """获取不存在的模板"""
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        with pytest.raises(NotFoundError):
            get_document_template(request, 999999)


@pytest.mark.django_db
@pytest.mark.integration
class TestDocumentTemplateUpdateAPI:
    """文书模板更新 API 测试"""

    def test_update_template_name(self) -> None:
        """更新模板名称"""
        template = DocumentTemplateFactory(name="旧名称")
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        payload = DocumentTemplateUpdate(name="新名称")
        result = update_document_template(request, template.id, payload)  # type: ignore[attr-defined]

        assert result.name == "新名称"
        template.refresh_from_db()  # type: ignore[attr-defined]
        assert template.name == "新名称"

    def test_update_template_partial(self) -> None:
        """部分更新（只更新指定字段）"""
        template = DocumentTemplateFactory(name="原名称", description="原描述")
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        payload = DocumentTemplateUpdate(description="新描述")
        result = update_document_template(request, template.id, payload)  # type: ignore[attr-defined]

        assert result.name == "原名称"
        assert result.description == "新描述"

    def test_update_template_not_found(self) -> None:
        """更新不存在的模板"""
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        payload = DocumentTemplateUpdate(name="新名称")
        with pytest.raises(NotFoundError):
            update_document_template(request, 999999, payload)


@pytest.mark.django_db
@pytest.mark.integration
class TestDocumentTemplateDeleteAPI:
    """文书模板删除 API 测试（软删除）"""

    def test_delete_template_success(self) -> None:
        """软删除模板"""
        template = DocumentTemplateFactory()
        template_id = template.id  # type: ignore[attr-defined]
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        result = delete_document_template(request, template_id)

        assert result["success"] is True
        template.refresh_from_db()  # type: ignore[attr-defined]
        assert template.is_active is False

    def test_delete_template_not_found(self) -> None:
        """删除不存在的模板"""
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        with pytest.raises(NotFoundError):
            delete_document_template(request, 999999)
