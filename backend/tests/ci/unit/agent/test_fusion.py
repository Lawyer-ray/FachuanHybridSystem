"""``services/chat/fusion.py`` 的确定性融合（RRF）。

本文件钉的是四件"换个实现就会悄悄错"的事：

1. **逐字节可复现**：同输入两次（以及换个 lane 插入顺序）输出完全一致——融合要
   进审计、进缓存、进 diff，任何"这次排 A 下次排 B"都不可接受；
2. **长尾不反转**：三路都排第 100 名的候选，``3 × 1/161 = 0.0186`` 会压过某一路
   的第 1 名 ``1/61 = 0.0164``。所以每一路必须先截到 ``2 × final_k``，本文件把
   这条边界（含"截到第几位"的精确位置）钉死；
3. **业务键去重**：同文不同法条不能并（并了就是丢依据），同一条法条跨两路必须并
   （不并就是三条一样的依据冒充三份材料）；``law_id::article_no`` 与
   ``file_id::page`` 形状相同，键必须带种类前缀才不撞；
4. **排序是完全是**：同分时按 ``hit_count`` / ``best_rank`` / ``key`` 决出唯一顺序，
   否则同一输入换个调用顺序就换个答案。

全部是纯函数用例：不建库、不联网。
"""

from __future__ import annotations

import json
from dataclasses import asdict

import pytest

from apps.agent.services.adjudication.contracts import FusedHit, RetrievalHit
from apps.agent.services.chat.fusion import LANE_TRUNCATION_FACTOR, RRF_K, case_key, page_key, rrf_fuse, statute_key

#: 一条"长尾"案号：在三路里都出现，但每路都排在第 100 名。
LONG_TAIL = case_key("（2021）最高法民申9号")  # allowlist secret（合成案号，仅用于测试解析规则）

#: 某一路的第 1 名（唯一一条进入计分的 rank 0 命中）。
FIRST_PLACE = statute_key(1, 1)


def _hit(key: str, lane: str, rank: int, title: str = "") -> RetrievalHit:
    return RetrievalHit(key=key, lane=lane, rank=rank, title=title)


def _dump(fused: list[FusedHit]) -> str:
    """序列化成稳定文本，用来做"两次执行逐字节一致"的比对。"""
    return json.dumps([asdict(hit) for hit in fused], ensure_ascii=False, sort_keys=True)


def _three_lane_fixture() -> dict[str, list[RetrievalHit]]:
    """一次典型的三路检索：法条 / 类案 / 卷宗页码，键与名次都有交叉。"""
    return {
        "law": [
            _hit(statute_key(1, 7), "law", 0),
            _hit(statute_key(1, 8), "law", 1),
            _hit(case_key("（2020）京01民终1号"), "law", 2),  # allowlist secret（合成案号，仅用于测试解析规则）
        ],
        "case": [
            _hit(case_key("（2020）京01民终1号"), "case", 0),  # allowlist secret（合成案号，仅用于测试解析规则）
            _hit(statute_key(1, 7), "case", 1),
        ],
        "file": [
            _hit(page_key(12, 3), "file", 0),
            _hit(statute_key(1, 8), "file", 1),
        ],
    }


def test_same_input_twice_is_byte_identical() -> None:
    """DoD ①：同输入两次执行，输出逐字节一致。"""
    lanes = _three_lane_fixture()
    assert _dump(rrf_fuse(lanes, 5)) == _dump(rrf_fuse(lanes, 5))


def test_lane_mapping_order_does_not_change_output() -> None:
    """lane 的 dict 插入顺序不参与计算：换个顺序仍是同一份输出。"""
    lanes = _three_lane_fixture()
    reversed_lanes = dict(reversed(list(lanes.items())))
    assert _dump(rrf_fuse(lanes, 5)) == _dump(rrf_fuse(reversed_lanes, 5))


