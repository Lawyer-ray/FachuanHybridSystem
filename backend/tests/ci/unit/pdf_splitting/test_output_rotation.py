"""输出侧页旋转（`services/split/output_rotation.py`）。

律师扫描卡纸时会把整叠纸倒着（180°）送进扫描仪，扫出来每页都是倒的；在阅读器里
人工点「转正」只改前端草稿，**PDF 文件一个字节都没变**。于是「我看着正了」与
「发给客户的 PDF 还是倒的」会同时成立，而且没人会再看第二眼。这个模块就是那些
出口（切页归案 / 归档进卷宗 / 单段下载 / 整包下载）共用的烧入实现。

按后果钉五件事：

1. **叠加而非覆盖**：源 PDF 自带 `/Rotate 90` 时再转 90 必须读回 **180**——
   写成覆盖会把一页正常纸转倒（这是本模块最容易犯、也最难被肉眼发现的错）；
2. 脏输入（`"3:45"`、全角数字、越界页号）**忽略 + 告警**，不能让律师丢掉一份
   已经切好的卷宗；
3. 跨段合并：同一绝对页被两段给了不同角度 → 后者生效 **且** 告警留痕；
4. 增量 0 是「撤销」，不计入「改过几页」；
5. 与同层 `page_rotation.py`（PaddleOCR 转正帧回写、逆时针为正、纯数学）是
   **两套约定**，不许互相传值——这里用一条显式断言把「顺时针」钉住。
"""

from __future__ import annotations

import io
import logging
from typing import Any

import pytest

from apps.pdf_splitting.services.split.output_rotation import (
    ROTATION_STEPS,
    apply_page_rotations,
    merge_page_rotations,
    parse_page_rotations,
)


def _pdf(*, rotations: list[int] | None = None) -> bytes:
    """造一份 N 页合成 PDF（可指定每页初始 /Rotate），模拟「扫描件本来就带旋转」。"""
    import pymupdf as fitz

    doc = fitz.open()
    for deg in rotations or [0]:
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 96), f"第 {deg} 度页")
        if deg:
            page.set_rotation(deg)
    data = doc.tobytes()
    doc.close()
    return data


def _open(data: bytes) -> Any:
    import pymupdf as fitz

    return fitz.open(stream=data, filetype="pdf")


class TestParsePageRotations:
    def test_empty_and_blank_are_no_rotation(self) -> None:
        assert parse_page_rotations("") == {}
        assert parse_page_rotations("   ") == {}
        assert parse_page_rotations(None) == {}  # type: ignore[arg-type]

    def test_parses_page_angle_pairs(self) -> None:
        assert parse_page_rotations("1:90,3:180,7:270") == {1: 90, 3: 180, 7: 270}

    def test_zero_is_kept(self) -> None:
        # 0 有意义：它把同一页更早给的增量撤销掉（跨段合并要靠它）
        assert parse_page_rotations("2:0") == {2: 0}

    def test_tolerates_whitespace(self) -> None:
        assert parse_page_rotations(" 1 : 90 , 2:180 ") == {1: 90, 2: 180}

    def test_same_page_later_wins(self) -> None:
        assert parse_page_rotations("1:90,1:270") == {1: 270}

    @pytest.mark.parametrize(
        "raw",
        ["3:45", "0:90", "-3:90", "abc", "3", "3:", ":90", "３:90", "3.0:90", "3:90x"],
    )
    def test_dirty_tokens_are_ignored_not_raised(self, raw: str, caplog: pytest.LogCaptureFixture) -> None:
        # 旋转是「让人看正」的辅助信息，脏值不该让整份卷宗失败
        with caplog.at_level(logging.WARNING):
            assert parse_page_rotations(raw) == {}
        assert any("pdf_split_page_rotation_ignored" in r.getMessage() for r in caplog.records)

    def test_one_bad_token_does_not_drop_the_others(self) -> None:
        assert parse_page_rotations("1:90,bad,3:180") == {1: 90, 3: 180}


