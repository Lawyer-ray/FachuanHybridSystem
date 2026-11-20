"""`diff3`：same / a / b / conflict 四类 + 相邻修改不误判。

为什么逐类钉死：合并结果直接决定律师要不要裁决。把 ``b``（只有 THEIRS 改）
误判成 ``conflict`` 是"让律师白看一条"；把 ``conflict`` 误判成 ``a`` 更糟——
那等于**静默选边**，把三栏并答变成某一栏的独角戏。

相邻修改（OURS 改前一个字、THEIRS 改后一个字）是最容易误判的一类：只看 sync
region 时两处改动会掉进同一个 gap，必须再按 BASE 坐标上的 opcode 区间确认
"确实不相交"才允许分别合并。
"""

from __future__ import annotations

from apps.contract_review.services.alignment.diff3 import MergeResult, diff3


def _kinds(result: MergeResult) -> list[str]:
    return [hunk.kind for hunk in result.hunks]


def _assert_hunks_cover_base(base: str, result: MergeResult) -> None:
    position = 0
    for hunk in result.hunks:
        assert hunk.base_start == position
        assert hunk.base_text == base[hunk.base_start : hunk.base_end]
        position = hunk.base_end
    assert position == len(base)


class TestSame:
    def test_unchanged_text_is_a_single_same_hunk(self) -> None:
        result = diff3("abc", "abc", "abc")

        assert _kinds(result) == ["same"]
        assert result.conflicts == ()
        assert result.merged_text == "abc"
        _assert_hunks_cover_base("abc", result)

    def test_both_sides_make_the_same_change_is_same(self) -> None:
        result = diff3("abc", "aXc", "aXc")

        assert "conflict" not in _kinds(result)
        assert result.conflicts == ()
        assert result.merged_text == "aXc"
        _assert_hunks_cover_base("abc", result)


class TestOnlyOurs:
    def test_only_ours_changed_is_kind_a(self) -> None:
        result = diff3("abc", "abcX", "abc")

        assert _kinds(result) == ["same", "a"]
        assert result.conflicts == ()
        assert result.merged_text == "abcX"
        _assert_hunks_cover_base("abc", result)


class TestOnlyTheirs:
    def test_only_theirs_changed_is_kind_b(self) -> None:
        result = diff3("abc", "abc", "abcY")

        assert _kinds(result) == ["same", "b"]
        assert result.conflicts == ()
        assert result.merged_text == "abcY"
        _assert_hunks_cover_base("abc", result)


class TestConflict:
    def test_overlapping_different_changes_conflict_with_base_coordinates(self) -> None:
        result = diff3("abc", "aXc", "aYc")

        assert _kinds(result) == ["same", "conflict", "same"]
        assert result.conflicts == ((1, 2),)
        assert result.has_conflicts is True
        assert result.merged_text is None
        _assert_hunks_cover_base("abc", result)

    def test_different_insertions_at_same_point_conflict(self) -> None:
        result = diff3("abc", "aXbc", "aYbc")

        assert _kinds(result) == ["same", "conflict", "same"]
        assert result.conflicts == ((1, 1),)
        assert result.merged_text is None
        _assert_hunks_cover_base("abc", result)

    def test_both_insert_different_text_into_empty_base_conflicts(self) -> None:
        result = diff3("", "X", "Y")

        assert _kinds(result) == ["conflict"]
        assert result.conflicts == ((0, 0),)
        assert result.merged_text is None


class TestAdjacentEdits:
    def test_adjacent_changes_merge_without_false_conflict(self) -> None:
        # OURS 改 c→X，THEIRS 改 d→Y；两处在 BASE 坐标上相邻但不重叠。
        result = diff3("abcd", "abXd", "abcY")

        assert _kinds(result) == ["same", "a", "b"]
        assert result.conflicts == ()
        assert result.merged_text == "abXY"
        _assert_hunks_cover_base("abcd", result)

    def test_two_adjacent_replacements_at_the_start(self) -> None:
        result = diff3("abc", "Xbc", "aYc")

        assert _kinds(result) == ["a", "b", "same"]
        assert result.conflicts == ()
        assert result.merged_text == "XYc"
        _assert_hunks_cover_base("abc", result)

    def test_single_side_insertion_next_to_other_side_replacement(self) -> None:
        # THEIRS 在 b 前插入 Y，OURS 把 b 换成 X：边界相接，可合并。
        result = diff3("abc", "aXc", "aYbc")

        assert result.conflicts == ()
        assert result.merged_text == "aYXc"
        _assert_hunks_cover_base("abc", result)