def test_score_is_one_over_zero_based_rank_plus_61() -> None:
    """k=61 + 0-based 名次：第 0 名 1/61、第 1 名 1/62（与 haystack 同口径）。"""
    assert RRF_K == 61
    assert rrf_fuse({"a": [_hit("case:X", "a", 0)]}, 1)[0].score == pytest.approx(1 / 61)
    assert rrf_fuse({"a": [_hit("case:X", "a", 1)]}, 1)[0].score == pytest.approx(1 / 62)


def test_long_tail_in_every_lane_does_not_beat_a_first_place() -> None:
    """DoD ②：三路都排第 100 名的候选不得压过某一路的第 1 名。

    不截断时 ``3 × 1/(100+61) = 0.0186 > 1/(0+61) = 0.0164``——正是这个不等式让
    "三路都见过" 冒充 "某一路最相关"。截断到 ``2 × final_k = 20`` 后长尾根本不
    参与计分。
    """
    final_k = 10
    lanes = {
        "law": [
            _hit(FIRST_PLACE, "law", 0),
            *(_hit(f"law:pad:{rank}", "law", rank) for rank in range(1, 100)),
            _hit(LONG_TAIL, "law", 100),
        ],
        "case": [
            *(_hit(f"case:pad:{rank}", "case", rank) for rank in range(1, 100)),
            _hit(LONG_TAIL, "case", 100),
        ],
        "file": [
            *(_hit(f"file:pad:{rank}", "file", rank) for rank in range(1, 100)),
            _hit(LONG_TAIL, "file", 100),
        ],
    }

    fused = rrf_fuse(lanes, final_k)

    # 先证明"不截断就会反转"，再证明实现没有反转。
    assert 3 * (1 / (100 + RRF_K)) > 1 / (0 + RRF_K)
    assert fused[0].key == FIRST_PLACE
    assert LONG_TAIL not in {hit.key for hit in fused}


def test_truncation_counts_positions_not_rank_values() -> None:
    """截断看的是"每路前几条"，不是"名次数字 < D"。

    名次可以稀疏（第 0 条之后直接是第 100 条），但计分只认前 ``2 × final_k`` 条。
    这里把同一份候选在次路上分别放在第 2 位（计入）与第 3 位（被截）：后者只拿到
    主路那一票。补位命中的名次刻意放到 100 以后，保证它们不抢榜首、只用来"占位"。
    """
    final_k = 1
    limit = LANE_TRUNCATION_FACTOR * final_k
    assert limit == 2

    target = case_key("（2020）京01民终7号")  # allowlist secret（合成案号，仅用于测试解析规则）
    padded = [_hit(f"case:pad:{rank}", "b", rank) for rank in (100, 101, 102)]

    kept = rrf_fuse(
        {
            "a": [_hit(target, "a", 0)],
            "b": [*padded[: limit - 1], _hit(target, "b", 103)],
        },
        final_k,
    )
    dropped = rrf_fuse(
        {
            "a": [_hit(target, "a", 0)],
            "b": [*padded[:limit], _hit(target, "b", 104)],
        },
        final_k,
    )

    assert kept[0].key == target
    assert kept[0].hit_count == 2
    assert dropped[0].key == target
    assert dropped[0].hit_count == 1
    assert dropped[0].score == pytest.approx(1 / (0 + RRF_K))


def test_same_text_different_article_is_not_merged() -> None:
    """DoD ③：同文不同法条不误并。

    法条里重复句式极多（两句只差一条），用内容哈希做键会把它们并成一条——等于
    凭空丢掉一条依据。这里两条命中 ``title`` 完全一样，只有业务键不同。
    """
    same_title = "合同解除后，尚未履行的，终止履行；已经履行的，当事人可以请求恢复原状"
    article_7 = statute_key(1, 7)
    article_8 = statute_key(1, 8)
    lanes = {
        "law": [_hit(article_7, "law", 0, same_title), _hit(article_8, "law", 1, same_title)],
        "file": [_hit(article_7, "file", 0, same_title), _hit(article_8, "file", 1, same_title)],
    }

    fused = rrf_fuse(lanes, 10)

    assert [hit.key for hit in fused] == [article_7, article_8]
    assert [hit.hit_count for hit in fused] == [2, 2]