class TestMergePageRotations:
    def test_merges_segments_into_one_table(self) -> None:
        assert merge_page_rotations(["1:90", "3:180", ""]) == {1: 90, 3: 180}

    def test_conflict_later_segment_wins_and_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        """同页两个角度说明调用方页区间算错了：取后者，但必须在日志里留痕。"""
        with caplog.at_level(logging.WARNING):
            merged = merge_page_rotations(["1:90", "1:270"])
        assert merged == {1: 270}
        assert any("pdf_split_page_rotation_conflict" in r.getMessage() for r in caplog.records)

    def test_same_value_twice_is_not_a_conflict(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            assert merge_page_rotations(["1:90", "1:90"]) == {1: 90}
        assert not [r for r in caplog.records if "conflict" in r.getMessage()]


class TestApplyPageRotations:
    def test_burns_rotation_into_page(self) -> None:
        doc = _open(_pdf(rotations=[0, 0]))
        assert apply_page_rotations(doc, {2: 90}) == 1
        assert int(doc.load_page(1).rotation) == 90
        assert int(doc.load_page(0).rotation) == 0
        doc.close()

    def test_stacks_on_top_of_existing_rotate(self) -> None:
        """源页 /Rotate 90 + 人工 90 → 读回 180（不是 90）。

        写成覆盖的实现在这里就会绿着走进生产：一页本来是正的纸被转倒，而
        律师只在收到客户投诉时才发现。
        """
        doc = _open(_pdf(rotations=[90]))
        assert int(doc.load_page(0).rotation) == 90
        apply_page_rotations(doc, {1: 90})
        assert int(doc.load_page(0).rotation) == 180
        doc.close()

    def test_clockwise_direction_is_pinned(self) -> None:
        """同层 `page_rotation.py` 的 θ 是**逆时针**为正，这里是**顺时针**增量。

        两个 90 恰好互相抵消符号错误，肉眼极难发现——所以直接把旋向钉住：
        顺时针转 90 后，原左下角的点应该跑到左上角。用 pymupdf 的
        `page.rotation_matrix` 反推「原页坐标 → 显示坐标」即可判定。
        """
        import pymupdf as fitz

        doc = _open(_pdf(rotations=[0]))
        page = doc.load_page(0)
        apply_page_rotations(doc, {1: 90})
        page = doc.load_page(0)
        # rotation_matrix 把原页坐标映射到显示坐标；顺时针 90° 时 (x, y) → (H-y, x)
        matrix = page.rotation_matrix
        shown = fitz.Point(0, 0) * matrix
        assert shown.x == pytest.approx(842, abs=1)  # 原序号 (0,0) 到显示页的右侧
        assert shown.y == pytest.approx(0, abs=1)
        doc.close()

    def test_zero_undoes_and_is_not_counted(self) -> None:
        doc = _open(_pdf(rotations=[90]))
        # 增量 0 视为「撤销」：不写 /Rotate，也不算「改过一页」
        assert apply_page_rotations(doc, {1: 0}) == 0
        assert int(doc.load_page(0).rotation) == 90  # 保持源文件原样，由调用方决定写 0
        doc.close()

    def test_out_of_range_page_is_ignored_with_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        doc = _open(_pdf(rotations=[0]))
        with caplog.at_level(logging.WARNING):
            assert apply_page_rotations(doc, {9: 90}) == 0
        assert any(
            "page_out_of_range" in str(r.__dict__.get("reason", "")) or "out_of_range" in r.getMessage()
            for r in caplog.records
        )
        doc.close()

    def test_illegal_angle_is_ignored(self) -> None:
        doc = _open(_pdf(rotations=[0]))
        assert apply_page_rotations(doc, {1: 45}) == 0
        assert int(doc.load_page(0).rotation) == 0
        doc.close()

    def test_empty_table_is_noop(self) -> None:
        doc = _open(_pdf(rotations=[0]))
        assert apply_page_rotations(doc, {}) == 0
        assert apply_page_rotations(doc, None) == 0
        doc.close()

    def test_rotation_survives_pdf_export_roundtrip(self) -> None:
        """真正要紧的性质：烧进去之后另存/切页，字节里的 /Rotate 还在。"""
        doc = _open(_pdf(rotations=[0]))
        apply_page_rotations(doc, {1: 180})
        out = io.BytesIO(doc.tobytes())
        doc.close()
        reopened = _open(out.getvalue())
        assert int(reopened.load_page(0).rotation) == 180
        reopened.close()

    def test_rotation_steps_are_the_four_right_angles(self) -> None:
        assert ROTATION_STEPS == (0, 90, 180, 270)
