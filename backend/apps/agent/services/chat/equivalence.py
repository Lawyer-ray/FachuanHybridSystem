"""多栏答案「是不是同一个立场」的确定性聚合（判等注入，聚合不花 LLM）。

## 为什么判等要双向，不是相似度、也不是单向 OR

字面重合度先出局：「该条款**应当**认定为无效」与「该条款**不**应当认定为
无效」只差一个字符，重合度 0.95+，结论却相反；「A 赔」与「B 赔」差三个字，
钱从谁口袋里出不一样。所以判等交给 LLM/小模型判**蕴含**（判等 prompt 与
并发/超时/解析重试都在调用方，不在本模块）。

而且必须**双向各判一次**（``i→j`` 与 ``j→i``，同一 prompt 只交换位置）：
单向判定会被位置偏置和"A 是否包含 B 的要件"这种不对称语义带偏——A 比 B 少
一个要件时，A→B 常被判蕴含，B→A 不成立。**两个方向都成立才算等价**；任一
方向 False / 无法解析，这条边就不存在（保守：宁可少并一簇，不可错并一簇）。

## 为什么用团（clique），不用并查集的连通分量

连通分量做的是**传递闭包**：A≈B、B≈C 就把三份并成一簇，哪怕 A 与 C 是对立
结论。"B 是折中意见"的多栏场景恰好长成这样（A~B、B~C 但 A≁C），并查集会
把「两两不同」说成「三方共识」——在法律场景里这是错误信息，比少并一次贵得多。
所以这里只承认**团**（簇内两两都必须双向蕴含），并按「最大团优先」贪心覆盖：
已经被前一个团收走的成员不再重复出簇。

N ≤ 6 时两两判定最多 30 次（C(6,2) × 2 方向），团枚举直接穷举子集就够
（2^6 = 64）。N > 6 **不回退到并查集**：直接返回「全部单例 + tie」，宁可说
"判不出来"，也不给一个错的共识。

## ``tie`` 的准确含义：不存在唯一最大簇

- ``tie=False``：有唯一的最大簇。返回的簇按 ``(大小降, 入参最早成员下标升)``
  排序，**首元素就是主导立场**，其余是少数立场（不裁掉，前端可以展开看）。
- ``tie=True``：没有唯一最大簇——**全异**（全是单例）或**平票**（≥2 个簇
  同为最大）。此时**所有**返回簇的 ``representative_id`` 都是空串、``tie``
  都是 True：上层必须显示"各说各的"。绝不回落成入参第一条——那会让律师把
  随机的一份当成共识。

## 为什么没有默认的判等实现

默认实现只能是 LLM judge 的薄封装，而它要带并发上限、单次超时、整阶段
deadline、解析重试与「失败记 unknown 按不等价处理」——这些属于调用方（评审
编排），写进这里会让纯图计算模块依赖网络与密钥，单测也跑不起来。``entails``
一律注入，失败语义由注入方负责（超时/解析失败返回 False，本模块不吞异常）。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from itertools import combinations

from ..adjudication.contracts import EquivalenceCluster

#: 判等函数：``entails(a, b)`` = 把 b 当作假设、a 当作前提时是否蕴含。
#: 本模块会对每个无序对**两个方向各调一次**，只有两次都为真才连边。
EntailsFn = Callable[[str, str], bool]

#: 允许做两两判等的最大份数。超过它直接降级为"全异 + tie"（见模块 docstring）。
MAX_CLIQUE_INPUT = 6


def _dedupe(ids: Sequence[str]) -> list[str]:
    """去重保序：同一个 id 出现两次会让团枚举把"自己等价自己"算成一条边。"""
    return list(dict.fromkeys(ids))


def _bidirectional_adjacency(order: Sequence[str], entails: EntailsFn) -> list[list[bool]]:
    """对称邻接矩阵：``adjacent[i][j]`` 为真当且仅当两个方向都判为蕴含。

    两个方向都问（不短路）：短路会省掉一次调用，但也会把"只在 A→B 方向成立"
    这类不对称证据一起省掉——它正是判断位置偏置的唯一线索。
    """
    size = len(order)
    adjacent = [[False] * size for _ in range(size)]
    for i in range(size):
        for j in range(i + 1, size):
            forward = bool(entails(order[i], order[j]))
            backward = bool(entails(order[j], order[i]))
            adjacent[i][j] = adjacent[j][i] = forward and backward
    return adjacent


def _is_clique(members: Sequence[int], adjacent: list[list[bool]]) -> bool:
    """``members`` 是否两两相连（团）。"""
    for left, right in combinations(members, 2):
        if not adjacent[left][right]:
            return False
    return True


def _greedy_maximal_cliques(size: int, adjacent: list[list[bool]]) -> list[tuple[int, ...]]:
    """最大团优先的贪心覆盖，返回互不重叠的团（成员不会出现在两个簇里）。

    从大到小枚举子集：是团且不是已收团的子集 → 它就是最大团。然后按枚举顺序
    依次收人：已进过前一个团的成员不再重复出簇（剩下的成员仍是团——团对子集
    封闭），这样既能给"折中意见"单独留一簇，也不会让同一份答案出现两次。
    成员下标一律升序，即入参顺序。
    """
    maximal: list[tuple[int, ...]] = []
    for clique_size in range(size, 0, -1):
        for candidate in combinations(range(size), clique_size):
            if any(set(candidate) <= set(clique) for clique in maximal):
                continue  # 已是某个已收团的子集 → 不是最大团
            if _is_clique(candidate, adjacent):
                maximal.append(candidate)

    taken: set[int] = set()
    groups: list[tuple[int, ...]] = []
    for clique in maximal:
        leftover = tuple(member for member in clique if member not in taken)
        if leftover:
            groups.append(leftover)
            taken.update(leftover)
    return groups


def cluster_answers(ids: Sequence[str], entails: EntailsFn) -> list[EquivalenceCluster]:
    """把「其实同一个立场」的答案聚成簇。

    Args:
        ids: 各栏答案的标识（顺序即"入参顺序"，决定代表与簇间排序；重复 id 去重）。
        entails: 判等函数，见 :data:`EntailsFn`。单向成立不算等价。

    Returns:
        按 ``(簇大小降, 入参最早成员下标升)`` 排序的簇；``tie`` 的语义见模块
        docstring。``tie=True`` 时 ``representative_id`` 一律为空串。

    Raises:
        注入的 ``entails`` 抛出的异常原样上抛——失败语义归调用方（见模块 docstring）。
    """
    order = _dedupe(ids)
    if not order:
        return []
    if len(order) > MAX_CLIQUE_INPUT:
        # 不判、不猜：份数超限时"全异"是唯一诚实的结论。
        return [EquivalenceCluster(member_ids=(member,), representative_id="", tie=True) for member in order]

    adjacent = _bidirectional_adjacency(order, entails)
    groups = _greedy_maximal_cliques(len(order), adjacent)

    sizes = [len(group) for group in groups]
    tie = sizes.count(max(sizes)) > 1

    clusters: list[EquivalenceCluster] = []
    for group in sorted(groups, key=lambda members: (-len(members), members[0])):
        cluster_members = tuple(order[index] for index in group)
        clusters.append(
            EquivalenceCluster(
                member_ids=cluster_members,
                # tie 时代表不可判定：空串是"没有代表"，不是"代表是第一条"。
                representative_id="" if tie else cluster_members[0],
                tie=tie,
            )
        )
    return clusters


__all__ = [
    "MAX_CLIQUE_INPUT",
    "EntailsFn",
    "cluster_answers",
]
