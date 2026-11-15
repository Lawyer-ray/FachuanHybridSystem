"""双引擎**定位数据**归一化的单测（EngineBlock / normalize_* / link_*）。

与 ``test_dual_engine.py`` 分开的原因：那个文件只覆盖 ``compare_pages`` 的判据
（什么算分歧、算什么等级），本文件只覆盖「两引擎的块坐标怎么变成前端能画的
统一结构」。两者由不同实现负责、改动节奏也不同，放一个文件里会互相覆盖。

数据一律虚构：示例机构 / 张三丰 / 李四 / 110101199001011234（明显假号）。
"""

from __future__ import annotations

from apps.document_parsing.protocols.document_parser_protocol import ParsedBlock
from apps.pdf_splitting.services.split.dual_engine import (
    ENGINE_MINERU,
    ENGINE_PADDLEOCR_VL,
    KIND_CHAR,
    KIND_MISSING,
    SEVERITY_HIGH,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    EngineBlock,
    EngineDisagreement,
    EngineVariant,
    link_disagreement_to_blocks,
    normalize_mineru_blocks,
    normalize_paddleocr_vl_blocks,
)

# ---------------------------------------------------------------------------

#: MinerU 页面尺寸：真实值取 layout["pages"][]["width"/"height"]
MINERU_PAGE_SIZES = {1: {"page_no": 1, "width": 1200, "height": 1976}}


def _mineru_block(text: str, bbox: list[float] | None, page_no: int = 1, block_type: str = "text") -> ParsedBlock:
    return ParsedBlock(type=block_type, text=text, bbox=bbox, page_no=page_no)


def _vl_pruned(
    blocks: list[dict],
    *,
    width: int | None = 1200,
    height: int | None = 1976,
) -> dict:
    """构造 VL 的 prunedResult 结构（真实字段名：width/height/parsing_res_list）。"""
    pruned: dict = {"parsing_res_list": blocks}
    if width is not None:
        pruned["width"] = width
    if height is not None:
        pruned["height"] = height
    return pruned


def test_mineru_blocks_normalized_to_unit_rect() -> None:
    """千分比 bbox → 0-1 矩形（除以 1000），不除以页面尺寸，且 approx=False。"""
    blocks = [_mineru_block("示例机构借款合同", [100, 60, 900, 130], block_type="title")]

    out = normalize_mineru_blocks(blocks, MINERU_PAGE_SIZES)

    assert len(out) == 1
    item = out[0]
    assert isinstance(item, EngineBlock)
    assert item.engine == ENGINE_MINERU
    assert item.page_no == 1
    assert item.block_type == "title"
    assert item.approx is False
    assert item.rect == {"x": 0.1, "y": 0.06, "w": 0.8, "h": 0.07}


def test_mineru_permille_bbox_ignores_page_size() -> None:
    """千分比换算与页面尺寸无关：给出、不给、给个离谱的尺寸，结果必须一致。

    这是本模块最容易复发的 bug：MinerU 的 page_size 是点（612×1008 之类），
    bbox 却是千分比，两者相除会把框挤扁到左上一小块。
    """
    blocks = [_mineru_block("地址：顺德区杏坛镇新齐宁路东侧六号之一", [35, 88, 980, 738])]

    with_size = normalize_mineru_blocks(blocks, MINERU_PAGE_SIZES)
    without_size = normalize_mineru_blocks(blocks, {})

    assert with_size[0].rect == {"x": 0.035, "y": 0.088, "w": 0.945, "h": 0.65}
    assert without_size[0].rect == with_size[0].rect
    assert without_size[0].approx is False


def test_mineru_slightly_out_of_range_permille_stays_permille() -> None:
    """轻微越界的千分比框（>1000 但远不到 2000）仍按千分比，不能被当成像素除烂。

    门框取 2000 而不是 1000 就是为了这个场景：引擎给越界坐标（多边形外接矩形、
    跨页拼接）时，按 1000 判定会被误判成像素，再被页宽除成一条细线。
    """
    blocks = [_mineru_block("轻微越界千分比块", [209, 89, 1066, 118])]

    out = normalize_mineru_blocks(blocks, MINERU_PAGE_SIZES)

    assert out[0].rect == {"x": 0.209, "y": 0.089, "w": 0.791, "h": 0.029}
    assert out[0].approx is False


