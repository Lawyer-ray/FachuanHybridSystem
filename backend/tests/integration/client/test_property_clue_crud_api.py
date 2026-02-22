"""
财产线索 CRUD API 集成测试

通过直接调用 Service 函数测试完整的 CRUD 流程。
使用 factories 创建测试数据。

注意：PropertyClue API 返回 PropertyClueOut schema，需要 clue_type_label 等字段，
因此直接测试 Service 层方法以验证核心业务逻辑。

Requirements: 5.4
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest

from apps.client.models import PropertyClue, PropertyClueAttachment
from apps.client.services.property_clue_service import PropertyClueService
from apps.core.exceptions import NotFoundError, ValidationException
from tests.factories.client_factories import ClientFactory
from tests.factories.organization_factories import LawyerFactory


@pytest.mark.django_db
@pytest.mark.integration
class TestPropertyClueCreate:
    """财产线索创建测试"""

    def test_create_clue_default_type(self) -> None:
        """创建默认类型（银行账户）财产线索"""
        client = ClientFactory()
        lawyer = LawyerFactory(is_admin=True)
        service = PropertyClueService()

        clue = service.create_clue(
            client_id=client.id,  # type: ignore[attr-defined]
            data={"content": "户名：张三\n开户行：工商银行"},
            user=lawyer,
        )

        assert clue.id is not None
        assert clue.client_id == client.id  # type: ignore[attr-defined]
        assert clue.clue_type == PropertyClue.BANK
        assert "张三" in clue.content

    def test_create_clue_real_estate(self) -> None:
        """创建不动产类型财产线索"""
        client = ClientFactory()
        service = PropertyClueService()

        clue = service.create_clue(
            client_id=client.id,  # type: ignore[attr-defined]
            data={"clue_type": "real_estate", "content": "北京市朝阳区某小区"},
        )

        assert clue.clue_type == PropertyClue.REAL_ESTATE

    def test_create_clue_client_not_found(self) -> None:
        """当事人不存在时创建失败"""
        service = PropertyClueService()

        with pytest.raises(NotFoundError):
            service.create_clue(client_id=999999, data={})

    def test_create_clue_invalid_type(self) -> None:
        """无效线索类型被拒绝"""
        client = ClientFactory()
        service = PropertyClueService()

        with pytest.raises(ValidationException):
            service.create_clue(
                client_id=client.id,  # type: ignore[attr-defined]
                data={"clue_type": "invalid_type"},
            )


@pytest.mark.django_db
@pytest.mark.integration
class TestPropertyClueList:
    """财产线索列表查询测试"""

    def test_list_clues_empty(self) -> None:
        """空列表查询"""
        client = ClientFactory()
        service = PropertyClueService()

        clues = service.list_clues_by_client(client_id=client.id)  # type: ignore[attr-defined]
        assert len(clues) == 0

    def test_list_clues_returns_all(self) -> None:
        """查询当事人所有线索"""
        client = ClientFactory()
        service = PropertyClueService()

        service.create_clue(client_id=client.id, data={"clue_type": "bank"})  # type: ignore[attr-defined]
        service.create_clue(client_id=client.id, data={"clue_type": "wechat"})  # type: ignore[attr-defined]

        clues = service.list_clues_by_client(client_id=client.id)  # type: ignore[attr-defined]
        assert len(clues) == 2

    def test_list_clues_client_not_found(self) -> None:
        """当事人不存在时查询失败"""
        service = PropertyClueService()

        with pytest.raises(NotFoundError):
            service.list_clues_by_client(client_id=999999)


@pytest.mark.django_db
@pytest.mark.integration
class TestPropertyClueGet:
    """财产线索详情查询测试"""

    def test_get_clue_success(self) -> None:
        """获取线索详情"""
        client = ClientFactory()
        service = PropertyClueService()
        clue = service.create_clue(
            client_id=client.id,  # type: ignore[attr-defined]
            data={"content": "测试内容"},
        )

        result = service.get_clue(clue_id=clue.id)

        assert result.id == clue.id
        assert result.content == "测试内容"

    def test_get_clue_not_found(self) -> None:
        """获取不存在的线索"""
        service = PropertyClueService()

        with pytest.raises(NotFoundError):
            service.get_clue(clue_id=999999)


@pytest.mark.django_db
@pytest.mark.integration
class TestPropertyClueUpdate:
    """财产线索更新测试"""

    def test_update_clue_content(self) -> None:
        """更新线索内容"""
        client = ClientFactory()
        service = PropertyClueService()
        clue = service.create_clue(
            client_id=client.id,  # type: ignore[attr-defined]
            data={"content": "旧内容"},
        )

        result = service.update_clue(
            clue_id=clue.id,
            data={"content": "新内容"},
        )

        assert result.content == "新内容"

    def test_update_clue_type(self) -> None:
        """更新线索类型"""
        client = ClientFactory()
        service = PropertyClueService()
        clue = service.create_clue(
            client_id=client.id,  # type: ignore[attr-defined]
            data={"clue_type": "bank"},
        )

        result = service.update_clue(
            clue_id=clue.id,
            data={"clue_type": "alipay"},
        )

        assert result.clue_type == PropertyClue.ALIPAY

    def test_update_clue_not_found(self) -> None:
        """更新不存在的线索"""
        service = PropertyClueService()

        with pytest.raises(NotFoundError):
            service.update_clue(clue_id=999999, data={"content": "x"})

    def test_update_clue_invalid_type(self) -> None:
        """更新为无效线索类型被拒绝"""
        client = ClientFactory()
        service = PropertyClueService()
        clue = service.create_clue(client_id=client.id, data={})  # type: ignore[attr-defined]

        with pytest.raises(ValidationException):
            service.update_clue(
                clue_id=clue.id,
                data={"clue_type": "invalid"},
            )


@pytest.mark.django_db
@pytest.mark.integration
class TestPropertyClueDelete:
    """财产线索删除测试"""

    def test_delete_clue_success(self) -> None:
        """删除线索"""
        client = ClientFactory()
        service = PropertyClueService()
        clue = service.create_clue(client_id=client.id, data={})  # type: ignore[attr-defined]
        clue_id = clue.id

        service.delete_clue(clue_id=clue_id)

        assert not PropertyClue.objects.filter(id=clue_id).exists()

    def test_delete_clue_cascades_attachments(self) -> None:
        """删除线索时级联删除附件"""
        client = ClientFactory()
        service = PropertyClueService()
        clue = service.create_clue(client_id=client.id, data={})  # type: ignore[attr-defined]
        attachment = service.add_attachment(
            clue_id=clue.id,
            file_path="/tmp/test.pdf",
            file_name="test.pdf",
        )
        attachment_id = attachment.id

        service.delete_clue(clue_id=clue.id)

        assert not PropertyClueAttachment.objects.filter(id=attachment_id).exists()

    def test_delete_clue_not_found(self) -> None:
        """删除不存在的线索"""
        service = PropertyClueService()

        with pytest.raises(NotFoundError):
            service.delete_clue(clue_id=999999)


@pytest.mark.django_db
@pytest.mark.integration
class TestPropertyClueAttachment:
    """财产线索附件测试"""

    def test_add_attachment_success(self) -> None:
        """添加附件"""
        client = ClientFactory()
        service = PropertyClueService()
        clue = service.create_clue(client_id=client.id, data={})  # type: ignore[attr-defined]

        attachment = service.add_attachment(
            clue_id=clue.id,
            file_path="/tmp/evidence.pdf",
            file_name="evidence.pdf",
        )

        assert attachment.id is not None
        assert attachment.file_name == "evidence.pdf"
        assert attachment.property_clue_id == clue.id

    def test_add_attachment_clue_not_found(self) -> None:
        """线索不存在时添加附件失败"""
        service = PropertyClueService()

        with pytest.raises(NotFoundError):
            service.add_attachment(
                clue_id=999999,
                file_path="/tmp/test.pdf",
                file_name="test.pdf",
            )

    def test_delete_attachment_success(self) -> None:
        """删除附件"""
        client = ClientFactory()
        service = PropertyClueService()
        clue = service.create_clue(client_id=client.id, data={})  # type: ignore[attr-defined]
        attachment = service.add_attachment(
            clue_id=clue.id,
            file_path="/tmp/test.pdf",
            file_name="test.pdf",
        )
        attachment_id = attachment.id

        service.delete_attachment(attachment_id=attachment_id)

        assert not PropertyClueAttachment.objects.filter(id=attachment_id).exists()

    def test_delete_attachment_not_found(self) -> None:
        """删除不存在的附件"""
        service = PropertyClueService()

        with pytest.raises(NotFoundError):
            service.delete_attachment(attachment_id=999999)
