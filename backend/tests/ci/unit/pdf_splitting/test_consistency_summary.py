"""一致性检测**接入层**的判据单测：文案按判据种类分、产物形状不许变。

全部数据虚构（测试甲/测试乙… 与示例证件号 110101199001011234）。
真实卷宗里的姓名与证件号不得出现在测试里。

对应契约：
- 接入层**不做业务过滤**，只裁体积、只贴段级提示；
- ``pick_top_inconsistencies`` 只许在原有 6 个键之外**加** ``kind``，不许改名/改语义；
- 实体聚类/证件号提示**不能说「疑似错字」**——那两种判据没有「哪个写法对」的证据。
"""

from __future__ import annotations

from apps.pdf_splitting.services.split.consistency_summary import (
    SUMMARY_INCONSISTENCY_LIMIT,
    attach_quality_flags_to_markdown,
    flag_text,
    flags_for_markdown,
    pick_top_inconsistencies,
)
from apps.pdf_splitting.services.split.cross_page_consistency import (
    KIND_ENTITY_CLUSTER,
    KIND_FREQUENCY,
    KIND_ID_MALFORMED,
    Inconsistency,
)

_FAKE_ID = "110101199001011234"
_FAKE_ID_BROKEN = "1x0101199001011244"


def _hit(
    canonical: str,
    variant: str,
    *,
    kind: str = KIND_FREQUENCY,
    canonical_count: int = 30,
    variant_count: int = 2,
    confidence: str = "high",
) -> Inconsistency:
    return Inconsistency(
        canonical=canonical,
        variant=variant,
        canonical_count=canonical_count,
        variant_count=variant_count,
        pages=[7, 9],
        confidence=confidence,
        kind=kind,
    )


class TestFlagTextPerKind:
    def test_frequency_kind_keeps_original_wording(self) -> None:
        """频次法有「高频写法」这个证据，文案保持原样（既有行为不许改）。"""
        text = flag_text(_hit("经办人", "受办人", canonical_count=178, variant_count=30))

        assert text.startswith("疑似错字：受办人")
        assert "178" in text and "30" in text and "经办人" in text

    def test_entity_cluster_does_not_claim_typo(self) -> None:
        """姓名聚类只能说「写法不一致、请核对」，不能说「疑似错字」。

        簇里各写法频次接近，系统并没有判定哪个对。写成「疑似错字」会让律师
        以为高频那个就是正确的，进而把两个真人合并成一个。
        """
        text = flag_text(_hit("测试甲", "测试乙", kind=KIND_ENTITY_CLUSTER, confidence="medium"))

        assert "疑似错字" not in text
        assert "测试乙" in text and "测试甲" in text
        assert "核对" in text

    def test_id_malformed_states_structural_reason(self) -> None:
        """证件号提示要说明依据是「位数结构不合法」，而不是频次。"""
        text = flag_text(_hit(_FAKE_ID, _FAKE_ID_BROKEN, kind=KIND_ID_MALFORMED, confidence="medium"))

        assert _FAKE_ID_BROKEN in text
        assert "结构不合法" in text
        assert "疑似错字" not in text

    def test_cluster_flag_only_hits_segments_containing_variant(self) -> None:
        """段级提示仍按 variant 精确子串命中，不做模糊匹配。"""
        items = [_hit("测试甲", "测试乙", kind=KIND_ENTITY_CLUSTER, confidence="medium")]

        assert len(flags_for_markdown("# 借款合同\n户名：测试乙", items)) == 1
        assert flags_for_markdown("# 借款合同\n户名：测试甲", items) == []
        assert flags_for_markdown("", items) == []


class TestSummaryShapeUnchanged:
    def test_keys_are_the_existing_six_plus_kind(self) -> None:
        """只许**加** kind 一个键：原有 6 个键的名字与语义不许动（旧前端忽略未知键）。"""
        items = [
            _hit("经办人", "受办人"),
            _hit("测试甲", "测试乙", kind=KIND_ENTITY_CLUSTER, confidence="medium"),
            _hit(_FAKE_ID, _FAKE_ID_BROKEN, kind=KIND_ID_MALFORMED, confidence="medium"),
        ]

        picked = pick_top_inconsistencies(items)

        assert len(picked) == 3
        for entry in picked:
            assert set(entry) == {
                "canonical",
                "variant",
                "canonical_count",
                "variant_count",
                "pages",
                "confidence",
                "kind",
            }

    def test_kind_is_per_item_so_drawer_can_relabel_each_row(self) -> None:
        """kind 必须逐条透出：抽屉要按行换文案，summary 级计数定位不到行。"""
        items = [
            _hit("经办人", "受办人"),
            _hit("测试甲", "测试乙", kind=KIND_ENTITY_CLUSTER, confidence="medium"),
            _hit(_FAKE_ID, _FAKE_ID_BROKEN, kind=KIND_ID_MALFORMED, confidence="medium"),
        ]

        picked = pick_top_inconsistencies(items)

        # 按 variant 认领而不是按下标：排序口径是 (confidence, -variant_count, canonical)，
        # 同级同次数时按 canonical 字典序，位置会随数据变，kind 跟着条目走才是要锁的契约。
        assert {entry["variant"]: entry["kind"] for entry in picked} == {
            "受办人": KIND_FREQUENCY,
            "测试乙": KIND_ENTITY_CLUSTER,
            _FAKE_ID_BROKEN: KIND_ID_MALFORMED,
        }

    def test_high_confidence_sorts_before_medium(self) -> None:
        """排序口径不变：high 在前，medium（实体判据）在后。"""
        items = [
            _hit("测试甲", "测试乙", kind=KIND_ENTITY_CLUSTER, confidence="medium", variant_count=9),
            _hit("经办人", "受办人", variant_count=1),
        ]

        picked = pick_top_inconsistencies(items)

        assert [entry["confidence"] for entry in picked] == ["high", "medium"]

    def test_limit_still_caps_output(self) -> None:
        items = [_hit(f"甲{i:03d}", f"乙{i:03d}") for i in range(SUMMARY_INCONSISTENCY_LIMIT + 20)]

        assert len(pick_top_inconsistencies(items)) == SUMMARY_INCONSISTENCY_LIMIT

    def test_attach_flags_keeps_markdown_and_positioned(self) -> None:
        """就地补 quality_flags，正文与定位框一个字节都不许动。"""
        items = [_hit("测试甲", "测试乙", kind=KIND_ENTITY_CLUSTER, confidence="medium")]
        segments_md = [
            {"order": 1, "markdown": "# 借款合同\n户名：测试乙", "positioned": [{"page": 7}]},
            {"order": 2, "markdown": "# 证据清单\n户名：测试甲", "positioned": []},
        ]

        result = attach_quality_flags_to_markdown(segments_md, items)

        assert result is segments_md
        assert result[0]["quality_flags"]
        assert "疑似错字" not in result[0]["quality_flags"][0]
        assert result[0]["markdown"] == "# 借款合同\n户名：测试乙"
        assert result[0]["positioned"] == [{"page": 7}]
        assert result[1]["quality_flags"] == []
