"""项目笔记：A 律师的判断怎么让同团队的 B 律师用上。

覆盖四件事（每一件都是「共享上下文」真正的坑）：

1. **可见性是同律师团队**，不是「点名共享」也不是「全所可见」——跨团队串号
   在法律行业是保密事故；
2. **项目是权限泡、案件是注入粒度**：挂在项目（合同）上的笔记在本项目所有
   案件的会话里可见，挂在某案件上的只在该案会话里展开；
3. **判断与事实必须分块**：模型写的判断未经人确认，注入时不能和「已确认事实」
   混在一起，否则推测会被当前提逐轮放大；
4. **快照按锚点隔离**：A 案的快照绝不能发给 B 案（这是最容易写错、也最贵的
   bug），且写入后要立刻可见（版本号失效，而不是等 TTL）。
"""

from __future__ import annotations

import pytest

from apps.agent.models import AgentMemory
from apps.agent.services import memory_service
from apps.organization.models import LawFirm, Lawyer, Team, TeamType

TEST_PASSWORD = "x-test-12345678"  # pragma: allowlist secret

CONTRACT_ID = 701
OTHER_CONTRACT_ID = 702
CASE_ID = 9001


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture()
def firm() -> LawFirm:
    return LawFirm.objects.create(name="甲律所")


@pytest.fixture()
def other_firm() -> LawFirm:
    return LawFirm.objects.create(name="乙律所")


@pytest.fixture()
def team(firm: LawFirm) -> Team:
    return Team.objects.create(name="争议解决组", team_type=TeamType.LAWYER, law_firm=firm)


@pytest.fixture()
def lawyer(firm: LawFirm, team: Team) -> Lawyer:
    user = Lawyer.objects.create_user(username="lawyer_a", real_name="甲律师", password=TEST_PASSWORD, law_firm=firm)
    user.lawyer_teams.add(team)
    return user


@pytest.fixture()
def colleague(firm: LawFirm, team: Team) -> Lawyer:
    user = Lawyer.objects.create_user(username="lawyer_b", real_name="乙律师", password=TEST_PASSWORD, law_firm=firm)
    user.lawyer_teams.add(team)
    return user


@pytest.fixture()
def outsider(other_firm: LawFirm) -> Lawyer:
    return Lawyer.objects.create_user(username="lawyer_c", real_name="丙律师", password=TEST_PASSWORD, law_firm=other_firm)


class TestWriteNote:
    @pytest.mark.django_db
    def test_requires_anchor(self, lawyer: Lawyer) -> None:
        with pytest.raises(ValueError, match="必须挂到项目"):
            memory_service.create_note(lawyer, content="对方已同意分期")

    @pytest.mark.django_db
    def test_written_note_is_active_but_unconfirmed(self, lawyer: Lawyer) -> None:
        note = memory_service.create_note(lawyer, content="法官倾向调解", contract_id=CONTRACT_ID)
        assert note.status == AgentMemory.Status.ACTIVE
        assert note.contract_id == CONTRACT_ID
        assert note.confirmed_at is None
        assert note.lawyer_id == lawyer.pk

    @pytest.mark.django_db
    def test_case_level_note_keeps_case_anchor(self, lawyer: Lawyer) -> None:
        note = memory_service.create_note(lawyer, content="本案已排期 3 月 12 日", contract_id=CONTRACT_ID, case_id=CASE_ID)
        assert note.case_id == CASE_ID
        assert note.contract_id == CONTRACT_ID

    @pytest.mark.django_db
    def test_too_long_rejected(self, lawyer: Lawyer) -> None:
        with pytest.raises(ValueError, match="过长"):
            memory_service.create_note(lawyer, content="x" * (memory_service.NOTE_MAX_CHARS + 1), contract_id=CONTRACT_ID)


class TestVisibility:
    @pytest.mark.django_db
    def test_teammate_sees_note(self, lawyer: Lawyer, colleague: Lawyer) -> None:
        memory_service.create_note(lawyer, content="对方已同意分期", contract_id=CONTRACT_ID)
        seen = memory_service.anchor_visible_queryset(colleague, contract_id=CONTRACT_ID, case_id=None)
        assert [m.content for m in seen] == ["对方已同意分期"]

    @pytest.mark.django_db
    def test_outsider_cannot_see_note(self, lawyer: Lawyer, outsider: Lawyer) -> None:
        memory_service.create_note(lawyer, content="和解底线 80 万", contract_id=CONTRACT_ID)
        seen = memory_service.anchor_visible_queryset(outsider, contract_id=CONTRACT_ID, case_id=None)
        assert list(seen) == []

    @pytest.mark.django_db
    def test_no_anchor_returns_nothing(self, lawyer: Lawyer) -> None:
        memory_service.create_note(lawyer, content="任意", contract_id=CONTRACT_ID)
        assert list(memory_service.anchor_visible_queryset(lawyer, contract_id=None, case_id=None)) == []

    @pytest.mark.django_db
    def test_sibling_case_note_not_expanded(self, lawyer: Lawyer, colleague: Lawyer) -> None:
        # 挂在 9001 案上的笔记，在 9002 案的会话里不展开（批量诉讼不串味）
        memory_service.create_note(lawyer, content="本案证人反复", contract_id=CONTRACT_ID, case_id=CASE_ID)
        seen = memory_service.anchor_visible_queryset(colleague, contract_id=None, case_id=CASE_ID + 1)
        assert list(seen) == []