def test_mineru_absolute_pixel_bbox_detected_by_magnitude() -> None:
    """坐标量级超过 2000 → 判定为绝对像素，按页宽高换算。"""
    # 1200×1976 页面上 300 DPI 级别的框：x 最大 2400 > 2000，只能是绝对像素
    blocks = [_mineru_block("本地 pipeline 块", [200, 120, 2400, 260])]

    out = normalize_mineru_blocks(blocks, MINERU_PAGE_SIZES)

    # 1200×1976 页面：[200,120] → 0.1667/0.0607，宽 2200/1200、高 140/1976
    assert out[0].rect == {"x": 0.1667, "y": 0.0607, "w": 0.8333, "h": 0.0709}
    assert out[0].approx is False


def test_mineru_absolute_pixel_without_page_size_returns_empty_rect_and_approx() -> None:
    """判定为绝对像素但缺页面尺寸 → rect 空 + approx=True，绝不按错单位画。"""
    blocks = [_mineru_block("本地 pipeline 块", [200, 120, 2400, 260])]

    out = normalize_mineru_blocks(blocks, {})

    assert len(out) == 1
    assert out[0].rect == {}
    assert out[0].approx is True


def test_mineru_out_of_bounds_permille_coords_are_clamped() -> None:
    """负越界坐标（多边形外接矩形算错）clamp 回 0-1，而不是画到页外。"""
    blocks = [_mineru_block("越界坐标块", [-50, -20, 980, 990])]

    out = normalize_mineru_blocks(blocks, MINERU_PAGE_SIZES)

    assert out[0].rect == {"x": 0.0, "y": 0.0, "w": 0.98, "h": 0.99}


def test_mineru_skips_empty_text_and_empty_bbox() -> None:
    """空文本 / 空 bbox 的块跳过（画不出来也没内容）。"""
    blocks = [
        _mineru_block("正常块", [100, 200, 600, 250]),
        _mineru_block("", [100, 200, 600, 250]),
        _mineru_block("无坐标块", None),
    ]

    out = normalize_mineru_blocks(blocks, MINERU_PAGE_SIZES)

    assert [item.text for item in out] == ["正常块"]


def test_vl_blocks_normalized_from_pruned_result() -> None:
    """VL prunedResult → 0-1 矩形；页号按 layoutParsingResults 下标 +1。"""
    pruned = _vl_pruned(
        [
            {
                "block_label": "doc_title",
                "block_content": "示例机构借款合同",
                "block_bbox": [262, 73, 921, 131],
                "block_id": 0,
                "block_order": 1,
                "group_id": 0,
                "block_polygon_points": [[262.0, 73.0], [921.0, 73.0], [921.0, 131.0], [262.0, 131.0]],
            }
        ]
    )

    out = normalize_paddleocr_vl_blocks([pruned])

    assert len(out) == 1
    item = out[0]
    assert item.engine == ENGINE_PADDLEOCR_VL
    assert item.page_no == 1
    assert item.block_type == "doc_title"
    assert item.approx is False
    assert item.rect == {"x": 0.2183, "y": 0.0369, "w": 0.5492, "h": 0.0294}


def test_vl_missing_page_size_returns_empty_rect_and_approx() -> None:
    """VL 缺 width/height → rect 空 + approx=True（同 MinerU 处置）。"""
    pruned = _vl_pruned(
        [
            {
                "block_label": "text",
                "block_content": "身份证号码：110101199001011234",
                "block_bbox": [1200, 1950, 2400, 1990],
            }
        ],
        width=None,
        height=None,
    )

    out = normalize_paddleocr_vl_blocks([pruned])

    assert out[0].rect == {}
    assert out[0].approx is True


def test_vl_falls_back_to_polygon_and_skips_empty() -> None:
    """无 block_bbox 时退回多边形外接矩形；空文本 / 无坐标块跳过。"""
    pruned = _vl_pruned(
        [
            {"block_label": "text", "block_content": "   ", "block_bbox": [1, 2, 3, 4]},
            {"block_label": "table", "block_content": "|a|b|", "block_bbox": None},
            {
                "block_label": "text",
                "block_content": "仅多边形块",
                "block_polygon_points": [[10, 10], [110, 10], [110, 60], [10, 60]],
            },
        ]
    )

    out = normalize_paddleocr_vl_blocks([pruned])

    assert [item.text for item in out] == ["仅多边形块"]
    assert out[0].rect == {"x": 0.0083, "y": 0.0051, "w": 0.0833, "h": 0.0253}


def test_vl_page_no_follows_result_index() -> None:
    """VL 块不带页码，只能靠 layoutParsingResults 顺序定位。"""
    results = [
        _vl_pruned([{"block_label": "text", "block_content": "第一页正文", "block_bbox": [0, 0, 100, 100]}]),
        _vl_pruned([{"block_label": "text", "block_content": "第二页正文", "block_bbox": [0, 0, 100, 100]}]),
    ]

    out = normalize_paddleocr_vl_blocks(results)

    assert [(item.page_no, item.text) for item in out] == [(1, "第一页正文"), (2, "第二页正文")]


