"""`classify`：互补 / 互斥 / 漏项 / 待人工 / 行级兜底。

三类主判据之外，这里专门锁两条容易"为了绿而绿"的规则：

1. **同一条款内区间不交叠、但改法不同 → ``manual``，不是 ``complementary``。**
   文本不冲突不等于法律效果不冲突；代码不许替律师判断哪句更强。
2. **行级降级时 ``clause_key`` 必须是 ``None``。** 把 ``L1`` 当条款坐标会让
   前端画出一条不存在的"第一条冲突"。
"""

from __future__ import annotations

from apps.contract_review.services.alignment.classify import classify_patches
from apps.contract_review.services.alignment.clause_split import split_clauses
from apps.contract_review.services.write_contracts import WritePatch

SUBPATH = "1-合同/alignment-test.docx"

TEXT = "\n".join(
    [
        "第一条 合同标的",
        "甲方向乙方采购设备十台。",
        "第二条 付款方式",
        "甲方应于收到发票后三十日内支付货款。",
        "第三条 违约责任",
        "乙方逾期交货的，按日万分之五支付违约金。",
        "第四条 争议解决",
        "因本合同产生的争议，提交乙方所在地仲裁委员会仲裁。仲裁裁决为终局裁决。",
        "第五条 保密",
        "双方应对本合同内容保密。",
    ]
)

CLAUSE_ONE = "甲方向乙方采购设备十台。"
CLAUSE_TWO = "甲方应于收到发票后三十日内支付货款。"
CLAUSE_THREE = "乙方逾期交货的，按日万分之五支付违约金。"
CLAUSE_FOUR_FIRST = "因本合同产生的争议，提交乙方所在地仲裁委员会仲裁。"
CLAUSE_FOUR_SECOND = "仲裁裁决为终局裁决。"

LINE_TEXT = "甲方应于三十日内付款\n乙方应于十日内交货\n争议提交仲裁"


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


def _classify(
    patches: list[WritePatch],
    text: str = TEXT,
    checklist: list[str] | None = None,
    subpath: str = SUBPATH,
) -> AlignmentReport:
    return classify_patches(patches, {subpath: text}, {subpath: checklist or []})


class TestComplementary:
    def test_patches_on_different_clauses_are_complementary(self) -> None:
        report = _classify(
            [
                _patch("p1", CLAUSE_ONE, "甲方向乙方采购设备十二台。"),
                _patch("p2", CLAUSE_TWO, "甲方应于收到发票后十五日内支付货款。"),
            ]
        )

        assert report.conflicts == ()
        assert [outcome.status for outcome in report.outcomes] == ["complementary", "complementary"]
        assert [outcome.clause_key for outcome in report.outcomes] == ["第一条", "第二条"]
        assert report.counts()["complementary"] == 2

    def test_same_clause_disjoint_same_replacement_is_complementary(self) -> None:
        report = _classify(
            [
                _patch("p1", CLAUSE_FOUR_FIRST, "争议提交甲方所在地仲裁委员会仲裁。"),
                _patch("p2", CLAUSE_FOUR_SECOND, "争议提交甲方所在地仲裁委员会仲裁。"),
            ]
        )

        assert report.conflicts == ()
        assert [outcome.status for outcome in report.outcomes] == ["complementary"]
        assert report.outcomes[0].clause_key == "第四条"


class TestOverlapDiff:
    def test_same_clause_overlap_different_replacement_is_mutex(self) -> None:
        report = _classify(
            [
                _patch("p1", CLAUSE_THREE, "乙方逾期交货的，按日万分之三支付违约金。"),
                _patch("p2", CLAUSE_THREE, "乙方逾期交货的，按日万分之十支付违约金。"),
            ]
        )

        assert len(report.conflicts) == 1
        conflict = report.conflicts[0]
        assert conflict.kind == "overlap_diff"
        assert conflict.clause_key == "第三条"
        assert conflict.patch_ids == ("p1", "p2")
        assert conflict.spans[0] == conflict.spans[1]
        assert "互斥" in conflict.summary
        assert report.outcomes[0].needs_manual is True

    def test_three_lanes_overlapping_is_one_conflict(self) -> None:
        report = _classify(
            [
                _patch("a", CLAUSE_THREE, "乙方逾期交货的，按日万分之三支付违约金。"),
                _patch("b", CLAUSE_THREE, "乙方逾期交货的，按日万分之五支付违约金。"),
                _patch("c", CLAUSE_THREE, "乙方逾期交货的，按日万分之十支付违约金。"),
            ]
        )

        assert len(report.conflicts) == 1
        assert report.conflicts[0].patch_ids == ("a", "b", "c")
        assert len(report.conflicts[0].spans) == 3


