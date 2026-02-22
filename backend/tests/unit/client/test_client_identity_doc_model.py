"""
ClientIdentityDoc 模型单元测试
"""

import pytest
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.client.models import Client, ClientIdentityDoc
from tests.factories import ClientFactory, ClientIdentityDocFactory


class TestClientIdentityDocModel(TestCase):
    """ClientIdentityDoc 模型测试"""

    def setUp(self):
        """测试设置"""
        self.client = ClientFactory()  # type: ignore[assignment]

    def test_doc_type_choices_excludes_legal_rep_certificate(self):
        """验证 DOC_TYPE_CHOICES 不包含 legal_rep_certificate"""
        doc_type_values = [choice[0] for choice in ClientIdentityDoc.DOC_TYPE_CHOICES]

        # 验证不包含 legal_rep_certificate
        self.assertNotIn("legal_rep_certificate", doc_type_values)

        # 验证包含其他预期的选项
        expected_types = [
            "id_card",
            "passport",
            "hk_macao_permit",
            "residence_permit",
            "household_register",
            "business_license",
            "legal_rep_id_card",
        ]
        for doc_type in expected_types:
            self.assertIn(doc_type, doc_type_values)

    def test_expiry_date_field_nullable(self):
        """验证 expiry_date 字段可为空"""
        # 创建不带到期日期的证件记录
        doc = ClientIdentityDocFactory(client=self.client, doc_type=ClientIdentityDoc.ID_CARD, expiry_date=None)

        # 验证可以保存
        doc.full_clean()  # type: ignore[attr-defined]
        doc.save()  # type: ignore[attr-defined]

        # 验证字段为空
        self.assertIsNone(doc.expiry_date)  # type: ignore[attr-defined]

    def test_expiry_date_field_accepts_date(self):
        """验证 expiry_date 字段接受日期值"""
        from datetime import date

        expiry_date = date(2030, 12, 31)
        doc = ClientIdentityDocFactory(client=self.client, doc_type=ClientIdentityDoc.ID_CARD, expiry_date=expiry_date)

        # 验证可以保存
        doc.full_clean()  # type: ignore[attr-defined]
        doc.save()  # type: ignore[attr-defined]

        # 验证日期值正确
        self.assertEqual(doc.expiry_date, expiry_date)  # type: ignore[attr-defined]

    def test_old_data_compatibility(self):
        """验证旧数据兼容性 - 现有记录不会因为模型变更而出错"""
        # 创建各种类型的证件记录，模拟旧数据
        # 为自然人创建自然人证件
        natural_client = ClientFactory(client_type=Client.NATURAL)
        natural_doc_types = [
            ClientIdentityDoc.ID_CARD,
            ClientIdentityDoc.PASSPORT,
        ]

        for doc_type in natural_doc_types:
            doc = ClientIdentityDocFactory(
                client=natural_client,
                doc_type=doc_type,
                expiry_date=None,  # 模拟旧数据没有到期日期
            )

            # 验证旧数据可以正常验证和保存
            doc.full_clean()  # type: ignore[attr-defined]
            doc.save()  # type: ignore[attr-defined]

            # 验证字符串表示正常
            str_repr = str(doc)
            self.assertIn(natural_client.name, str_repr)
            self.assertIn(doc_type, str_repr)

        # 为法人创建法人证件
        legal_client = ClientFactory(client_type=Client.LEGAL)
        legal_doc_types = [ClientIdentityDoc.BUSINESS_LICENSE, ClientIdentityDoc.LEGAL_REP_ID_CARD]

        for doc_type in legal_doc_types:
            doc = ClientIdentityDocFactory(
                client=legal_client,
                doc_type=doc_type,
                expiry_date=None,  # 模拟旧数据没有到期日期
            )

            # 验证旧数据可以正常验证和保存
            doc.full_clean()  # type: ignore[attr-defined]
            doc.save()  # type: ignore[attr-defined]

            # 验证字符串表示正常
            str_repr = str(doc)
            self.assertIn(legal_client.name, str_repr)
            self.assertIn(doc_type, str_repr)

    def test_natural_person_doc_type_validation(self):
        """验证自然人证件类型验证"""
        natural_client = ClientFactory(client_type=Client.NATURAL)

        # 自然人可用的证件类型
        valid_types = [
            ClientIdentityDoc.ID_CARD,
            ClientIdentityDoc.PASSPORT,
            ClientIdentityDoc.HK_MACAO_PERMIT,
            ClientIdentityDoc.RESIDENCE_PERMIT,
            ClientIdentityDoc.HOUSEHOLD_REGISTER,
        ]

        for doc_type in valid_types:
            doc = ClientIdentityDocFactory(client=natural_client, doc_type=doc_type)
            # 应该通过验证
            doc.full_clean()  # type: ignore[attr-defined]

    def test_legal_person_doc_type_validation(self):
        """验证法人证件类型验证"""
        legal_client = ClientFactory(client_type=Client.LEGAL)

        # 法人可用的证件类型（包括自然人证件和法人专用证件）
        valid_types = [
            ClientIdentityDoc.ID_CARD,  # 自然人证件也可用于法人
            ClientIdentityDoc.BUSINESS_LICENSE,
            ClientIdentityDoc.LEGAL_REP_ID_CARD,
        ]

        for doc_type in valid_types:
            doc = ClientIdentityDocFactory(client=legal_client, doc_type=doc_type)
            # 应该通过验证
            doc.full_clean()  # type: ignore[attr-defined]

    def test_media_url_method(self):
        """验证 media_url 方法"""
        doc = ClientIdentityDocFactory(client=self.client, file_path="client_identity_docs/test.jpg")

        # 验证 media_url 方法存在且可调用
        media_url = doc.media_url()  # type: ignore[attr-defined]

        # 如果有文件路径，应该返回 URL 字符串或 None
        self.assertTrue(isinstance(media_url, (str, type(None))))