class TestSupersede:
    @pytest.mark.django_db
    def test_superseded_note_stops_being_injected_but_stays_in_db(self, lawyer: Lawyer) -> None:
        old = memory_service.create_note(lawyer, content="对方要求三个月内付清", contract_id=CONTRACT_ID)
        new = memory_service.create_note(
            lawyer,
            content="对方已同意六个月内分期",
            contract_id=CONTRACT_ID,
            supersede_id=str(old.pk),
        )
        seen = list(memory_service.anchor_visible_queryset(lawyer, contract_id=CONTRACT_ID, case_id=None))
        assert [m.pk for m in seen] == [new.pk]
        assert AgentMemory.objects.filter(pk=old.pk).exists()


class TestConfirm:
    @pytest.mark.django_db
    def test_teammate_can_confirm_and_rewrite(self, lawyer: Lawyer, colleague: Lawyer) -> None:
        note = memory_service.create_note(lawyer, content="大概能判三年", contract_id=CONTRACT_ID)
        confirmed = memory_service.confirm_note(colleague, str(note.pk), content="已确认量刑区间为三年")
        assert confirmed.confirmed_at is not None
        assert confirmed.confirmed_by_id == colleague.pk
        assert confirmed.content == "已确认量刑区间为三年"

    @pytest.mark.django_db
    def test_outsider_cannot_confirm(self, lawyer: Lawyer, outsider: Lawyer) -> None:
        note = memory_service.create_note(lawyer, content="内部判断", contract_id=CONTRACT_ID)
        with pytest.raises(ValueError, match="无权访问"):
            memory_service.confirm_note(outsider, str(note.pk))


class TestSnapshot:
    @pytest.mark.django_db
    def test_judgment_block_marks_author_and_warns(self, lawyer: Lawyer, colleague: Lawyer) -> None:
        memory_service.create_note(lawyer, content="法官倾向调解", contract_id=CONTRACT_ID)
        snapshot = memory_service.build_snapshot(colleague, contract_id=CONTRACT_ID)
        assert "本项目同事的判断" in snapshot
        assert "未经确认" in snapshot
        assert "甲律师" in snapshot
        assert "法官倾向调解" in snapshot

    @pytest.mark.django_db
    def test_confirmed_note_renders_in_fact_block(self, lawyer: Lawyer) -> None:
        note = memory_service.create_note(lawyer, content="对方已同意分期", contract_id=CONTRACT_ID)
        memory_service.confirm_note(lawyer, str(note.pk))
        snapshot = memory_service.build_snapshot(lawyer, contract_id=CONTRACT_ID)
        assert "本项目已确认的事实" in snapshot
        assert "随时" not in snapshot  # 断言没有混进其他块
        fact_pos = snapshot.index("本项目已确认的事实")
        judge_pos = snapshot.find("本项目同事的判断")
        assert judge_pos == -1 or fact_pos < judge_pos

    @pytest.mark.django_db
    def test_snapshot_isolated_by_anchor(self, lawyer: Lawyer) -> None:
        memory_service.create_note(lawyer, content="A 项目专属判断", contract_id=CONTRACT_ID)
        other = memory_service.build_snapshot(lawyer, contract_id=OTHER_CONTRACT_ID)
        assert "A 项目专属判断" not in other
        own = memory_service.build_snapshot(lawyer, contract_id=CONTRACT_ID)
        assert "A 项目专属判断" in own

    @pytest.mark.django_db
    def test_no_anchor_keeps_old_behaviour(self, lawyer: Lawyer) -> None:
        memory_service.create_note(lawyer, content="只属于项目", contract_id=CONTRACT_ID)
        snapshot = memory_service.build_snapshot(lawyer)
        assert "只属于项目" not in snapshot

    @pytest.mark.django_db
    def test_new_note_visible_immediately(self, lawyer: Lawyer) -> None:
        first = memory_service.build_snapshot(lawyer, contract_id=CONTRACT_ID)
        assert "刚写的判断" not in first
        memory_service.create_note(lawyer, content="刚写的判断", contract_id=CONTRACT_ID)
        second = memory_service.build_snapshot(lawyer, contract_id=CONTRACT_ID)
        assert "刚写的判断" in second

    @pytest.mark.django_db
    def test_snapshot_is_byte_stable_without_writes(self, lawyer: Lawyer) -> None:
        memory_service.create_note(lawyer, content="判断一条", contract_id=CONTRACT_ID)
        memory_service.create_note(lawyer, content="判断二条", contract_id=CONTRACT_ID)
        first = memory_service.build_snapshot(lawyer, contract_id=CONTRACT_ID)
        second = memory_service.build_snapshot(lawyer, contract_id=CONTRACT_ID)
        assert first == second
