"""`conflict.py`：同一 subpath 内 patch 的互补 / 互斥 / 重复分类。

**为什么锁这个纯函数**：它是"三栏并答不许静默互相覆盖"的唯一判据。判漏了
（把互斥当互补），第二栏的改动会把第一栏踩掉，而且**没有任何报错**——律师看到
的是"AI 说改好了，但文件里只有一栏的改法"。所以这里逐类钉死：

- 区间不相交 → 互补（不产出冲突）；
- 相交且 replacement 不同 → `overlap_diff`；
- 相交且 replacement 相同 → `duplicate`；
- 三份两两相交 → **一条**冲突（不是两条两两冲突：同一处原文，律师要一次裁决完）；
- 包含关系（一栏的原文是另一栏原文的一部分）也算相交——字符串不相等但落笔必然互相踩；
- 定位不到的 patch 不产出冲突（它在应用阶段单独报锚点缺失，混进冲突会误导裁决）。
"""

from __future__ import annotations

from apps.contract_review.services.patch.conflict import detect_conflicts, patch_span, spans_overlap
from tests.ci.unit.contract_review.services.patch.docx_fixtures import (
    CLAUSE_COURT,
    CLAUSE_PAYMENT,
    CLAUSE_PENALTY,
    SUBPATH,
)
from apps.contract_review.services.write_contracts import WritePatch

FULL_TEXT = "\n".join([CLAUSE_PAYMENT, CLAUSE_PENALTY, CLAUSE_COURT])


def _patch(patch_id: str, original: str, replacement: str, subpath: str = SUBPATH) -> WritePatch:
    return WritePatch(
        patch_id=patch_id,
        session_id="s-1",
        turn=1,
        agent_kind="pi",
        run_id=f"run:{patch_id}",
        owner_kind="contract",
        owner_id=1,
        subpath=subpath,
        original=original,
        replacement=replacement,
    )


def _detect(*patches: WritePatch) -> list[dict]:
    conflicts = detect_conflicts(
        list(patches),
        dict.fromkeys({patch.subpath for patch in patches}, FULL_TEXT),
    )
    return [
        {"kind": c.kind, "patch_ids": list(c.patch_ids), "spans": list(c.spans), "summary": c.summary}
        for c in conflicts
    ]


class TestSpan:
    def test_span_of_existing_original(self) -> None:
        start, end = patch_span(FULL_TEXT, CLAUSE_PENALTY) or (-1, -1)
        assert FULL_TEXT[start:end] == CLAUSE_PENALTY

    def test_missing_original_has_no_span(self) -> None:
        assert patch_span(FULL_TEXT, "合同里没有这句话。") is None

    def test_touching_spans_do_not_overlap(self) -> None:
        # 半开区间：A 的结尾正好是 B 的开头不算相交（各改各的）
        assert not spans_overlap((0, 5), (5, 9))
        assert spans_overlap((0, 5), (4, 9))


class TestComplementary:
    def test_disjoint_originals_produce_no_conflict(self) -> None:
        conflicts = _detect(
            _patch("p1", CLAUSE_PAYMENT, "甲方应于十五日内支付货款。"),
            _patch("p2", CLAUSE_COURT, "因本合同产生的争议，由甲方所在地人民法院管辖。"),
        )
        assert conflicts == []

    def test_single_patch_produces_no_conflict(self) -> None:
        assert _detect(_patch("p1", CLAUSE_PENALTY, "违约金按日万分之三计算。")) == []


class TestOverlapDiff:
    def test_same_original_two_rewrites_is_one_mutex_conflict(self) -> None:
        conflicts = _detect(
            _patch("p1", CLAUSE_PAYMENT, "甲方应于十五日内支付货款。"),
            _patch("p2", CLAUSE_PAYMENT, "甲方应于十日内支付货款。"),
        )
        assert len(conflicts) == 1
        assert conflicts[0]["kind"] == "overlap_diff"
        assert conflicts[0]["patch_ids"] == ["p1", "p2"]
        assert conflicts[0]["spans"] == [patch_span(FULL_TEXT, CLAUSE_PAYMENT)] * 2
        assert "互斥" in conflicts[0]["summary"]

    def test_three_lanes_overlapping_is_a_single_conflict(self) -> None:
        """三份两两相交 → 一条冲突（前端只该画一处，而不是画两遍）。"""
        conflicts = _detect(
            _patch("a", CLAUSE_PAYMENT, "甲方应于十五日内支付货款。"),
            _patch("b", CLAUSE_PAYMENT, "甲方应于十日内支付货款。"),
            _patch("c", CLAUSE_PAYMENT, "甲方应于五日内支付货款。"),
        )
        assert len(conflicts) == 1
        assert conflicts[0]["patch_ids"] == ["a", "b", "c"]
        assert len(conflicts[0]["spans"]) == 3

    def test_contained_original_counts_as_overlap(self) -> None:
        """一栏改整句、另一栏只改句中一段：字符串不相等，但落笔必然互相踩。"""
        conflicts = _detect(
            _patch("whole", CLAUSE_PAYMENT, "甲方应于十五日内支付货款。"),
            _patch("part", "三十日内支付货款", "十日内支付货款"),
        )
        assert [c["kind"] for c in conflicts] == ["overlap_diff"]
        assert conflicts[0]["patch_ids"] == ["part", "whole"]


class TestDuplicate:
    def test_same_original_same_replacement_is_duplicate(self) -> None:
        same = "甲方应于十五日内支付货款。"
        conflicts = _detect(_patch("p1", CLAUSE_PAYMENT, same), _patch("p2", CLAUSE_PAYMENT, same))
        assert len(conflicts) == 1
        assert conflicts[0]["kind"] == "duplicate"
        assert "去重" in conflicts[0]["summary"]


class TestUnlocatable:
    def test_patch_whose_original_is_gone_is_not_a_conflict(self) -> None:
        """定位不到 ≠ 冲突：应用阶段会单独报锚点缺失，别让律师裁决没发生的事。"""
        conflicts = _detect(
            _patch("gone", "这句话已经不在文档里了。", "新话。"),
            _patch("alive", CLAUSE_PAYMENT, "甲方应于十五日内支付货款。"),
        )
        assert conflicts == []

    def test_unknown_subpath_is_ignored(self) -> None:
        conflicts = detect_conflicts([_patch("p1", CLAUSE_PAYMENT, "x")], {})
        assert conflicts == []


class TestDeterminism:
    def test_input_order_does_not_change_output(self) -> None:
        patches = [
            _patch("p1", CLAUSE_PAYMENT, "甲方应于十五日内支付货款。"),
            _patch("p2", CLAUSE_PAYMENT, "甲方应于十日内支付货款。"),
        ]
        assert _detect(*patches) == _detect(*reversed(patches))
