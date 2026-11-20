"""``services/chat/equivalence.py`` 的等价聚类（双向蕴含 + 团覆盖 + 显式 tie）。

本文件钉的是三件会让律师被误导的事：

1. **单向蕴含不算等价**：A 比 B 少一个要件时，A→B 常被判蕴含、B→A 不成立。
   只判一次的"等价"会把"少写一条"评成"一致"，这正是判等最贵的一类错；
2. **不做传递闭包**：A≈B、B≈C 但 A≉C（"B 是折中意见"）时，并查集会并成三方
   共识。这里只认团（簇内两两都必须双向蕴含），折中那份单独成簇；
3. **全异 / 平票显式 tie**：没有唯一最大簇时 ``representative_id`` 必须是空串、
   所有簇 ``tie=True``。绝不回落成入参第一条——那会让律师把随机一份当共识。

全部是纯函数用例：判等函数注入假实现，不联网、不建库。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from itertools import combinations
from typing import cast

from apps.agent.services.adjudication.contracts import EquivalenceCluster
from apps.agent.services.chat.equivalence import MAX_CLIQUE_INPUT, cluster_answers

#: 判等形状与生产一致：``entails(a, b)`` = 把 b 当假设、a 当前提时是否蕴含。
Entails = Callable[[str, str], bool]


def _entails_over(equivalent_pairs: Iterable[tuple[str, str]]) -> Entails:
    """按"互为等价"的答案对造一个对称判等函数（两个方向都返回 True）。"""
    pairs = {frozenset(pair) for pair in equivalent_pairs}

    def entails(premise: str, hypothesis: str) -> bool:
        return frozenset({premise, hypothesis}) in pairs

    return entails


def _never(a: str, b: str) -> bool:
    """全异：任何一对都不等价。"""
    return False


def test_single_direction_entailment_does_not_merge() -> None:
    """只有 A→B 成立：不是等价，两份各成一簇且都 tie（代表不可判定）。"""

    def only_forward(premise: str, hypothesis: str) -> bool:
        return premise == "A"

    clusters = cluster_answers(["A", "B"], only_forward)

    assert [cluster.member_ids for cluster in clusters] == [("A",), ("B",)]
    assert all(cluster.tie for cluster in clusters)
    assert all(cluster.representative_id == "" for cluster in clusters)


def test_compromise_answer_is_not_transitively_merged() -> None:
    """A≈B、B≈C 但 A≉C：A 与 C 绝不能出现在同一个簇里（并查集会并成三方）。"""
    clusters = cluster_answers(["A", "B", "C"], _entails_over([("A", "B"), ("B", "C")]))

    assert [cluster.member_ids for cluster in clusters] == [("A", "B"), ("C",)]
    assert all(cluster.tie is False for cluster in clusters)
    assert clusters[0].representative_id == "A"
    assert clusters[1].representative_id == "C"


def test_all_distinct_returns_singletons_with_tie_and_no_representative() -> None:
    """DoD ④全异：三份互不等价 → 三个单例簇、全部 tie、代表一律空串（不回落首条）。"""
    clusters = cluster_answers(["A", "B", "C"], _never)

    assert [cluster.member_ids for cluster in clusters] == [("A",), ("B",), ("C",)]
    assert all(cluster.tie for cluster in clusters)
    assert all(cluster.representative_id == "" for cluster in clusters)
    # 空串是"没有代表"，不是"代表是入参第一条"——后者会让前端把随机一份当共识。
    assert "A" not in {cluster.representative_id for cluster in clusters}


def test_tied_largest_clusters_mark_every_cluster_as_tie() -> None:
    """平票：两组同为最大 → 没有唯一最大簇，所有簇都不给代表。"""
    clusters = cluster_answers(["A", "B", "C", "D"], _entails_over([("A", "B"), ("C", "D")]))

    assert [cluster.member_ids for cluster in clusters] == [("A", "B"), ("C", "D")]
    assert all(cluster.tie for cluster in clusters)
    assert {cluster.representative_id for cluster in clusters} == {""}


def test_unique_largest_cluster_comes_first_and_minority_is_kept() -> None:
    """有唯一最大簇：首元素是主导立场，少数立场照样返回（不裁掉）。"""
    clusters = cluster_answers(["A", "B", "C"], _entails_over([("A", "B")]))

    assert [cluster.member_ids for cluster in clusters] == [("A", "B"), ("C",)]
    assert [cluster.tie for cluster in clusters] == [False, False]
    assert clusters[0].representative_id == "A"
    assert clusters[1].representative_id == "C"


def test_clusters_are_ordered_by_size_then_input_position() -> None:
    """簇间排序：先按大小降序，再按入参最早成员下标升序。"""
    clusters = cluster_answers(
        ["A", "B", "C", "D", "E"],
        _entails_over([("A", "B"), ("C", "D"), ("D", "E"), ("C", "E")]),
    )

    assert [cluster.member_ids for cluster in clusters] == [("C", "D", "E"), ("A", "B")]
    assert clusters[0].representative_id == "C"
    assert all(cluster.tie is False for cluster in clusters)


def test_representative_is_earliest_member_in_input_order() -> None:
    """团内两两等价，代表取入参最早的那一份（不改写原文，见模块 docstring）。"""
    clusters = cluster_answers(["C", "A", "B"], _entails_over([("A", "B"), ("A", "C"), ("B", "C")]))

    assert len(clusters) == 1
    assert clusters[0].member_ids == ("C", "A", "B")
    assert clusters[0].representative_id == "C"
    assert clusters[0].tie is False


def test_entailment_is_asked_both_ways_once_per_pair() -> None:
    """每一对都问两个方向、且从不问 (x, x)——双向证据是判位置偏置的唯一来源。"""
    calls: list[tuple[str, str]] = []
    ids = ["A", "B", "C", "D"]

    def recording(premise: str, hypothesis: str) -> bool:
        calls.append((premise, hypothesis))
        return False

    cluster_answers(ids, recording)

    assert len(calls) == 2 * len(list(combinations(ids, 2)))
    assert all(premise != hypothesis for premise, hypothesis in calls)
    assert {frozenset(call) for call in calls} == {frozenset(pair) for pair in combinations(ids, 2)}


def test_more_than_max_input_degrades_to_all_distinct_without_judging() -> None:
    """份数超过上限：不判、不猜，直接"全部单例 + tie"（不回退到并查集）。"""
    ids = [f"L{index}" for index in range(MAX_CLIQUE_INPUT + 1)]

    def must_not_be_called(premise: str, hypothesis: str) -> bool:
        raise AssertionError("超过 MAX_CLIQUE_INPUT 时不应发起判等")

    clusters = cluster_answers(ids, must_not_be_called)

    assert [cluster.member_ids for cluster in clusters] == [(member,) for member in ids]
    assert all(cluster.tie for cluster in clusters)
    assert all(cluster.representative_id == "" for cluster in clusters)


def test_empty_and_single_input() -> None:
    """空输入 → 空列表；单份答案自成唯一最大簇（有代表、不 tie）。"""
    assert cluster_answers([], _never) == []

    clusters = cluster_answers(["A"], _never)

    assert len(clusters) == 1
    assert clusters[0].member_ids == ("A",)
    assert clusters[0].representative_id == "A"
    assert clusters[0].tie is False


def test_duplicate_ids_are_deduped_and_never_self_compared() -> None:
    """重复 id 去重保序：同一份答案不会既当成员又当"等价对象"。"""
    calls: list[tuple[str, str]] = []

    def recording(premise: str, hypothesis: str) -> bool:
        calls.append((premise, hypothesis))
        return False

    clusters = cluster_answers(["A", "A", "B"], recording)

    assert [cluster.member_ids for cluster in clusters] == [("A",), ("B",)]
    assert calls == [("A", "B"), ("B", "A")]


def test_failed_judgement_counts_as_not_equivalent() -> None:
    """判等失败（注入方按约定返回假值）按"不等价"处理，不并簇、不抛错。"""

    def unknown(premise: str, hypothesis: str) -> bool:
        return cast(bool, None)

    clusters = cluster_answers(["A", "B"], unknown)

    assert [cluster.member_ids for cluster in clusters] == [("A",), ("B",)]
    assert all(cluster.tie for cluster in clusters)


def test_cluster_answers_returns_contract_type() -> None:
    """返回的必须是契约里的 frozen dataclass（前端/评审侧按它取值）。"""
    clusters = cluster_answers(["A", "B"], _entails_over([("A", "B")]))

    assert isinstance(clusters[0], EquivalenceCluster)
    assert isinstance(clusters[0].member_ids, tuple)
