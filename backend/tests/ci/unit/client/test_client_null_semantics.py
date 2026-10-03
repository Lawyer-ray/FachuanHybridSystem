"""Client 双空态与导入丢失语义回归测试。

覆盖两个行为锚点：
- id_number（unique）save 钩子：空串必须归一为 NULL（'' 会与存量互撞唯一约束）
- resolve_with_attachments 的 PropertyClue 查重键含 content：同类型多条线索
  （如一个客户的多个银行账户）重导入不得被静默吞并
"""

from __future__ import annotations

import pytest

from apps.client.models import Client, PropertyClue
from apps.client.services.client_resolve_service import ClientResolveService
from apps.testing.factories import ClientFactory


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
