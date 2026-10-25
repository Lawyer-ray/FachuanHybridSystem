"""Agent 记忆（个人 / 团队 / 律所三级）核心行为。

覆盖三件事，对应三个最容易出错的地方：

1. **权限边界**：``visible_queryset`` 是唯一入口。跨团队、跨律所的串号是
   法律行业的保密事故，不是体验问题，必须有断言守着。
2. **策展闸门**：团队/律所记忆只能经 ``promote_memory`` 产生，且强制改写 +
   PII 拦截。原样提升等于把具体案件事实搬进全所可见层级。
3. **注入渲染**：快照按层限额、超长条目跳过、``pending`` 不进上下文。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.agent.models import AgentMemory, content_hash_of
from apps.agent.services import memory_service
from apps.organization.models import LawFirm, Lawyer, Team, TeamType

TEST_PASSWORD = "x-test-12345678"  # pragma: allowlist secret


@pytest.fixture()
def firm() -> LawFirm:
    return LawFirm.objects.create(name="甲律所")


@pytest.fixture()
def other_firm() -> LawFirm:
    return LawFirm.objects.create(name="乙律所")


@pytest.fixture()
def team(firm: LawFirm) -> Team:
    return Team.objects.create(name="劳动争议组", team_type=TeamType.LAWYER, law_firm=firm)


@pytest.fixture()
def lawyer(firm: LawFirm, team: Team) -> Lawyer:
    user = Lawyer.objects.create_user(username="lawyer_a", password=TEST_PASSWORD, law_firm=firm)
    user.lawyer_teams.add(team)
    return user


@pytest.fixture()
def colleague(firm: LawFirm, team: Team) -> Lawyer:
    user = Lawyer.objects.create_user(username="lawyer_b", password=TEST_PASSWORD, law_firm=firm)
    user.lawyer_teams.add(team)
    return user


@pytest.fixture()
def outsider(other_firm: LawFirm) -> Lawyer:
    return Lawyer.objects.create_user(username="lawyer_c", password=TEST_PASSWORD, law_firm=other_firm)


def _memory(lawyer: Lawyer, content: str, **kwargs: object) -> AgentMemory:
    defaults: dict[str, object] = {
        "scope": AgentMemory.Scope.LAWYER,
        "lawyer": lawyer,
        "kind": AgentMemory.Kind.PREFERENCE,
        "content": content,
        "status": AgentMemory.Status.ACTIVE,
        "created_by": lawyer,
    }
    defaults.update(kwargs)
    return AgentMemory.objects.create(**defaults)


@pytest.mark.django_db
class TestContentHash:
    def test_normalizes_whitespace(self) -> None:
        assert content_hash_of("文书 先给结论") == content_hash_of("  文书 先给结论  ")

    def test_differs_on_content(self) -> None:
        assert content_hash_of("A") != content_hash_of("B")


@pytest.mark.django_db
class TestVisibleScope:
    def test_same_team_member_sees_team_memory(self, lawyer: Lawyer, colleague: Lawyer, team: Team) -> None:
        team_memory = AgentMemory.objects.create(
            scope=AgentMemory.Scope.TEAM,
            team=team,
            kind=AgentMemory.Kind.PROCEDURE,
            content="法院函件控制在 800 字内",
            status=AgentMemory.Status.ACTIVE,
            created_by=lawyer,
        )
        assert memory_service.visible_queryset(colleague).filter(pk=team_memory.pk).exists()

    def test_other_firm_cannot_see(self, lawyer: Lawyer, outsider: Lawyer, team: Team) -> None:
        team_memory = AgentMemory.objects.create(
            scope=AgentMemory.Scope.TEAM,
            team=team,
            kind=AgentMemory.Kind.PROCEDURE,
            content="法院函件控制在 800 字内",
            status=AgentMemory.Status.ACTIVE,
            created_by=lawyer,
        )
        assert not memory_service.visible_queryset(outsider).filter(pk=team_memory.pk).exists()

    def test_personal_memory_is_private(self, lawyer: Lawyer, colleague: Lawyer) -> None:
        mine = _memory(lawyer, "我习惯先看结论")
        assert not memory_service.visible_queryset(colleague).filter(pk=mine.pk).exists()

    def test_pending_memory_not_visible_by_default(self, lawyer: Lawyer) -> None:
        pending = _memory(lawyer, "可能是偏好", status=AgentMemory.Status.PENDING)
        assert not memory_service.visible_queryset(lawyer).filter(pk=pending.pk).exists()


@pytest.mark.django_db
class TestCreateMemory:
    def test_personal_memory_active_by_default(self, lawyer: Lawyer) -> None:
        memory = memory_service.create_memory(lawyer, content="文书先给结论再给理由", kind=AgentMemory.Kind.PREFERENCE)
        assert memory.status == AgentMemory.Status.ACTIVE
        assert memory.scope == AgentMemory.Scope.LAWYER

    def test_duplicate_content_merges_not_duplicates(self, lawyer: Lawyer) -> None:
        first = memory_service.create_memory(lawyer, content="文书先给结论")
        second = memory_service.create_memory(lawyer, content="  文书先给结论  ")
        assert first.pk == second.pk
        assert AgentMemory.objects.filter(lawyer=lawyer).count() == 1

    def test_rejects_empty(self, lawyer: Lawyer) -> None:
        with pytest.raises(ValueError):
            memory_service.create_memory(lawyer, content="   ")

    def test_rejects_team_scope(self, lawyer: Lawyer) -> None:
        """团队/律所层只能经策展提升，不能直接写。"""
        with pytest.raises(ValueError, match="策展"):
            memory_service.create_memory(lawyer, content="x", scope=AgentMemory.Scope.TEAM)


@pytest.mark.django_db
class TestPromotion:
    def _promote(
        self,
        lawyer: Lawyer,
        sources: list[AgentMemory],
        *,
        content: str,
        kind: str = AgentMemory.Kind.PROCEDURE,
        scope: str = AgentMemory.Scope.TEAM,
        team: Team | None = None,
    ) -> AgentMemory:
        return memory_service.promote_memory(
            lawyer,
            source_ids=[str(s.pk) for s in sources],
            content=content,
            kind=kind,
            scope=scope,
            team_id=team.pk if team else None,
        )

    def test_promote_team_memory(self, lawyer: Lawyer, team: Team) -> None:
        a = _memory(lawyer, "回复法院函件不要超过 800 字", kind=AgentMemory.Kind.PROCEDURE)
        promoted = self._promote(lawyer, [a], content="回复法院函件控制在 800 字以内", team=team)
        assert promoted.scope == AgentMemory.Scope.TEAM
        assert promoted.team_id == team.pk
        assert promoted.status == AgentMemory.Status.ACTIVE
        assert list(promoted.promoted_from.all()) == [a]

    def test_rejects_verbatim_promotion(self, lawyer: Lawyer, team: Team) -> None:
        """强制改写闸门：原样提升等于把个人内容搬进全所可见层。"""
        source = _memory(lawyer, "回复法院函件不要超过 800 字")
        with pytest.raises(ValueError, match="原样提升"):
            self._promote(lawyer, [source], content="回复法院函件不要超过 800 字", team=team)

    def test_rejects_pii_in_promoted_content(self, lawyer: Lawyer, team: Team) -> None:
        source = _memory(lawyer, "某公司案件有分期方案")
        with pytest.raises(ValueError, match="敏感信息"):
            self._promote(
                lawyer,
                [source],
                content="客户手机 13800138000 的案子都可分期",  # privacy-allow PII 检测器自身的测试输入
                team=team,
            )

    def test_law_firm_rejects_fact_kind(self, lawyer: Lawyer) -> None:
        """律所层只接受惯例/偏好——具体事实进律所层没有正当理由。

        注意：提升到律所层要求 ``is_admin``，所以这里先把该律师设为管理员，
        否则会先撞上权限闸门而不是类型闸门。
        """
        lawyer.is_admin = True
        lawyer.save(update_fields=["is_admin"])
        source = _memory(lawyer, "某案的结论")
        with pytest.raises(ValueError, match="惯例"):
            self._promote(
                lawyer,
                [source],
                content="全所统一在立案前做冲突检索",
                kind=AgentMemory.Kind.FACT,
                scope=AgentMemory.Scope.LAW_FIRM,
            )

    def test_non_admin_cannot_promote_to_law_firm(self, lawyer: Lawyer) -> None:
        """非法所管理员提升到律所层必须被权限闸门拦住。"""
        source = _memory(lawyer, "某条惯例")
        with pytest.raises(ValueError, match="无权"):
            self._promote(
                lawyer,
                [source],
                content="全所统一在立案前做冲突检索",
                scope=AgentMemory.Scope.LAW_FIRM,
            )

    def test_non_member_cannot_promote_to_team(self, outsider: Lawyer, team: Team) -> None:
        with pytest.raises(ValueError, match="无权"):
            memory_service.promote_memory(
                outsider,
                source_ids=[],
                content="x",
                kind=AgentMemory.Kind.PROCEDURE,
                scope=AgentMemory.Scope.TEAM,
                team_id=team.pk,
            )


@pytest.mark.django_db
class TestScanPii:
    @pytest.mark.parametrize(
        "content",
        [
            "客户手机 13800138000",  # privacy-allow PII 检测器自身的测试输入
            "身份证 110101199001011234",  # privacy-allow PII 检测器自身的测试输入
            "案号（2024）京0105民初1234号",  # privacy-allow PII 检测器自身的测试输入
            "王某某诉北京某某科技有限公司",
        ],
    )
    def test_detects(self, content: str) -> None:
        assert memory_service.scan_pii_risk(content)

    def test_clean_content_passes(self) -> None:
        assert memory_service.scan_pii_risk("回复法院函件控制在 800 字以内") == []

    def test_anonymized_passes(self) -> None:
        """「王某诉某公司」是安全的匿名化写法。"""
        assert memory_service.scan_pii_risk("劳动争议案件客户普遍接受分期") == []


@pytest.mark.django_db
class TestSnapshot:
    def test_snapshot_contains_memory(self, lawyer: Lawyer) -> None:
        _memory(lawyer, "文书先给结论再给理由", kind=AgentMemory.Kind.PREFERENCE)
        snapshot = memory_service.build_snapshot(lawyer, refresh=True, refresh_reason="test")
        assert "文书先给结论再给理由" in snapshot
        assert "个人记忆" in snapshot

    def test_pending_excluded_from_snapshot(self, lawyer: Lawyer) -> None:
        _memory(lawyer, "未确认的推测", status=AgentMemory.Status.PENDING)
        snapshot = memory_service.build_snapshot(lawyer, refresh=True, refresh_reason="test")
        assert "未确认的推测" not in snapshot

    def test_oversized_entry_skipped(self, lawyer: Lawyer) -> None:
        """超长条目意味着抽取失败（把整段对话当一条记忆），不应注入。"""
        long_text = "很长的内容" * 100
        _memory(lawyer, long_text)
        snapshot = memory_service.build_snapshot(lawyer, refresh=True, refresh_reason="test")
        assert long_text not in snapshot

    def test_empty_snapshot_is_empty_string(self, lawyer: Lawyer) -> None:
        assert memory_service.build_snapshot(lawyer, refresh=True, refresh_reason="test") == ""

    def test_cached_snapshot_is_byte_stable(self, lawyer: Lawyer) -> None:
        """快照缓存是 prompt cache 命中的前提：同参数两次调用必须逐字节相同。"""
        _memory(lawyer, "偏好一")
        first = memory_service.build_snapshot(lawyer, refresh=True, refresh_reason="t")
        second = memory_service.build_snapshot(lawyer)
        assert first == second


@pytest.mark.django_db
class TestForgetRestore:
    def test_soft_delete_then_restore(self, lawyer: Lawyer) -> None:
        memory = _memory(lawyer, "待删的偏好")
        memory_service.forget_memory(lawyer, str(memory.pk))
        memory.refresh_from_db()
        assert memory.status == AgentMemory.Status.DELETED
        memory_service.restore_memory(lawyer, str(memory.pk))
        memory.refresh_from_db()
        assert memory.status == AgentMemory.Status.ACTIVE

    def test_confirm_pending(self, lawyer: Lawyer) -> None:
        pending = _memory(lawyer, "推测的偏好", status=AgentMemory.Status.PENDING)
        affected = memory_service.confirm_memories(lawyer, [str(pending.pk)], accept=True)
        assert affected == 1
        pending.refresh_from_db()
        assert pending.status == AgentMemory.Status.ACTIVE

    def test_reject_pending(self, lawyer: Lawyer) -> None:
        pending = _memory(lawyer, "推测的偏好", status=AgentMemory.Status.PENDING)
        memory_service.confirm_memories(lawyer, [str(pending.pk)], accept=False)
        pending.refresh_from_db()
        assert pending.status == AgentMemory.Status.DELETED


@pytest.mark.django_db
class TestKeywordFallback:
    def test_keyword_search_without_embedding(self, lawyer: Lawyer) -> None:
        """embed 服务未配置时检索必须退化为关键词而不是整体失效。"""
        target = _memory(lawyer, "文书先给结论再给理由")
        _memory(lawyer, "完全不相关的另一条记忆")
        results = memory_service.search_memories(lawyer, "结论")
        assert [m.pk for m, _score in results] == [target.pk]

    def test_no_match_returns_empty(self, lawyer: Lawyer) -> None:
        _memory(lawyer, "文书先给结论")
        assert memory_service.search_memories(lawyer, "完全不沾边的词") == []


# ── 端到端回归：两个真实 bug（2026-10-25 实测发现）──────────────────────────


@pytest.mark.django_db
class TestCurationPermissionBoundary:
    """管理员策展成员记忆 —— 曾因复用「可见范围」而全线失败。

    真实症状：候选池里明明列出成员记忆，一提交提升就报
    「部分来源记忆不存在或无权访问」。根因是 `promote_memory` 用
    `visible_queryset`（「我自己看得见的」）校验来源，而管理员的可见范围
    不含成员的个人记忆。策展来源范围与读可见范围是两个不同概念。
    """

    def test_admin_can_promote_member_memory(self, firm: LawFirm, team: Team) -> None:
        admin = Lawyer.objects.create_user(username="cur_admin", password=TEST_PASSWORD, law_firm=firm, is_admin=True)
        admin.lawyer_teams.add(team)
        member = Lawyer.objects.create_user(username="cur_member", password=TEST_PASSWORD, law_firm=firm)
        member.lawyer_teams.add(team)

        source = _memory(member, "回复法院函件不要超过 800 字", kind=AgentMemory.Kind.PROCEDURE)
        promoted = memory_service.promote_memory(
            admin,
            source_ids=[str(source.pk)],
            content="对外函件统一控制在 800 字以内，超出的拆附件",
            kind=AgentMemory.Kind.PROCEDURE,
            scope=AgentMemory.Scope.TEAM,
            team_id=team.pk,
        )
        assert promoted.scope == AgentMemory.Scope.TEAM
        assert list(promoted.promoted_from.all()) == [source]

    def test_admin_cannot_promote_other_team_memory(self, firm: LawFirm) -> None:
        """跨团队成员不在策展来源范围内。"""
        other_team = Team.objects.create(name="他组", team_type=TeamType.LAWYER, law_firm=firm)
        admin = Lawyer.objects.create_user(username="cur_admin2", password=TEST_PASSWORD, law_firm=firm, is_admin=True)
        outsider_member = Lawyer.objects.create_user(username="cur_out2", password=TEST_PASSWORD, law_firm=firm)
        outsider_member.lawyer_teams.add(other_team)

        source = _memory(outsider_member, "他组的一条惯例", kind=AgentMemory.Kind.PROCEDURE)
        with pytest.raises(ValueError, match="不存在或无权访问"):
            memory_service.promote_memory(
                admin,
                source_ids=[str(source.pk)],
                content="改写后的规则",
                kind=AgentMemory.Kind.PROCEDURE,
                scope=AgentMemory.Scope.TEAM,
                team_id=other_team.pk + 999,  # 不属于该团队的 id
            )

    def test_candidates_and_promote_share_source_scope(self, firm: LawFirm, team: Team) -> None:
        """候选池里列出来的，必须就能提升成功（口径一致）。"""
        admin = Lawyer.objects.create_user(username="cur_admin3", password=TEST_PASSWORD, law_firm=firm, is_admin=True)
        admin.lawyer_teams.add(team)
        member = Lawyer.objects.create_user(username="cur_member3", password=TEST_PASSWORD, law_firm=firm)
        member.lawyer_teams.add(team)
        _memory(member, "回函要附法条原文", kind=AgentMemory.Kind.PROCEDURE)

        candidates = memory_service.promote_candidates(admin, scope=AgentMemory.Scope.TEAM, team_id=team.pk)
        assert len(candidates) == 1
        promoted = memory_service.promote_memory(
            admin,
            source_ids=[candidates[0]["id"]],
            content="对外回函一律附引用法条原文",
            kind=AgentMemory.Kind.PROCEDURE,
            scope=AgentMemory.Scope.TEAM,
            team_id=team.pk,
        )
        assert promoted.pk is not None


@pytest.mark.django_db
class TestRouteOrdering:
    """静态路径不能被动态段吞掉 —— 曾导致 /snapshot 返回 405。

    Django 按注册顺序匹配路径，``/{memory_id}`` 会吃掉任何单段路径。
    真实症状：``GET /agent/memory/snapshot`` 命中 ``DELETE /{memory_id}``
    的规则返回 405（allow: DELETE），pi 扩展拿不到快照、记忆功能整体失效，
    而前端与日志都没有明显报错。
    """

    def test_snapshot_path_resolves_to_snapshot_view(self) -> None:
        from django.urls import resolve

        match = resolve("/api/v1/agent/memory/snapshot")
        assert match.func.__name__ != "forget_memory", "静态路径被动态段 /{memory_id} 吞掉了"
        assert "snapshot" in str(match.func).lower() or "snapshot" in match.url_name.lower()

    @pytest.mark.parametrize("path", ["confirm", "snapshot", "promotion", "promotion/candidates", "scopes"])
    def test_static_routes_not_shadowed(self, path: str) -> None:
        from django.urls import resolve

        match = resolve(f"/api/v1/agent/memory/{path}")
        assert match.func.__name__ != "forget_memory"


@pytest.mark.django_db
class TestSemanticSearch:
    """语义检索：字面无关、语义相关时必须召回。

    这是 `recall_memory` 的核心能力。早前它拉全量后做子串过滤，问
    「我问过的格式要求」找不到存成「文书先给结论」的记忆——等于该功能
    只对「用户记得原话」的有用，而那种情况本来就不需要检索。
    """

    def test_keyword_miss_still_recalled_by_vector(self, lawyer: Lawyer) -> None:
        """用假向量直接验证余弦通路（不依赖真实 embed 服务）。"""
        target = _memory(lawyer, "文书先给结论再给理由")
        AgentMemory.objects.filter(pk=target.pk).update(embedding=[1.0, 0.0, 0.0])
        irrelevant = _memory(lawyer, "完全不相关的另一条")
        AgentMemory.objects.filter(pk=irrelevant.pk).update(embedding=[0.0, 1.0, 0.0])

        # 查询语义上接近「格式要求」，但字面与两条都不重合
        with patch.object(memory_service, "_embed_query", return_value=[1.0, 0.0, 0.0]):
            hits = memory_service.search_memories(lawyer, "我问过的格式要求")

        ids = [m.pk for m, _score in hits]
        assert target.pk in ids, "语义命中必须被召回"
        assert irrelevant.pk not in ids, "不相关的不应混入"

    def test_backfill_fills_missing_embedding(self, lawyer: Lawyer) -> None:
        """没有向量的历史记忆，在检索时被批量补上。"""
        memory = _memory(lawyer, "回函要附法条原文")
        assert not memory.embedding

        with patch.object(memory_service, "_embed_query", return_value=[1.0, 0.0]):
            with patch(
                "apps.core.interfaces.ServiceLocator.get_llm_service",
                return_value=MagicMock(embed_texts=lambda texts, **kw: [[0.9, 0.1]] * len(texts)),
            ):
                memory_service.search_memories(lawyer, "法条")

        memory.refresh_from_db()
        assert memory.embedding == [0.9, 0.1]

    def test_empty_query_falls_back_to_usage_ranking(self, lawyer: Lawyer) -> None:
        _memory(lawyer, "高命中偏好", hit_count=10)
        _memory(lawyer, "低命中偏好", hit_count=0)
        hits = memory_service.search_memories(lawyer, "")
        assert hits[0][0].content == "高命中偏好"

    def test_search_respects_scope_isolation(self, lawyer: Lawyer, outsider: Lawyer) -> None:
        mine = _memory(lawyer, "我的私密偏好")
        with patch.object(memory_service, "_embed_query", return_value=None):
            assert all(m.pk != mine.pk for m, _ in memory_service.search_memories(outsider, "私密"))


@pytest.mark.django_db
class TestLawFirmAcknowledgment:
    """律所层影响全所，提交必须显式确认影响面。

    为什么不是双管理员会签：实测生产数据里存在只有 1 个管理员、甚至 0 个
    管理员的律所，强制会签会让那些律所完全用不了律所层。真实约束应该是
    「你知道自己在写全所规范」。
    """

    def test_law_firm_requires_acknowledgment(self, lawyer: Lawyer) -> None:
        lawyer.is_admin = True
        lawyer.save(update_fields=["is_admin"])
        source = _memory(lawyer, "立案前统一做冲突检索")

        with pytest.raises(ValueError, match="影响面"):
            memory_service.promote_memory(
                lawyer,
                source_ids=[str(source.pk)],
                content="全所立案前统一完成冲突检索并留痕",
                kind=AgentMemory.Kind.PROCEDURE,
                scope=AgentMemory.Scope.LAW_FIRM,
            )

    def test_law_firm_accepts_with_acknowledgment(self, lawyer: Lawyer) -> None:
        lawyer.is_admin = True
        lawyer.save(update_fields=["is_admin"])
        source = _memory(lawyer, "立案前统一做冲突检索")

        promoted = memory_service.promote_memory(
            lawyer,
            source_ids=[str(source.pk)],
            content="全所立案前统一完成冲突检索并留痕",
            kind=AgentMemory.Kind.PROCEDURE,
            scope=AgentMemory.Scope.LAW_FIRM,
            acknowledged_firm_wide=True,
        )
        assert promoted.scope == AgentMemory.Scope.LAW_FIRM

    def test_team_layer_does_not_require_acknowledgment(self, lawyer: Lawyer, team: Team) -> None:
        """团队层影响面有限，不增加摩擦。"""
        source = _memory(lawyer, "回函先给结论")
        promoted = memory_service.promote_memory(
            lawyer,
            source_ids=[str(source.pk)],
            content="对外回函统一先给结论再展开理由",
            kind=AgentMemory.Kind.PROCEDURE,
            scope=AgentMemory.Scope.TEAM,
            team_id=team.pk,
        )
        assert promoted.scope == AgentMemory.Scope.TEAM


@pytest.mark.django_db
class TestPlaybookChannel:
    """操作指引走「索引 + 按需取全文」通道，不挤占每轮注入。

    为什么需要这条通道：注入层单条上限 200 字、律所层配额 700 字。一份
    36 行的「阅卷规范」若按普通记忆处理会被**静默跳过**——律师写了、界面
    显示已保存、但助手永远看不到，会以为记忆坏了。静默失败比功能缺失更伤信任。
    """

    PLAYBOOK = (
        "阅卷规范\n"
        "1. 阅卷前先调 get_case 确认承办阶段与当事人\n"
        "2. 卷宗按「程序性文书 → 证据 → 笔录」排序\n"
        "3. 每份材料页脚标注来源与页码\n"
        "4. 复印件与原件分卷存放\n"
    )

    def test_playbook_creation_allows_long_multiline(self, lawyer: Lawyer) -> None:
        memory = memory_service.create_memory(lawyer, content=self.PLAYBOOK, kind=AgentMemory.Kind.PLAYBOOK)
        assert memory.kind == AgentMemory.Kind.PLAYBOOK
        assert "\n" in memory.content, "操作指引必须保留换行（压平会丢失分步结构）"
        assert len(memory.content) > 80, "多行结构应被保留"

    def test_playbook_not_inlined_only_indexed(self, lawyer: Lawyer) -> None:
        memory_service.create_memory(lawyer, content=self.PLAYBOOK, kind=AgentMemory.Kind.PLAYBOOK)
        snapshot = memory_service.build_snapshot(lawyer, refresh=True, refresh_reason="test")

        # 正文不进注入
        assert "每份材料页脚标注来源与页码" not in snapshot
        # 但索引行必须在——看不到索引就永远不会去取全文
        assert "阅卷规范" in snapshot
        assert "recall_memory" in snapshot
        # 索引只能是标题，不能带出正文（实测踩过：压平后再切首行会变半截正文）
        assert "阅卷前先调 get_case" not in snapshot

    def test_short_rules_still_inlined_alongside_playbook(self, lawyer: Lawyer) -> None:
        memory_service.create_memory(lawyer, content="文书先给结论", kind=AgentMemory.Kind.PREFERENCE)
        memory_service.create_memory(lawyer, content=self.PLAYBOOK, kind=AgentMemory.Kind.PLAYBOOK)
        snapshot = memory_service.build_snapshot(lawyer, refresh=True, refresh_reason="test")

        assert "文书先给结论" in snapshot, "短规则不被指引挤掉"
        assert "阅卷规范" in snapshot

    def test_playbook_full_text_retrievable(self, lawyer: Lawyer) -> None:
        """按需取全文：检索必须返回完整正文而不是索引。"""
        memory_service.create_memory(lawyer, content=self.PLAYBOOK, kind=AgentMemory.Kind.PLAYBOOK)
        with patch.object(memory_service, "_embed_query", return_value=None):
            hits = memory_service.search_memories(lawyer, "阅卷规范", limit=5)
        assert hits, "应能检索到指引"
        assert "每份材料页脚标注来源与页码" in hits[0][0].content

    def test_playbook_rejects_over_limit(self, lawyer: Lawyer) -> None:
        with pytest.raises(ValueError, match="过长"):
            memory_service.create_memory(
                lawyer, content="x" * (memory_service.PLAYBOOK_MAX_CHARS + 1), kind=AgentMemory.Kind.PLAYBOOK
            )

    def test_short_kind_still_flattened(self, lawyer: Lawyer) -> None:
        """非指引类型仍压成一行——它们应当是一句可复用的事实。"""
        memory = memory_service.create_memory(
            lawyer, content="文书先给结论\n再给理由", kind=AgentMemory.Kind.PREFERENCE
        )
        assert "\n" not in memory.content


@pytest.mark.django_db
class TestReinforcedAnchor:
    """衰减锚点与「最后修改」分离（借 pi-memory-evolution 的 reinforcedAt）。

    混用两者会出两种错：
    - 用 updated_at 做衰减 → 仅被命中的记忆永远不衰减（命中也推 updated_at）；
    - 用 updated_at 做衰减 → 改个措辞就无幸续命。
    """

    def test_hit_refreshes_reinforced_but_not_updated(self, lawyer: Lawyer) -> None:
        memory = _memory(lawyer, "常被用到的偏好")
        original_updated = memory.updated_at
        assert memory.reinforced_at is None

        memory_service.mark_hit([memory])

        memory.refresh_from_db()
        assert memory.reinforced_at is not None, "命中应刷新衰减锚点"
        assert memory.updated_at == original_updated, "命中不是修改，不得动 updated_at"
        assert memory.hit_count == 1
