"""client app 补充 Model 单元测试

覆盖 Client 的 clean() 验证逻辑、__str__、choices，
以及 ClientIdentityDoc 的 clean() 验证逻辑。
"""

import pytest
from django.core.exceptions import ValidationError

from apps.client.models.client import Client
from apps.client.models.identity_doc import ClientIdentityDoc
from apps.testing.factories import ClientFactory, ClientIdentityDocFactory


# ============================================================
# Client
# ============================================================


@pytest.mark.django_db
class TestClient:
    def test_str(self):
        client = Client.objects.create(name="张三", client_type=Client.NATURAL)
        assert str(client) == "张三"

    def test_client_type_choices(self):
        assert Client.NATURAL == "natural"
        assert Client.LEGAL == "legal"
        assert Client.NON_LEGAL_ORG == "non_legal_org"

    def test_clean_legal_with_representative(self):
        """法人类型有法定代表人应通过验证"""
        client = Client(
            name="测试公司",
            client_type=Client.LEGAL,
            legal_representative="李四",
        )
        client.clean()  # 不应抛异常

    def test_clean_legal_without_representative(self):
        """法人类型没有法定代表人应抛出 ValidationError"""
        client = Client(
            name="测试公司",
            client_type=Client.LEGAL,
            legal_representative=None,
        )
        with pytest.raises(ValidationError):
            client.clean()

    def test_clean_legal_empty_representative(self):
        """法人类型法定代表人为空字符串应抛出 ValidationError"""
        client = Client(
            name="测试公司",
            client_type=Client.LEGAL,
            legal_representative="",
        )
        with pytest.raises(ValidationError):
            client.clean()

    def test_clean_natural_no_representative_required(self):
        """自然人类型不需要法定代表人"""
        client = Client(
            name="张三",
            client_type=Client.NATURAL,
        )
        client.clean()  # 不应抛异常

    def test_clean_non_legal_org_with_representative(self):
        """非法人组织有负责人应通过验证"""
        client = Client(
            name="合伙企业",
            client_type=Client.NON_LEGAL_ORG,
            legal_representative="王五",
        )
        client.clean()

    def test_default_client_type(self):
        client = Client.objects.create(name="默认类型")
        assert client.client_type == Client.LEGAL

    def test_is_our_client_default(self):
        client = Client.objects.create(name="默认我方", client_type=Client.NATURAL)
        assert client.is_our_client is False


# ============================================================
# ClientIdentityDoc
# ============================================================


@pytest.mark.django_db
class TestClientIdentityDoc:
    def test_str_empty(self):
        """__str__ 返回空字符串（避免 Admin inline 泄露）"""
        client = ClientFactory(client_type=Client.NATURAL)
        doc = ClientIdentityDocFactory(client=client, doc_type=ClientIdentityDoc.ID_CARD)
        assert str(doc) == ""

    def test_clean_natural_valid_doc_type(self):
        """自然人使用身份证应通过验证"""
        client = ClientFactory(client_type=Client.NATURAL)
        doc = ClientIdentityDoc(client=client, doc_type=ClientIdentityDoc.ID_CARD, file_path="test.pdf")
        doc.clean()

    def test_clean_natural_passport(self):
        """自然人使用护照应通过验证"""
        client = ClientFactory(client_type=Client.NATURAL)
        doc = ClientIdentityDoc(client=client, doc_type=ClientIdentityDoc.PASSPORT, file_path="test.pdf")
        doc.clean()

    def test_clean_natural_hk_macao_permit(self):
        """自然人使用港澳通行证应通过验证"""
        client = ClientFactory(client_type=Client.NATURAL)
        doc = ClientIdentityDoc(client=client, doc_type=ClientIdentityDoc.HK_MACAO_PERMIT, file_path="test.pdf")
        doc.clean()

    def test_clean_natural_residence_permit(self):
        """自然人使用居住证应通过验证"""
        client = ClientFactory(client_type=Client.NATURAL)
        doc = ClientIdentityDoc(client=client, doc_type=ClientIdentityDoc.RESIDENCE_PERMIT, file_path="test.pdf")
        doc.clean()

    def test_clean_natural_household_register(self):
        """自然人使用户口本应通过验证"""
        client = ClientFactory(client_type=Client.NATURAL)
        doc = ClientIdentityDoc(client=client, doc_type=ClientIdentityDoc.HOUSEHOLD_REGISTER, file_path="test.pdf")
        doc.clean()

    def test_clean_natural_invalid_doc_type(self):
        """自然人使用营业执照应抛出 ValidationError"""
        client = ClientFactory(client_type=Client.NATURAL)
        doc = ClientIdentityDoc(client=client, doc_type=ClientIdentityDoc.BUSINESS_LICENSE, file_path="test.pdf")
        with pytest.raises(ValidationError):
            doc.clean()

    def test_clean_legal_valid_doc_type(self):
        """法人使用营业执照应通过验证"""
        client = ClientFactory(client_type=Client.LEGAL)
        doc = ClientIdentityDoc(client=client, doc_type=ClientIdentityDoc.BUSINESS_LICENSE, file_path="test.pdf")
        doc.clean()

    def test_clean_legal_rep_id_card(self):
        """法人使用法定代表人身份证应通过验证"""
        client = ClientFactory(client_type=Client.LEGAL)
        doc = ClientIdentityDoc(client=client, doc_type=ClientIdentityDoc.LEGAL_REP_ID_CARD, file_path="test.pdf")
        doc.clean()

    def test_clean_legal_invalid_doc_type(self):
        """法人使用普通身份证应抛出 ValidationError"""
        client = ClientFactory(client_type=Client.LEGAL)
        doc = ClientIdentityDoc(client=client, doc_type=ClientIdentityDoc.ID_CARD, file_path="test.pdf")
        with pytest.raises(ValidationError):
            doc.clean()

    def test_clean_non_legal_org_valid(self):
        """非法人组织使用营业执照应通过验证"""
        client = ClientFactory(client_type=Client.NON_LEGAL_ORG)
        doc = ClientIdentityDoc(client=client, doc_type=ClientIdentityDoc.BUSINESS_LICENSE, file_path="test.pdf")
        doc.clean()

    def test_clean_non_legal_org_invalid(self):
        """非法人组织使用护照应抛出 ValidationError"""
        client = ClientFactory(client_type=Client.NON_LEGAL_ORG)
        doc = ClientIdentityDoc(client=client, doc_type=ClientIdentityDoc.PASSPORT, file_path="test.pdf")
        with pytest.raises(ValidationError):
            doc.clean()

    def test_doc_type_choices(self):
        choices = dict(ClientIdentityDoc.DOC_TYPE_CHOICES)
        assert choices["id_card"] == "身份证"
        assert choices["passport"] == "护照"
        assert choices["business_license"] == "营业执照"
        assert choices["legal_rep_id_card"] == "法定代表人/负责人身份证"
