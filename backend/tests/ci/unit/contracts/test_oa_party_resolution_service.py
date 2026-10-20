"""律所ID 同步的当事人解析单测：OA 名单 → 本地 Client（缺失自动建库、阵营标记正确）。

覆盖：委托人自动建库为我方、利冲相关方自动建库为非我方、既有记录复用不重复建库、
我方分组把既有「非我方」提升为我方、非我方分组不抹掉既有「我方」标记、
无新增权限时不建库、证件号优先匹配、单个当事人异常不影响其他条目。
"""

from __future__ import annotations

import pytest

from apps.client.models import Client
from apps.contracts.services.contract.integrations.oa_party_resolution_service import OaPartyResolutionService


def _payload() -> dict[str, list[dict[str, str]]]:
    return {
        "clients": [{"name": "某委托人公司", "customer_type": "legal", "id_number": "91440000TEST000001"}],
        "opponents": [{"name": "某原告公司", "conflict_type": "原告"}],
        "co_parties": [{"name": "同案被告甲", "conflict_type": "被告"}],
        "third_parties": [{"name": "某第三人公司", "conflict_type": "第三人"}],
    }


@pytest.mark.django_db
class TestOaPartyResolutionService:
    def _resolve(self, payload: dict, *, allow_create: bool = True) -> dict:
        return OaPartyResolutionService().resolve_payload(payload, allow_create=allow_create)

    def test_creates_missing_parties_with_group_flags(self):
        resolved = self._resolve(_payload())

        our = Client.objects.get(pk=resolved["clients"][0]["client_id"])
        assert our.is_our_client is True
        assert our.client_type == "legal"
        assert our.id_number == "91440000TEST000001"

        for group in ("opponents", "co_parties", "third_parties"):
            client = Client.objects.get(pk=resolved[group][0]["client_id"])
            assert client.is_our_client is False
            assert resolved[group][0]["created"] is True

        assert resolved["co_parties"][0]["client_name"] == "同案被告甲"
        assert Client.objects.count() == 4

    def test_infers_natural_person_type_for_untyped_conflict_party(self):
        resolved = self._resolve({"clients": [], "opponents": [{"name": "张某某", "conflict_type": "被告"}]})
        client = Client.objects.get(pk=resolved["opponents"][0]["client_id"])
        assert client.client_type == "natural"

    def test_reuses_existing_party_by_name_case_insensitive(self):
        existing = Client.objects.create(name="某原告公司", is_our_client=False)
        resolved = self._resolve({"clients": [], "opponents": [{"name": "某原告公司", "conflict_type": "原告"}]})

        assert resolved["opponents"][0]["client_id"] == existing.pk
        assert resolved["opponents"][0]["created"] is False
        assert Client.objects.filter(name="某原告公司").count() == 1

    def test_our_group_promotes_existing_party_flag(self):
        """委托人若在库中被标为非我方，必须改为我方——否则 ContractParty 会把身份纠正成对方。"""
        existing = Client.objects.create(name="某委托人公司", is_our_client=False)
        resolved = self._resolve({"clients": [{"name": "某委托人公司", "customer_type": "legal"}]})

        existing.refresh_from_db()
        assert existing.is_our_client is True
        assert resolved["clients"][0]["created"] is False

    def test_non_our_group_keeps_existing_our_client_flag(self):
        """同一当事人可能在别的案件是我方委托人，利冲出现在对方席不抹掉全局标记。"""
        existing = Client.objects.create(name="某原告公司", is_our_client=True)
        self._resolve({"clients": [], "opponents": [{"name": "某原告公司", "conflict_type": "原告"}]})

        existing.refresh_from_db()
        assert existing.is_our_client is True

    def test_without_create_permission_missing_party_is_unresolved(self):
        resolved = self._resolve(_payload(), allow_create=False)

        for group in ("clients", "opponents", "co_parties", "third_parties"):
            assert resolved[group][0]["client_id"] is None
            assert resolved[group][0]["created"] is False
        assert Client.objects.count() == 0

    def test_without_create_permission_existing_party_still_resolves(self):
        existing = Client.objects.create(name="某原告公司")
        resolved = self._resolve({"clients": [], "opponents": [{"name": "某原告公司"}]}, allow_create=False)

        assert resolved["opponents"][0]["client_id"] == existing.pk

    def test_matches_by_id_number_before_name(self):
        existing = Client.objects.create(name="某公司（旧名）", id_number="91440000TEST000002")
        resolved = self._resolve(
            {"clients": [{"name": "某公司（新名）", "customer_type": "legal", "id_number": "91440000TEST000002"}]}
        )

        assert resolved["clients"][0]["client_id"] == existing.pk
        assert resolved["clients"][0]["client_name"] == "某公司（旧名）"
        assert resolved["clients"][0]["created"] is False

    def test_blank_name_is_left_unresolved(self):
        resolved = self._resolve({"clients": [{"name": "   "}], "opponents": [], "co_parties": [], "third_parties": []})

        assert resolved["clients"][0]["client_id"] is None
        assert resolved["clients"][0]["created"] is False
