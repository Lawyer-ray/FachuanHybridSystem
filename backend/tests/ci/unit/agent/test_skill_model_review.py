"""模型层不变量：``status`` 与 ``review_status`` 正交、线上指针可空、归档仍占名。

这组用例只锁**模型契约**，不碰业务逻辑。它们存在的理由是两个字段一旦被混用
（比如有人在某个分支里写了 ``status = "pending"``），排查成本极高：``resolve``
只查 ``status=ACTIVE``，于是「待审」会表现成「这条技能凭空下线」，而界面上
显示的是「待审核中」——两边都看不出问题在哪。
"""

from __future__ import annotations

from typing import Any

import pytest
from django.db import IntegrityError, transaction

from apps.agent.models import AgentSkill, AgentSkillRevision
from apps.organization.models import LawFirm, Lawyer

TEST_PASSWORD = "x-test-12345678"  # pragma: allowlist secret


def _lawyer(username: str = "model-user") -> Lawyer:
    firm = LawFirm.objects.create(name="模型所")
    return Lawyer.objects.create_user(username=username, password=TEST_PASSWORD, law_firm=firm)


def _row(
    lawyer: Lawyer,
    name: str,
    *,
    status: str = AgentSkill.Status.ACTIVE,
    scope: str = AgentSkill.Scope.LAWYER,
    **extra: Any,
) -> AgentSkill:
    return AgentSkill.objects.create(
        scope=scope,
        lawyer=lawyer if scope == AgentSkill.Scope.LAWYER else None,
        name=name,
        title=name,
        description="描述",
        body="正文",
        status=status,
        created_by=lawyer,
        **extra,
    )


@pytest.mark.django_db
class TestReviewStatusOrthogonal:
    def test_status_choices_have_no_pending(self) -> None:
        """``status`` 只表示线上槽位，**不许**出现 ``pending``。"""
        values = {choice.value for choice in AgentSkill.Status}
        assert values == {"draft", "active", "archived"}
        assert "pending" not in values

    def test_review_status_defaults_to_none(self) -> None:
        skill = _row(_lawyer(), "default-review")
        assert skill.review_status == AgentSkill.ReviewStatus.NONE
        assert skill.review_note == ""
        assert skill.published_revision is None

    def test_review_status_values(self) -> None:
        assert {choice.value for choice in AgentSkill.ReviewStatus} == {"none", "pending", "rejected"}

    def test_active_with_pending_review_is_legal(self) -> None:
        """双轨的核心状态组合：线上仍 active、修订流 pending。"""
        skill = _row(_lawyer(), "two-track")
        skill.review_status = AgentSkill.ReviewStatus.PENDING
        skill.save(update_fields=["review_status"])
        skill.refresh_from_db()
        assert skill.status == AgentSkill.Status.ACTIVE
        assert skill.review_status == AgentSkill.ReviewStatus.PENDING


@pytest.mark.django_db
class TestPublishedRevision:
    def test_published_revision_set_null_on_delete(self) -> None:
        lawyer = _lawyer("setnull")
        skill = _row(lawyer, "with-revision")
        revision = AgentSkillRevision.objects.create(
            skill=skill,
            version=1,
            title=skill.title,
            description=skill.description,
            body=skill.body,
            status=skill.status,
        )
        skill.published_revision = revision
        skill.save(update_fields=["published_revision"])

        revision.delete()
        skill.refresh_from_db()
        # SET_NULL 而不是 CASCADE：删一条快照不该连带删技能本体（那会丢掉整个审计链）
        assert skill.published_revision is None
        assert AgentSkill.objects.filter(pk=skill.pk).exists()

    def test_has_unpublished_changes_reads_version_gap(self) -> None:
        lawyer = _lawyer("version-gap")
        skill = _row(lawyer, "gap")
        revision = AgentSkillRevision.objects.create(
            skill=skill, version=1, title="旧", description="旧", body="旧", status=skill.status
        )
        skill.published_revision = revision
        skill.save(update_fields=["published_revision"])
        assert skill.has_unpublished_changes is False

        skill.version = 2
        skill.save(update_fields=["version"])
        skill.refresh_from_db()
        assert skill.has_unpublished_changes is True

    def test_personal_skill_has_no_unpublished_state(self) -> None:
        skill = _row(_lawyer("personal-none"), "personal")
        assert skill.published_revision is None
        assert skill.has_unpublished_changes is False

    def test_is_shared_flag(self) -> None:
        firm = LawFirm.objects.create(name="共享所")
        lawyer = Lawyer.objects.create_user(username="shared-flag", password=TEST_PASSWORD, law_firm=firm)
        personal = _row(lawyer, "p")
        assert personal.is_shared is False
        shared = AgentSkill.objects.create(
            scope=AgentSkill.Scope.LAW_FIRM,
            law_firm=firm,
            name="f",
            title="f",
            description="d",
            body="b",
            status=AgentSkill.Status.DRAFT,
            created_by=lawyer,
        )
        assert shared.is_shared is True


@pytest.mark.django_db
class TestUniqueConstraints:
    def test_archived_still_occupies_name(self) -> None:
        """归档占名：数据库约束包含 ARCHIVED，校验口径必须与之一致。

        否则 ``/skills/validate`` 说「可以用」、``POST`` 撞 409——用户在两个界面
        看到互相矛盾的答案，且没有任何一处能解释清楚。
        """
        lawyer = _lawyer("archive-name")
        _row(lawyer, "taken", status=AgentSkill.Status.ARCHIVED)
        with pytest.raises(IntegrityError), transaction.atomic():
            _row(lawyer, "taken")

    def test_scope_owner_check_constraint(self) -> None:
        """``scope`` 与归属字段必须自洽：lawyer 作用域不得同时挂 team。"""
        lawyer = _lawyer("owner-check")
        firm = LawFirm.objects.create(name="约束所")
        from apps.organization.models import Team

        team = Team.objects.create(law_firm=firm, name="组", team_type="lawyer")
        with pytest.raises(IntegrityError), transaction.atomic():
            AgentSkill.objects.create(
                scope=AgentSkill.Scope.LAWYER,
                lawyer=lawyer,
                team=team,
                name="both",
                title="both",
                description="d",
                body="b",
            )
