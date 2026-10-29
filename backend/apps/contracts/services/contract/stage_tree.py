"""非诉专项阶段树的状态推导（纯函数，无 ORM / 无 IO）。

原型 `frontend/prototype/2026.10.03-办案详情原型/54-assets/phase-tree.js` 的
`deriveStates` 是这套规则的唯一参照，前后端必须给出同一个答案，否则同一份
stages 在页面刷新前后会「跳状态」。规则：

- 叶子：有**实际文件**（deliverables 里 `planned` 不为真的项）= 已完成；
  第一个「没有实际文件」的叶子（先序）= 进行中；其余 = 未开始。
- 父节点：由子节点聚合 —— 子全完成才算完成，否则进行中（子全未开始也照此
  视为进行中：父节点已经启动了进度）。

为什么不按 `deliverables[].state` 直接读：那是前端的编辑态（律师手改的
「撰写中」），而阶段状态是**从文件事实推出来的**；两者混在一起会出现
「阶段已完成但交付物还是待开始」这种自相矛盾。文件事实只有 `planned`。

为什么找「当前叶子」要先排除父节点：父节点的 deliverables 往往是空数组
（交付物挂在子阶段上），先序遍历它排在子节点之前，会把「进行中」抢走，
真正的当前叶子被误判成未开始（原型里踩过这个坑）。
"""

from __future__ import annotations

import copy
from typing import Any

# 阶段状态码：与前端 `PhaseState` 同义（ok = 已完成 / doing = 进行中 / todo = 未开始）
PHASE_DONE = "ok"
PHASE_DOING = "doing"
PHASE_PENDING = "todo"

StageNode = dict[str, Any]


def _iter_nodes(nodes: list[StageNode]) -> list[StageNode]:
    """**先序**展开（父 → 子 → 兄弟，与原型 `walk` 的 `forEach` 顺序一致）。

    顺序必须是 DFS 先序而不是按层展开：当前叶子取「先序第一个没落文件的
    叶子」，按层会把顶层无文件的兄弟节点排到子节点前面，把 curKey 抢走。
    """
    out: list[StageNode] = []
    stack: list[StageNode] = list(reversed(nodes))
    while stack:
        node = stack.pop()
        out.append(node)
        stack.extend(reversed(node.get("children") or []))
    return out


def _children(node: StageNode) -> list[StageNode]:
    return node.get("children") or []


def _has_real_file(node: StageNode) -> bool:
    return any(not deliverable.get("planned") for deliverable in node.get("deliverables") or [])


def _current_leaf_key(nodes: list[StageNode]) -> str | None:
    """第一个「没有实际文件」的叶子（先序）。整棵树都已落文件时为 None。"""
    for node in _iter_nodes(nodes):
        if _children(node) or _has_real_file(node):
            continue
        return str(node.get("key"))
    return None


def _compute(node: StageNode, current_key: str | None) -> str:
    """就地写入 node["state"] 并返回它；子节点先算，父节点靠子聚合。"""
    children = _children(node)
    if children:
        # 不能写 all(...)：all 短路，后面的兄弟节点拿不到 state
        child_states = [_compute(child, current_key) for child in children]
        state = PHASE_DONE if all(s == PHASE_DONE for s in child_states) else PHASE_DOING
    elif _has_real_file(node):
        state = PHASE_DONE
    else:
        state = PHASE_DOING if str(node.get("key")) == current_key else PHASE_PENDING
    node["state"] = state
    return state


def derive_phase_states(stages: list[StageNode] | None) -> list[StageNode]:
    """返回带 `state` 的**深拷贝**阶段树，入参不被修改；入参为空返回 []。

    节点按前端已定形的键读取（key / children / deliverables[].planned），缺失
    键一律按空处理——历史数据里的半成品节点不该让整页 500。
    """
    tree: list[StageNode] = copy.deepcopy(stages or [])
    current_key = _current_leaf_key(tree)
    for node in tree:
        _compute(node, current_key)
    return tree


__all__ = ["PHASE_DOING", "PHASE_DONE", "PHASE_PENDING", "derive_phase_states"]
