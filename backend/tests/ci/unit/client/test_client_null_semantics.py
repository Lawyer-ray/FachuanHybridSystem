"""Client 双空态与导入丢失语义回归测试。

覆盖三个行为锚点：
- id_number（unique）save 钩子：空串必须归一为 NULL（'' 会与存量互撞唯一约束）
- resolve_with_attachments 的 PropertyClue 查重键含 content：同类型多条线索
  （如一个客户的多个银行账户）重导入不得被静默吞并
- ClientIdentityDoc.file_path（unique 约束键）：待上传占位行必须存 NULL，
  admin inline 一次保存多个新证件行不得互撞 uniq_clientidentitydoc_client_file_path
"""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from apps.client.admin.client_admin import ClientIdentityDocInline
from apps.client.models import Client, ClientIdentityDoc, PropertyClue
from apps.client.services.client_resolve_service import ClientResolveService
from apps.testing.factories import ClientFactory

User = get_user_model()


@pytest.mark.django_db
class TestIdNumberSaveHook:
    def test_empty_string_normalized_to_none(self):
        c = ClientFactory(client_type="natural", id_number="")
        c.refresh_from_db()
        assert c.id_number is None

    def test_two_empty_id_numbers_coexist(self):
        """两个未填证件号的客户不撞唯一约束（多 NULL 共存）。"""
        ClientFactory(client_type="natural", id_number="")
        ClientFactory(client_type="natural", id_number="")  # 不应抛 IntegrityError
        assert Client.objects.filter(id_number__isnull=True).count() == 2

    def test_real_value_preserved(self):
        c = ClientFactory(client_type="natural", id_number="91330100MA27X8989X")
        c.refresh_from_db()
        assert c.id_number == "91330100MA27X8989X"


@pytest.mark.django_db
class TestResolvePropertyClueContentDedup:
    BANK_CLUES = {
        "name": "多账户客户",
        "client_type": "legal",
        "id_number": "91330100TEST0001X",
        "legal_representative": "代表",
        "property_clues": [
            {"clue_type": "bank", "content": "中国银行账户 6222 0001"},
            {"clue_type": "bank", "content": "建设银行账户 6217 0002"},
        ],
    }

    def test_same_type_multiple_clues_all_created(self):
        """同一客户同类型多条线索（多银行账户）必须全部落库。"""
        svc = ClientResolveService()
        client = svc.resolve_with_attachments(dict(self.BANK_CLUES))
        assert PropertyClue.objects.filter(client=client, clue_type="bank").count() == 2

    def test_reimport_is_idempotent(self):
        """重导入同一份数据不产生重复线索（content 进查重键后幂等）。"""
        svc = ClientResolveService()
        svc.resolve_with_attachments(dict(self.BANK_CLUES))
        svc.resolve_with_attachments(dict(self.BANK_CLUES))
        assert PropertyClue.objects.filter(clue_type="bank").count() == 2

    def test_identity_docs_idempotent(self):
        data = dict(
            self.BANK_CLUES,
            identity_docs=[
                {"file_path": "identity_docs/a.pdf", "doc_type": "business_license"},
            ],
        )
        svc = ClientResolveService()
        svc.resolve_with_attachments(dict(data))
        client = svc.resolve_with_attachments(dict(data))
        from apps.client.models import ClientIdentityDoc

        assert ClientIdentityDoc.objects.filter(client=client).count() == 1


def _make_admin_request() -> Any:
    from django.test import RequestFactory

    request = RequestFactory().get("/admin/")
    request.user = User(is_superuser=True, is_staff=True)
    return request


@pytest.mark.django_db
class TestIdentityDocFilePathNullSemantics:
    """证件待上传占位行的 NULL 语义（2026-10-09 admin 双上传 IntegrityError 回归）。"""

    def test_two_pending_docs_coexist(self):
        """同一客户两个待上传占位行（file_path 空）不撞唯一约束。"""
        client = ClientFactory(client_type="legal")
        ClientIdentityDoc.objects.create(client=client, doc_type="business_license")
        ClientIdentityDoc.objects.create(client=client, doc_type="legal_rep_id_card")  # 不应抛 IntegrityError
        assert ClientIdentityDoc.objects.filter(client=client, file_path__isnull=True).count() == 2

    def test_empty_string_normalized_to_none(self):
        client = ClientFactory(client_type="legal")
        doc = ClientIdentityDoc.objects.create(client=client, doc_type="id_card", file_path="")
        doc.refresh_from_db()
        assert doc.file_path is None

    def test_real_path_unique_still_enforced(self):
        """约束只对占位行放行：同客户同真实路径仍须被拦下。"""
        client = ClientFactory(client_type="legal")
        ClientIdentityDoc.objects.create(client=client, doc_type="business_license", file_path="client_docs/a.pdf")
        with pytest.raises(IntegrityError):
            ClientIdentityDoc.objects.create(client=client, doc_type="legal_rep_id_card", file_path="client_docs/a.pdf")

    def test_admin_inline_two_new_rows_in_one_save(self):
        """复现用户实爆路径：admin inline 一次保存新增两个证件行。

        save_formset 先 formset.save() 整批 INSERT（此时 file_path 尚为空占位）、
        文件落盘回填在后；旧行为第二行 INSERT 即撞 uniq_..._client_file_path。
        """
        from django.forms.models import inlineformset_factory

        client = ClientFactory(client_type="legal")
        inline = ClientIdentityDocInline(Client, AdminSite())
        formset_cls = inline.get_formset(_make_admin_request(), obj=client)
        prefix = formset_cls.get_default_prefix()

        data = {
            f"{prefix}-TOTAL_FORMS": "2",
            f"{prefix}-INITIAL_FORMS": "0",
            f"{prefix}-MIN_NUM_FORMS": "0",
            f"{prefix}-MAX_NUM_FORMS": "1000",
            f"{prefix}-0-doc_type": "business_license",
            f"{prefix}-1-doc_type": "legal_rep_id_card",
        }
        formset = formset_cls(data, instance=client)
        assert formset.is_valid(), formset.errors
        formset.save()

        assert ClientIdentityDoc.objects.filter(client=client).count() == 2
        assert ClientIdentityDoc.objects.filter(client=client, file_path__isnull=True).count() == 2