def test_link_matches_both_engines_by_text_containment() -> None:
    """一条分歧按文本包含关系挂回两引擎各自的块（真实分歧：罗浩瑜 / 罗若瑜）。"""
    mineru_blocks = normalize_mineru_blocks(
        [
            _mineru_block("示例机构借款合同", [100, 60, 1100, 130], block_type="title"),
            _mineru_block("借款人：罗浩瑜", [100, 200, 600, 250]),
        ],
        MINERU_PAGE_SIZES,
    )
    vl_blocks = normalize_paddleocr_vl_blocks(
        [_vl_pruned([{"block_label": "text", "block_content": "借款人：罗若瑜", "block_bbox": [100, 200, 600, 250]}])]
    )
    disagreement = EngineDisagreement(
        page_no=1,
        kind=KIND_CHAR,
        severity=SEVERITY_HIGH,
        variants=[
            EngineVariant(engine=ENGINE_MINERU, text="借款人：罗浩瑜"),
            EngineVariant(engine=ENGINE_PADDLEOCR_VL, text="借款人：罗若瑜"),
        ],
        context="借款人：罗浩瑜",
        anchor_hit=True,
        similarity=0.85,
    )

    linked = link_disagreement_to_blocks(disagreement, {ENGINE_MINERU: mineru_blocks, ENGINE_PADDLEOCR_VL: vl_blocks})

    assert linked[ENGINE_MINERU] is not None
    assert linked[ENGINE_MINERU].text == "借款人：罗浩瑜"
    assert linked[ENGINE_PADDLEOCR_VL] is not None
    assert linked[ENGINE_PADDLEOCR_VL].text == "借款人：罗若瑜"


def test_link_returns_none_when_no_text_match() -> None:
    """匹配不上就返回 None——不猜框（错框比没框更误导）。"""
    blocks = normalize_mineru_blocks([_mineru_block("借款人：张三丰", [100, 200, 600, 250])], MINERU_PAGE_SIZES)
    disagreement = EngineDisagreement(
        page_no=1,
        kind=KIND_CHAR,
        severity=SEVERITY_MEDIUM,
        variants=[EngineVariant(engine=ENGINE_MINERU, text="完全不相干的另一段话")],
        context="完全不相干的另一段话",
    )

    assert link_disagreement_to_blocks(disagreement, {ENGINE_MINERU: blocks}) == {ENGINE_MINERU: None}


def test_link_returns_none_for_wrong_page_and_short_variant() -> None:
    """页码不符 / 变体过短（<3 字，几乎必然被任意块包含）→ None。"""
    blocks = normalize_mineru_blocks([_mineru_block("借款人：罗浩瑜", [100, 200, 600, 250])], MINERU_PAGE_SIZES)

    wrong_page = EngineDisagreement(
        page_no=2,
        kind=KIND_CHAR,
        severity=SEVERITY_MEDIUM,
        variants=[EngineVariant(engine=ENGINE_MINERU, text="借款人：罗浩瑜")],
        context="借款人：罗浩瑜",
    )
    short = EngineDisagreement(
        page_no=1,
        kind=KIND_CHAR,
        severity=SEVERITY_MEDIUM,
        variants=[EngineVariant(engine=ENGINE_MINERU, text="李四")],
        context="李四",
    )

    assert link_disagreement_to_blocks(wrong_page, {ENGINE_MINERU: blocks}) == {ENGINE_MINERU: None}
    assert link_disagreement_to_blocks(short, {ENGINE_MINERU: blocks}) == {ENGINE_MINERU: None}


def test_link_missing_variant_keeps_that_engine_none() -> None:
    """missing 类分歧里某引擎变体为空串：该引擎没识别出这段，保持 None（只画另一侧的框）。"""
    mineru_blocks = normalize_mineru_blocks([_mineru_block("借款人：罗浩瑜", [100, 200, 600, 250])], MINERU_PAGE_SIZES)
    disagreement = EngineDisagreement(
        page_no=1,
        kind=KIND_MISSING,
        severity=SEVERITY_LOW,
        variants=[
            EngineVariant(engine=ENGINE_MINERU, text="借款人：罗浩瑜"),
            EngineVariant(engine=ENGINE_PADDLEOCR_VL, text=""),
        ],
        context="借款人：罗浩瑜",
    )

    linked = link_disagreement_to_blocks(disagreement, {ENGINE_MINERU: mineru_blocks, ENGINE_PADDLEOCR_VL: []})

    assert linked[ENGINE_MINERU] is not None
    assert linked[ENGINE_PADDLEOCR_VL] is None
