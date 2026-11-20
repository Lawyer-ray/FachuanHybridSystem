"""记忆作用域解析与权限边界。

``visible_queryset`` 是唯一读权限入口；``_curation_source_queryset`` 是
策展来源范围——两者刻意不同（管理员要策展成员记忆，但看不到别人的个人
记忆），见各函数注释。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.apps import apps as django_apps
from django.db.models import Q, QuerySet

from ...models import AgentMemory

if TYPE_CHECKING:
    from apps.organization.models import Lawyer


def team_member_ids(lawyer: Lawyer) -> set[int]:
    """当前律师可见范围的**律师 id 集合**（同律师团队全体 + 自己）。

    直接调 ``OrgAccessComputationService.compute``，不在这里重写一遍
    「团队成员」的算法：那是全系统的权限真相（``org_access["lawyers"]``），
    在这里复制一份必然漂移，而漂移的后果是「同团队的人看不到彼此的判断」
    或反过来「团队外的人看到了」——后者是泄密。

    延迟 import：agent 不在模块加载期静态依赖 organization 的服务图
    （与 ``session_service`` 的库懒解析同口径）。
    """
    from apps.organization.services.wiring import build_org_access_computation_service

    access = build_org_access_computation_service().compute(lawyer)
    lawyer_ids = set(access.get("lawyers", set()) or set())
    lawyer_ids.add(lawyer.pk)
    return lawyer_ids


def anchor_q(*, contract_id: int | None, case_id: int | None) -> Q | None:
    """项目/案件锚点的匹配条件；两个锚点都为空时返回 None（调用方不加条件）。

    匹配语义：挂在**本项目**上的条目，或挂在**本案**上的条目。合同层的条目
    在它所有下属案件的会话里可见（项目就是权限泡）；案件层的条目不在兄弟
    案件里展开——那会让批量诉讼的事实互相串味。
    """
    condition = Q()
    matched = False
    if contract_id is not None:
        condition |= Q(contract_id=contract_id)
        matched = True
    if case_id is not None:
        condition |= Q(case_id=case_id)
        matched = True
    return condition if matched else None


def anchor_visible_queryset(
    lawyer: Lawyer,
    *,
    contract_id: int | None,
    case_id: int | None,
    include_status: tuple[str, ...] = (AgentMemory.Status.ACTIVE,),
) -> QuerySet[AgentMemory]:
    """**项目笔记的唯一读入口**：同团队成员挂在本项目/本案上的条目。

    与 :func:`visible_queryset` 的区别（别把两者混用）：

    | | visible_queryset | 本函数 |
    |:-|:-|:-|
    | 回答 | 「我个人/我团队/我所」的偏好与惯例 | 「本项目」的判断 |
    | 归属维度 | scope（lawyer/team/law_firm） | 锚点（contract_id/case_id） |
    | 作者范围 | 按作用域三档 | 同律师团队全体（含他人） |

    被更新条目推翻的旧条（``superseded_by`` 非空）不参与注入：模型该看到
    的是现结论；旧结论留在库里供人回查「当时怎么定的」。
    """
    condition = anchor_q(contract_id=contract_id, case_id=case_id)
    if condition is None:
        return AgentMemory.objects.none()
    return AgentMemory.objects.filter(
        condition,
        lawyer_id__in=list(team_member_ids(lawyer)),
        status__in=include_status,
        superseded_by__isnull=True,
    )


def resolve_scopes(lawyer: Lawyer) -> list[tuple[str, dict[str, Any]]]:
    """当前律师可见的记忆作用域。

    顺序即注入顺序（个人 → 团队 → 律所）。团队取 ``lawyer_teams``（律师团队），
    不含业务团队：业务团队是承接口径，不承载办案习惯。
    """
    scopes: list[tuple[str, dict[str, Any]]] = [(AgentMemory.Scope.LAWYER, {"lawyer": lawyer})]
    team_ids = list(lawyer.lawyer_teams.values_list("id", flat=True))
    if team_ids:
        scopes.append((AgentMemory.Scope.TEAM, {"team_id__in": team_ids}))
    if lawyer.law_firm_id:
        scopes.append((AgentMemory.Scope.LAW_FIRM, {"law_firm_id": lawyer.law_firm_id}))
    return scopes


def visible_queryset(
    lawyer: Lawyer, *, include_status: tuple[str, ...] = (AgentMemory.Status.ACTIVE,)
) -> QuerySet[AgentMemory]:
    """当前律师可见且处于指定状态的记忆。

    **这是权限边界**：任何读路径都必须经此函数，不要直接 ``AgentMemory.objects``。
    三段 OR：个人（自己）、团队（所在律师团队）、律所（所属律所）。整条 Q 里
    同时带 ``scope`` 与归属字段，避免「团队条件命中律所记忆」这类交叉误匹配。
    """
    condition = Q(scope=AgentMemory.Scope.LAWYER, lawyer=lawyer)
    team_ids = list(lawyer.lawyer_teams.values_list("id", flat=True))
    if team_ids:
        condition |= Q(scope=AgentMemory.Scope.TEAM, team_id__in=team_ids)
    if lawyer.law_firm_id:
        condition |= Q(scope=AgentMemory.Scope.LAW_FIRM, law_firm_id=lawyer.law_firm_id)
    return AgentMemory.objects.filter(condition, status__in=include_status)


def _can_curate(lawyer: Lawyer, memory: AgentMemory) -> bool:
    """该律师是否有权策展这条记忆所属的作用域。

    团队层：律所管理员，或该团队的成员（团队惯例由本团队自己定）。
    律所层：必须是律所管理员。
    """
    if memory.scope == AgentMemory.Scope.LAW_FIRM:
        return bool(lawyer.is_admin and lawyer.law_firm_id == memory.law_firm_id)
    if memory.scope == AgentMemory.Scope.TEAM:
        if lawyer.is_admin and lawyer.law_firm_id == (memory.team.law_firm_id if memory.team else None):
            return True
        return memory.team is not None and lawyer.lawyer_teams.filter(pk=memory.team.pk).exists()
    return memory.lawyer_id == lawyer.pk


def can_curate_scope(lawyer: Lawyer, scope: str, *, team_id: int | None = None) -> bool:
    """是否有权向指定作用域提升记忆（前端据此决定是否显示策展入口）。"""
    if scope == AgentMemory.Scope.TEAM:
        if not team_id:
            return False
        if lawyer.is_admin:
            return True
        return lawyer.lawyer_teams.filter(pk=team_id).exists()
    if scope == AgentMemory.Scope.LAW_FIRM:
        return bool(lawyer.is_admin and lawyer.law_firm_id)
    return True


def _curation_source_queryset(lawyer: Lawyer, *, scope: str, team_id: int | None) -> QuerySet[AgentMemory]:
    """策展的**来源范围**：可被提升为指定团队/律所的人记忆。

    这个范围与 ``visible_queryset``（「我自己看得见的」）**刻意不同**：
    管理员要策展成员的记忆，但他看不到别人的个人记忆。早期实现把两处
    混用，症状是管理员提交提升时被「部分来源记忆不存在或无权访问」拦住——
    候选池里明明列着，一提交就报不存在。

    写入仍由 ``can_curate_scope`` 把关（调用方先校验），本函数只负责
    「该作用域下哪些人记忆属于可策展来源」。
    """
    # 跨 app 模型延迟解析（agent 不静态依赖 organization，与 session_service 同口径）
    lawyer_model = django_apps.get_model("organization", "Lawyer")

    if scope == AgentMemory.Scope.TEAM:
        if not team_id:
            raise ValueError("提升到团队必须指定 team_id")
        member_ids = list(
            # 只取本团队成员的个人记忆
            lawyer_model.objects.filter(lawyer_teams__id=team_id).values_list("id", flat=True)
        )
    elif scope == AgentMemory.Scope.LAW_FIRM:
        if not lawyer.law_firm_id:
            raise ValueError("当前账号未归属律所")
        member_ids = list(lawyer_model.objects.filter(law_firm_id=lawyer.law_firm_id).values_list("id", flat=True))
    else:
        raise ValueError("只能向团队或律所层提升")

    return AgentMemory.objects.filter(
        scope=AgentMemory.Scope.LAWYER,
        lawyer_id__in=member_ids,
        status=AgentMemory.Status.ACTIVE,
    )