def test_same_key_across_lanes_is_merged_once() -> None:
    """同一条法条被两路各命中一次 → 一条结果、两票（不是两条重复依据）。"""
    key = statute_key(100, 3)
    fused = rrf_fuse({"law": [_hit(key, "law", 0)], "file": [_hit(key, "file", 4)]}, 5)

    assert len(fused) == 1
    assert fused[0].hit_count == 2
    assert fused[0].best_rank == 0
    assert fused[0].lanes == ("file", "law")
    assert fused[0].score == pytest.approx(1 / 61 + 1 / 65)


def test_business_keys_keep_kinds_apart() -> None:
    """``law_id::article_no`` 与 ``file_id::page`` 形状相同，键必须带种类前缀。"""
    assert statute_key(3, 7) != page_key(3, 7)
    assert case_key("（2020）京01民终1号").endswith("（2020）京01民终1号")  # allowlist secret（合成案号，仅用于测试解析规则）
    with pytest.raises(ValueError):
        statute_key("", 7)
    with pytest.raises(ValueError):
        case_key("   ")
    with pytest.raises(ValueError):
        page_key(12, "")


def test_duplicate_key_within_one_lane_votes_once() -> None:
    """一路里同一份材料出现两次：只按该路内最好的名次投一票。"""
    key = case_key("（2020）京01民终3号")  # allowlist secret（合成案号，仅用于测试解析规则）
    fused = rrf_fuse({"a": [_hit(key, "a", 1), _hit(key, "a", 5)]}, 1)

    assert fused[0].hit_count == 1
    assert fused[0].best_rank == 1
    assert fused[0].score == pytest.approx(1 / (1 + RRF_K))


def test_order_is_total_when_score_hit_count_and_best_rank_tie() -> None:
    """三个数值键全同 → 按业务键升序，输出顺序唯一（不依赖 dict 迭代顺序）。"""
    high = statute_key(2, 2)
    low = statute_key(1, 1)
    fused = rrf_fuse({"a": [_hit(high, "a", 0)], "b": [_hit(low, "b", 0)]}, 2)

    assert [hit.key for hit in fused] == [low, high]
    assert fused[0].score == fused[1].score
    assert fused[0].hit_count == fused[1].hit_count
    assert fused[0].best_rank == fused[1].best_rank


def test_lane_field_on_hit_does_not_decide_membership() -> None:
    """``RetrievalHit.lane`` 只是冗余标注：``FusedHit.lanes`` 取映射键。"""
    fused = rrf_fuse({"law": [_hit("case:X", "stale-label", 0)]}, 1)

    assert fused[0].lanes == ("law",)


def test_degenerate_hits_are_dropped_instead_of_raising() -> None:
    """空业务键 / 负名次是上游退化数据：丢掉它们，不让整轮融合失败。"""
    fused = rrf_fuse(
        {"a": [_hit("", "a", 0), _hit(case_key("（2020）京01民终4号"), "a", -1), _hit("case:Y", "a", 0)]},  # allowlist secret（合成案号，仅用于测试解析规则）
        5,
    )

    assert [hit.key for hit in fused] == ["case:Y"]


def test_final_k_caps_output_and_must_be_positive() -> None:
    """``final_k`` 是输出上限；0/负数属于调用方算错，直接报错而不是返回空列表。"""
    lanes = {"a": [_hit(f"case:{rank}", "a", rank) for rank in range(30)]}

    assert len(rrf_fuse(lanes, 3)) == 3
    assert len(rrf_fuse(lanes, 100)) == 30
    with pytest.raises(ValueError):
        rrf_fuse(lanes, 0)
    assert rrf_fuse({}, 5) == []