class TestDuplicate:
    def test_same_clause_same_replacement_is_duplicate(self) -> None:
        same = "乙方逾期交货的，按日万分之三支付违约金。"
        report = _classify([_patch("p1", CLAUSE_THREE, same), _patch("p2", CLAUSE_THREE, same)])

        assert len(report.conflicts) == 1
        assert report.conflicts[0].kind == "duplicate"
        assert "去重" in report.conflicts[0].summary


class TestMissing:
    def test_checklist_hit_without_patch_is_missing(self) -> None:
        report = _classify([], checklist=["第五条"])

        assert len(report.conflicts) == 1
        conflict = report.conflicts[0]
        assert conflict.kind == "missing"
        assert conflict.clause_key == "第五条"
        assert conflict.patch_ids == ()
        assert conflict.spans == ()
        assert "漏项" in conflict.summary

    def test_checklist_key_not_in_text_is_still_missing(self) -> None:
        report = _classify([], checklist=["第九条"])

        assert len(report.conflicts) == 1
        assert report.conflicts[0].kind == "missing"
        assert "未找到" in report.conflicts[0].summary


class TestManual:
    def test_same_clause_disjoint_different_replacement_is_manual_not_complementary(self) -> None:
        report = _classify(
            [
                _patch("p1", CLAUSE_FOUR_FIRST, "争议提交甲方所在地仲裁委员会仲裁。"),
                _patch("p2", CLAUSE_FOUR_SECOND, "仲裁裁决不是终局裁决，任何一方均可起诉。"),
            ]
        )

        assert len(report.conflicts) == 1
        assert report.conflicts[0].kind == "overlap_diff"
        assert "待人工" in report.conflicts[0].summary
        assert [outcome.status for outcome in report.outcomes] == ["manual"]
        outcome = report.outcomes[0]
        assert outcome.clause_key == "第四条"
        assert outcome.needs_manual is True
        assert "待人工" in outcome.summary
        assert "法律效果" in outcome.summary

    def test_cross_clause_patch_is_manual_with_no_clause_key(self) -> None:
        report = _classify(
            [
                _patch(
                    "p1",
                    "甲方向乙方采购设备十台。\n第二条 付款方式",
                    "甲方向乙方采购设备十二台。",
                )
            ]
        )

        assert report.conflicts == ()
        assert [outcome.status for outcome in report.outcomes] == ["manual"]
        assert report.outcomes[0].clause_key is None


class TestLineFallback:
    def test_line_level_never_claims_clause_key(self) -> None:
        split = split_clauses(LINE_TEXT)
        assert split.aligned is False
        assert split.granularity == "line"

        report = _classify(
            [
                _patch("p1", "甲方应于三十日内付款", "甲方应于十日内付款", subpath="1-合同/line.docx"),
                _patch("p2", "乙方应于十日内交货", "乙方应于五日内交货", subpath="1-合同/line.docx"),
            ],
            text=LINE_TEXT,
            subpath="1-合同/line.docx",
        )

        assert report.conflicts == ()
        assert all(outcome.clause_key is None for outcome in report.outcomes)
        assert [outcome.status for outcome in report.outcomes] == ["complementary", "complementary"]

    def test_line_level_same_line_overlap_still_conflicts_without_clause_key(self) -> None:
        subpath = "1-合同/line.docx"
        report = _classify(
            [
                _patch("p1", "甲方应于三十日内付款", "甲方应于十日内付款", subpath=subpath),
                _patch("p2", "甲方应于三十日内付款", "甲方应于五日内付款", subpath=subpath),
            ],
            text=LINE_TEXT,
            subpath=subpath,
        )

        assert len(report.conflicts) == 1
        assert report.conflicts[0].kind == "overlap_diff"
        assert report.conflicts[0].clause_key is None

    def test_line_level_checklist_cannot_produce_missing(self) -> None:
        subpath = "1-合同/line.docx"
        report = _classify([], text=LINE_TEXT, checklist=["第五条"], subpath=subpath)

        assert report.conflicts == ()
        assert report.outcomes == ()
        assert any("清单漏项无法按条款判定" in note for note in report.notes)


class TestUnlocated:
    def test_patch_not_found_in_text_is_unlocated_not_conflict(self) -> None:
        report = _classify([_patch("p1", "合同里没有这句话。", "随便改。")])

        assert report.conflicts == ()
        assert [outcome.status for outcome in report.outcomes] == ["unlocated"]
        assert report.outcomes[0].clause_key is None

    def test_missing_text_reports_unlocated_and_note(self) -> None:
        report = classify_patches([_patch("p1", CLAUSE_ONE, "改。")], {}, None)

        assert [outcome.status for outcome in report.outcomes] == ["unlocated"]
        assert any("全文缺失" in note for note in report.notes)
