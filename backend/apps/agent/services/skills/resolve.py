"""解析「某个律师这一轮看到什么技能」——**唯一解析入口**。

任何地方（注入、清单、将来多后端的提示块）都必须经过本模块，不许自己拼
「内置 + 个人」的并集。这样级联去重、偏好过滤、影子关系只有一份实现。

## 四步（P0 只落地前三步里的前两段）

1. **可见集**：内置（文件扫描）∪ ``scope=lawyer & lawyer=我 & status=active``。
   team / law_firm 的可见性在 P0 不开（字段与索引已预留）。
2. **按 name 级联去重**：``SCOPE_RANK`` 小者胜（个人 > 团队 > 所内）；败者进
   赢家的 ``shadowed``。内置名是保留字、个人技能不得占用，所以内置天然不参与
   冲突（若历史数据撞上，内置胜——它随代码发布，不该被数据库行顶掉）。
3. **偏好过滤**：内置看 ``AgentSkillPreference``（缺省启用），个人看
   ``AgentSkill.enabled``。``archived`` 永远不出现——偏好翻不回来。
4. 预算裁剪不在 P0（pi 走 ``--skill`` 目录注入，不经提示块）。
"""

from __future__ import annotations

from collections import defaultdict

from apps.agent.models import AgentSkill, AgentSkillPreference

from .constants import BUILTIN_PREFIX, SCOPE_RANK
from .library import builtin_skills


def visible_skills(user_id: int) -> list[dict]:
    """该律师可见的技能（含禁用项与 ``shadowed``，供清单/开关展示）。"""
    entries = _builtin_entries(user_id) + _personal_entries(user_id)
    winners: dict[str, dict] = {}
    shadowed: dict[str, list[dict]] = defaultdict(list)
    for entry in entries:
        current = winners.get(entry["name"])
        if current is None:
            winners[entry["name"]] = entry
            continue
        if _rank(entry) < _rank(current):
            shadowed[entry["name"]].append(_shadow_ref(current))
            winners[entry["name"]] = entry
        else:
            shadowed[entry["name"]].append(_shadow_ref(entry))
    for name, loser in shadowed.items():
        winners[name]["shadowed"] = loser
    return [winners[name] for name in sorted(winners)]


def resolve_for_user(user_id: int) -> list[dict]:
    """本轮**可交付**的技能（启用且可见）；注入与将来的提示块都只认这个结果。"""
    return [skill for skill in visible_skills(user_id) if skill["enabled"]]


def _builtin_entries(user_id: int) -> list[dict]:
    disabled = set(
        AgentSkillPreference.objects.filter(
            user_id=user_id,
            enabled=False,
            skill_key__startswith=BUILTIN_PREFIX,
        ).values_list("skill_key", flat=True)
    )
    entries: list[dict] = []
    for skill in builtin_skills():
        entries.append({**skill, "enabled": skill["key"] not in disabled, "shadowed": []})
    return entries


def _personal_entries(user_id: int) -> list[dict]:
    rows = AgentSkill.objects.filter(lawyer_id=user_id, status=AgentSkill.Status.ACTIVE).order_by("name")
    return [
        {
            "key": f"skill:{row.pk}",
            "name": row.name,
            "title": row.title,
            "description": row.description,
            "enabled": row.enabled,
            "source": "user",
            "scope": row.scope,
            "editable": True,
            "version": row.version,
            "shadowed": [],
        }
        for row in rows
    ]


def _rank(entry: dict) -> int:
    """级联优先级：数值小者胜；内置（保留名）永远最高。"""
    if entry["source"] == "builtin":
        return -1
    return SCOPE_RANK.get(str(entry.get("scope") or ""), len(SCOPE_RANK))


def _shadow_ref(entry: dict) -> dict:
    return {"key": entry["key"], "scope": entry.get("scope", ""), "title": entry["title"]}
