"""Client Model 测试 - Client, ClientIdentityDoc, PropertyClue"""

from __future__ import annotations

from typing import Any

import pytest

from apps.client.models import Client, ClientIdentityDoc, PropertyClue, PropertyClueAttachment


@pytest.mark.django_db
class TestClientModel:
    """Client 模型测试"""

    def test_str_representation(self) -> None:
        """__str__ 应返回客户名称"""
        client = Client.objects.create(name="测试客户", client_type="natural")
        assert str(client) == "测试客户"

    def test_create_natural_client(self) -> None:
        """创建自然人客户"""
        client = Client.objects.create(name="自然人", client_type="natural")
        assert client.client_type == "natural"

    def test_create_legal_client(self) -> None:
        """创建法人客户"""
        client = Client.objects.create(
            name="法人公司", client_type="legal", legal_representative="法定代表人"
        )
        assert client.client_type == "legal"
        assert client.legal_representative == "法定代表人"

    def test_create_non_legal_org_client(self) -> None:
        """创建非法人组织客户"""
        client = Client.objects.create(
            name="非法人组织", client_type="non_legal_org", legal_representative="负责人"
        )
        assert client.client_type == "non_legal_org"

    def test_is_our_client(self) -> None:
        """我方当事人标记"""
        client = Client.objects.create(name="我方客户", client_type="natural", is_our_client=True)
        assert client.is_our_client is True

    def test_client_type_choices(self) -> None:
        """客户类型选项"""
        assert Client.NATURAL == "natural"
        assert Client.LEGAL == "legal"
        assert Client.NON_LEGAL_ORG == "non_legal_org"


@pytest.mark.django_db
class TestClientIdentityDocModel:
    """ClientIdentityDoc 模型测试"""

    def test_create_id_card(self) -> None:
        """创建身份证件"""
        client = Client.objects.create(name="证件测试客户", client_type="natural")
        doc = ClientIdentityDoc.objects.create(
            client=client,
            doc_type="id_card",
            file_path="identity_docs/test_id.pdf",
        )
        assert doc.doc_type == "id_card"

    def test_create_business_license(self) -> None:
        """创建营业执照"""
        client = Client.objects.create(
            name="执照测试公司", client_type="legal", legal_representative="法定代表人"
        )
        doc = ClientIdentityDoc.objects.create(
            client=client,
            doc_type="business_license",
            file_path="identity_docs/test_license.pdf",
        )
        assert doc.doc_type == "business_license"

    def test_doc_type_choices(self) -> None:
        """证件类型选项"""
        assert ClientIdentityDoc.ID_CARD == "id_card"
        assert ClientIdentityDoc.BUSINESS_LICENSE == "business_license"


@pytest.mark.django_db
class TestPropertyClueModel:
    """PropertyClue 模型测试"""

    def test_create_property_clue(self) -> None:
        """创建财产线索"""
        client = Client.objects.create(name="财产线索测试客户", client_type="natural")
        clue = PropertyClue.objects.create(
            client=client,
            clue_type="bank_account",
        )
        assert clue.clue_type == "bank_account"

    def test_property_clue_with_value(self) -> None:
        """创建财产线索"""
        from decimal import Decimal

        client = Client.objects.create(name="价值测试客户", client_type="natural")
        clue = PropertyClue.objects.create(
            client=client,
            clue_type="real_estate",
        )
        assert clue.clue_type == "real_estate"


@pytest.mark.django_db
class TestPropertyClueAttachmentModel:
    """PropertyClueAttachment 模型测试"""

    def test_create_attachment(self) -> None:
        """创建财产线索附件"""
        client = Client.objects.create(name="附件测试客户", client_type="natural")
        clue = PropertyClue.objects.create(
            client=client, clue_type="bank_account"
        )
        attachment = PropertyClueAttachment.objects.create(
            property_clue=clue,
            file_path="property_clues/test_attachment.pdf",
        )
        assert attachment.property_clue == clue
