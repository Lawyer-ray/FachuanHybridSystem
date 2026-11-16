"""材料预处理 md 查找服务测试。

纯助手（draft_segs/seg_page_range/seg_covers_part/to_draft_segment/哈希）不碰库；
编排（find_draft_segments_for_file）用 django_db + mock inbox 侧服务函数，
只验证 cases 侧的哈希匹配与段序输出逻辑（DB 测试由主会话集中跑）。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from apps.cases.services.material import material_draft_md_service as mod
from apps.cases.services.material.material_draft_md_service import (
    MaterialDraftMdService,
    compute_file_sha256,
    draft_segs,
    seg_covers_part,
    seg_page_range,
    to_draft_segment,
)


def _seg(i: int, *, md: str = "正文", mi: int = 0, pages: list[int] | None = None) -> dict:
    ps = pages if pages is not None else [i + 1]
    return {"id": f"s{i}", "fn": f"材料{i}", "md": md, "refs": [{"mi": mi, "p": p} for p in ps]}


class TestPureHelpers:
    def test_draft_segs_filters_non_dict(self) -> None:
        assert draft_segs({"segs": [_seg(0), "坏数据", None]}) == [_seg(0)]
        assert draft_segs(None) == []
        assert draft_segs({}) == []

    def test_seg_page_range_min_max(self) -> None:
        assert seg_page_range(_seg(0, pages=[3, 1, 2])) == (1, 3)
        assert seg_page_range({"refs": []}) == (None, None)

    def test_seg_covers_part(self) -> None:
        assert seg_covers_part(_seg(0, mi=1), 1) is True
        assert seg_covers_part(_seg(0, mi=1), 0) is False

    def test_to_draft_segment_skips_empty_md(self) -> None:
        assert to_draft_segment(_seg(0, md="  ")) is None
        d = to_draft_segment(_seg(0, md="正文", pages=[2, 4]))
        assert d is not None
        assert d.segment_ref == "s0"
        assert d.name == "材料0"
        assert (d.page_start, d.page_end) == (2, 4)
        assert d.md == "正文"

    def test_compute_file_sha256(self, tmp_path: Path) -> None:
        import hashlib

        f = tmp_path / "a.bin"
        f.write_bytes(b"hello world")
        assert compute_file_sha256(f) == hashlib.sha256(b"hello world").hexdigest()

    def test_compute_file_sha256_missing_returns_empty(self, tmp_path: Path) -> None:
        assert compute_file_sha256(tmp_path / "nope.bin") == ""


@pytest.mark.django_db
class TestFindDraftSegmentsOrchestration:
    def _material(self, case, *, file_hash: str, message_id: int | None, ref: str = "s0"):
        from apps.cases.models import CaseMaterial

        return CaseMaterial.objects.create(
            case=case,
            category="party",
            type_name="借款合同",
            source_file_hash=file_hash,
            source_message_id=message_id,
            source_segment_ref=ref,
        )

    def test_segment_level_match_returns_md_in_draft_order(self, case) -> None:
        self._material(case, file_hash="H", message_id=11, ref="s1")
        self._material(case, file_hash="H", message_id=11, ref="s0")
        msg = SimpleNamespace(draft_state={"segs": [_seg(0, md="甲"), _seg(1, md="乙")]}, attachments_meta=[])
        with patch("apps.message_hub.services.inbox_query.get_message_or_none", return_value=msg):
            out = MaterialDraftMdService().find_draft_segments_for_file(case.id, "H")
        # 按草稿段序（s0 先于 s1），不按匹配集合无序遍历
        assert [d.segment_ref for d in out] == ["s0", "s1"]
        assert [d.md for d in out] == ["甲", "乙"]

    def test_no_hash_match_falls_to_pack_level(self, case) -> None:
        self._material(case, file_hash="OTHER", message_id=11, ref="s0")
        msg = SimpleNamespace(
            draft_state={"segs": [_seg(0, md="整包甲", mi=0), _seg(1, md="整包乙", mi=0)]},
            attachments_meta=[{"local_path": "x.pdf", "part_index": 0}],
        )
        with (
            patch("apps.message_hub.services.inbox_query.get_message_or_none", return_value=msg),
            patch("apps.message_hub.services.base.resolve_media_attachment_path", return_value=Path("x.pdf")),
            patch.object(mod, "compute_file_sha256", return_value="H"),
        ):
            out = MaterialDraftMdService().find_draft_segments_for_file(case.id, "H")
        assert [d.md for d in out] == ["整包甲", "整包乙"]

    def test_no_provenance_returns_empty(self, case) -> None:
        self._material(case, file_hash="H", message_id=None)
        assert MaterialDraftMdService().find_draft_segments_for_file(case.id, "H") == []

    def test_empty_hash_short_circuits(self, case) -> None:
        assert MaterialDraftMdService().find_draft_segments_for_file(case.id, "") == []

    def test_deleted_message_degrades(self, case) -> None:
        self._material(case, file_hash="H", message_id=11, ref="s0")
        with patch("apps.message_hub.services.inbox_query.get_message_or_none", return_value=None):
            assert MaterialDraftMdService().find_draft_segments_for_file(case.id, "H") == []

    def test_other_case_hash_not_matched(self, case) -> None:
        from apps.testing.factories import CaseFactory

        other = CaseFactory()
        self._material(other, file_hash="H", message_id=11, ref="s0")
        # 本案无该哈希材料，且本案无溯源消息 → 包级也查不到
        assert MaterialDraftMdService().find_draft_segments_for_file(case.id, "H") == []
