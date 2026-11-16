"""图片块补救 OCR + 兜底页复用 VL 版面结果。

真实背景（579 材料包 164 页只读实测）：
- MinerU 把照片/手写页整块当图片返回，54 个 image 块全被重建层丢掉：身份证页
  只剩 45 字印章语（姓名/证号/住址全丢），面谈笔录 2 页只剩 209 字。
- 29 页走「本地 OCR 兜底」（本部署实为 PaddleOCR-VL 云 API），worker 只取拼好的
  纯文本，同一次响应里的 ``layoutParsingResults``（块坐标）当场被丢掉。

所以这里锁两件事：兜底页把已经付过费的版面结果用起来；质量画像标出的图形页/
证件缺字段页真的触发一次**定向**补救，且兜底页不重复计费。

全部用桩与合成数据，不调云端。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pymupdf as fitz

from apps.pdf_splitting.services.split.ocr_handler import _recognize_page, _rescale_region_blocks, vl_page_layout
from apps.pdf_splitting.services.split.page_quality import assess_page_quality
from apps.pdf_splitting.services.split.pipeline import PageTextExtractor
from apps.pdf_splitting.services.split.split_models import OCRPageResult, OCRRuntimeProfile, SegmentDraft

TEMPLATE_KEY = "filing_materials_v1"
PROFILE = OCRRuntimeProfile(key="accurate", use_v5=True, dpi=220, workers=2)

#: 身份证页实测形态：只有标题与印章套话，字段区是 MinerU 返回的空 image 块。
ID_CARD_TEXT = "中华人民共和国\n居民身份证\n已核对与原件相符\n经办人：李四"
ID_CARD_LAYOUT = {
    "page_no": 1,
    "blocks": [
        {"type": "image", "text": "", "bbox": [17, 12, 941, 818]},
        {"type": "text", "text": "中华人民共和国居民身份证", "bbox": [233, 488, 480, 546]},
    ],
    "text": ID_CARD_TEXT,
}

#: 补救读回来的字段（合成值，不是任何真实证件）。
RESCUED_TEXT = "姓名 张三\n性别 男 民族 汉\n住址 某某省某某市某某路1号\n公民身份号码 110101198001011234"


def _make_scan_pdf(path: Path, pages: int = 1) -> None:
    """造一份无文本层的扫描 PDF：逐页都会走云端/兜底路径。"""
    with fitz.open() as doc:
        for _ in range(pages):
            doc.new_page()
        doc.save(path.as_posix())


def _vl_pruned(blocks: list[dict[str, Any]], *, width: int = 1000, height: int = 1400) -> dict[str, Any]:
    """VL 的 prunedResult 结构（真实字段名：width/height/parsing_res_list）。"""
    return {"width": width, "height": height, "parsing_res_list": blocks}


class TestVlPageLayout:
    def test_块类型走现成归一化表(self) -> None:
        layout = vl_page_layout(
            [
                {
                    "prunedResult": _vl_pruned(
                        [
                            {
                                "block_label": "doc_title",
                                "block_content": "个人房产抵押贷款合同",
                                "block_bbox": [100, 50, 900, 120],
                            },
                            {
                                "block_label": "text",
                                "block_content": "第一条 借款金额",
                                "block_bbox": [100, 200, 900, 260],
                            },
                            {"block_label": "header", "block_content": "某某银行", "block_bbox": [100, 10, 900, 40]},
                        ]
                    )
                }
            ],
            page_no=5,
            text="正文",
        )

        assert layout is not None
        assert layout["page_no"] == 5
        assert [block["type"] for block in layout["blocks"]] == ["title", "text", "header"]

    def test_坐标收敛成千分比且页尺寸记1000(self) -> None:
        layout = vl_page_layout(
            [
                {
                    "prunedResult": _vl_pruned(
                        [{"block_label": "text", "block_content": "正文", "block_bbox": [100, 70, 900, 140]}]
                    )
                }
            ],
            page_no=1,
            text="正文",
        )

        assert layout is not None
        # 与 MinerU 同一套量纲：混排卷宗里兜底页的绿框才不会按千分比去除绝对像素
        assert layout["width"] == 1000 and layout["height"] == 1000
        assert layout["blocks"][0]["bbox"] == [100.0, 50.0, 900.0, 100.0]

    def test_缺页尺寸时保留文字但不编坐标(self) -> None:
        layout = vl_page_layout(
            [
                {
                    "prunedResult": {
                        "parsing_res_list": [
                            {"block_label": "text", "block_content": "正文", "block_bbox": [1, 2, 3, 4]}
                        ]
                    }
                }
            ],
            page_no=1,
            text="正文",
        )

        assert layout is not None
        assert layout["blocks"][0]["text"] == "正文"
        assert "bbox" not in layout["blocks"][0]

    def test_没有块时返回None而不是空壳(self) -> None:
        assert vl_page_layout([], page_no=1, text="正文") is None
        assert vl_page_layout([{"prunedResult": _vl_pruned([])}], page_no=1, text="") is None
        assert vl_page_layout(None, page_no=1, text="") is None

    def test_VL版面能重建标题表格并画出定位框(self) -> None:
        from apps.pdf_splitting.services.split.markdown_builder import build_segments_markdown
        from apps.pdf_splitting.services.split.pipeline import build_page_descriptor

        table_md = "|日期|金额|\n|---|---|\n|20170201|5000|"
        layout = vl_page_layout(
            [
                {
                    "prunedResult": _vl_pruned(
                        [
                            {
                                "block_label": "doc_title",
                                "block_content": "借款合同",
                                "block_bbox": [100, 50, 900, 120],
                            },
                            {"block_label": "table", "block_content": table_md, "block_bbox": [100, 300, 900, 900]},
                        ]
                    )
                }
            ],
            page_no=1,
            text=f"借款合同\n{table_md}",
        )
        page = build_page_descriptor(
            page_no=1,
            text=layout["text"],
            source_method="ocr",
            ocr_failed=False,
            template_key=TEMPLATE_KEY,
            layout=layout,
        )
        draft = SegmentDraft(
            order=0,
            page_start=1,
            page_end=1,
            segment_type="contract",
            filename="借款合同.pdf",
            confidence=0.9,
            source_method="llm",
            review_flag="normal",
        )

        entry = build_segments_markdown([draft], [page], bbox_backend="mineru")[0]

        assert "## 借款合同" in entry["markdown"]
        assert "|日期|金额|" in entry["markdown"] or "| 日期 | 金额 |" in entry["markdown"]
        # 兜底页以前 positioned 恒空（无 layout）；现在同一套千分比口径能画框
        assert entry["positioned"]
        assert all(0 <= item["rect"]["x"] <= 1 for item in entry["positioned"])


class TestRecognizePage:
    class _LayoutService:
        def __init__(self, result: Any) -> None:
            self.result = result
            self.bytes_calls = 0

        def recognize_layout(self, image_bytes: bytes) -> Any:
            return self.result

        def recognize_bytes(self, image_bytes: bytes) -> str:
            self.bytes_calls += 1
            return "纯文本兜底"

    def test_优先用版面结果_不再调纯文本接口(self) -> None:
        from types import SimpleNamespace

        result = SimpleNamespace(
            text="借款合同",
            layout_results=[
                {
                    "prunedResult": _vl_pruned(
                        [{"block_label": "text", "block_content": "借款合同", "block_bbox": [0, 0, 500, 100]}]
                    )
                }
            ],
        )
        service = self._LayoutService(result)

        text, layout = _recognize_page(service, b"png", page_no=3)

        assert text == "借款合同"
        assert layout is not None and layout["page_no"] == 3
        assert service.bytes_calls == 0  # 同一次响应就够了，不多付一次

    def test_拿不到版面才退回纯文本(self) -> None:
        service = self._LayoutService(None)

        text, layout = _recognize_page(service, b"png", page_no=1)

        assert text == "纯文本兜底"
        assert layout is None
        assert service.bytes_calls == 1


class TestRescaleRegionBlocks:
    def test_裁剪图坐标换算回整页(self) -> None:
        blocks = [{"type": "text", "text": "姓名 张三", "bbox": [0, 0, 1000, 500]}]

        out = _rescale_region_blocks(blocks, region=[200, 100, 800, 700])

        # 裁剪图占整页 x:200-800 / y:100-700，块占裁剪图上半部
        assert out[0]["bbox"] == [200.0, 100.0, 800.0, 400.0]

    def test_无坐标块原样保留(self) -> None:
        out = _rescale_region_blocks([{"type": "text", "text": "正文"}], region=[0, 0, 500, 500])
        assert out == [{"type": "text", "text": "正文"}]


class _RescueHandler:
    """取字桩：云端给「身份证页」，补救接口返回字段文本并记录调用。"""

    def __init__(
        self,
        *,
        cloud: dict[int, OCRPageResult] | None = None,
        local: dict[int, OCRPageResult] | None = None,
        rescue: dict[str, Any] | None = None,
        rescue_empty: bool = False,
        rescue_error: Exception | None = None,
    ) -> None:
        self.cloud = (
            cloud
            if cloud is not None
            else {
                1: OCRPageResult(
                    page_no=1, text=ID_CARD_TEXT, source_method="mineru_ocr", ocr_failed=False, layout=ID_CARD_LAYOUT
                )
            }
        )
        self.local = local or {}
        self.rescue = (
            rescue
            if rescue is not None
            else {"text": RESCUED_TEXT, "blocks": [{"type": "text", "text": RESCUED_TEXT, "bbox": [17, 12, 941, 400]}]}
        )
        self.rescue_empty = rescue_empty
        self.rescue_error = rescue_error
        self.rescue_calls: list[tuple[int, list[float]]] = []
        self.written: list[tuple[str, int, str]] = []

    def resolve_runtime_profile(self, profile_key: str) -> OCRRuntimeProfile:
        return PROFILE

    def resolve_cloud_backends(self, cloud_backend: str | None = None) -> list[str]:
        return ["mineru"]

    def sha256_file(self, pdf_path: Path) -> str:
        return "hash-rescue"

    def read_ocr_cache(self, *, pdf_hash: str, profile_key: str, page_no: int) -> Any:
        return None

    def write_ocr_cache(self, *, pdf_hash: str, profile_key: str, result: OCRPageResult) -> None:
        self.written.append((profile_key, result.page_no, result.text))

    def parse_cloud_pages(self, *, pdf_path: Path, backend: str) -> dict[int, OCRPageResult]:
        return self.cloud

    def parallel_ocr(
        self, *, pdf_path: Path, page_numbers: list[int], runtime_profile: Any
    ) -> dict[int, OCRPageResult]:
        return self.local

    def ocr_page_region(self, *, pdf_path: Path, page_no: int, region: list[float], runtime_profile: Any) -> Any:
        self.rescue_calls.append((page_no, region))
        if self.rescue_error:
            raise self.rescue_error
        return None if self.rescue_empty else self.rescue


class TestImageRescue:
    def test_身份证页救回字段并进正文与版面(self, tmp_path: Path) -> None:
        pdf = tmp_path / "scan.pdf"
        _make_scan_pdf(pdf)
        handler = _RescueHandler()

        pages, summary = PageTextExtractor(ocr_handler=handler).extract(
            pdf, ocr_profile="accurate", template_key=TEMPLATE_KEY
        )

        assert handler.rescue_calls == [(1, [17, 12, 941, 818])]
        assert "公民身份号码 110101198001011234" in pages[0].text
        assert ID_CARD_TEXT.splitlines()[0] in pages[0].text  # 原有正文没被顶掉
        assert any(block["text"] == RESCUED_TEXT for block in pages[0].layout["blocks"])
        assert summary["image_rescue_pages"] == [1]
        assert summary["image_rescue_chars"] == len(RESCUED_TEXT)

    def test_补救结果回写缓存_重跑不再付费(self, tmp_path: Path) -> None:
        pdf = tmp_path / "scan.pdf"
        _make_scan_pdf(pdf)
        handler = _RescueHandler()

        _pages, summary = PageTextExtractor(ocr_handler=handler).extract(
            pdf, ocr_profile="accurate", template_key=TEMPLATE_KEY
        )

        profile = summary["ocr_cloud_cache_profile"]
        rescued_writes = [item for item in handler.written if item[0] == profile and RESCUED_TEXT in item[2]]
        assert len(rescued_writes) == 1

    def test_兜底页复用已有VL结果_不重复计费(self, tmp_path: Path) -> None:
        pdf = tmp_path / "scan.pdf"
        _make_scan_pdf(pdf)
        # 兜底页的版面本来就来自 VL 那次响应：再调一次等于同一页付两次钱
        handler = _RescueHandler(
            cloud={},
            local={
                1: OCRPageResult(
                    page_no=1,
                    text="面谈笔录表",
                    source_method="ocr",
                    ocr_failed=False,
                    layout={"page_no": 1, "blocks": [{"type": "image", "text": "", "bbox": [100, 100, 900, 900]}]},
                )
            },
        )

        _pages, summary = PageTextExtractor(ocr_handler=handler).extract(
            pdf, ocr_profile="accurate", template_key=TEMPLATE_KEY
        )

        assert handler.rescue_calls == []
        assert summary["image_rescue_reused"] == 1
        assert summary["image_rescue_pages"] == []

    def test_正常文本页不触发补救(self, tmp_path: Path) -> None:
        pdf = tmp_path / "scan.pdf"
        _make_scan_pdf(pdf)
        body = "5.4 借款人应在本合同签订后三十日内办理抵押登记手续，并将登记证明文件交由贷款人保管。" * 4
        handler = _RescueHandler(
            cloud={
                1: OCRPageResult(
                    page_no=1,
                    text=body,
                    source_method="mineru_ocr",
                    ocr_failed=False,
                    layout={"page_no": 1, "blocks": [{"type": "image", "text": "", "bbox": [0, 0, 900, 900]}]},
                )
            }
        )

        _pages, summary = PageTextExtractor(ocr_handler=handler).extract(
            pdf, ocr_profile="accurate", template_key=TEMPLATE_KEY
        )

        assert handler.rescue_calls == []
        assert summary["image_rescue_pages"] == []

    def test_补救页数有上限(self, tmp_path: Path) -> None:
        from apps.pdf_splitting.services.split.pipeline import _RESCUE_MAX_PAGES

        pdf = tmp_path / "scan.pdf"
        count = _RESCUE_MAX_PAGES + 3
        _make_scan_pdf(pdf, count)
        handler = _RescueHandler(
            cloud={
                no: OCRPageResult(
                    page_no=no,
                    text="平面图",
                    source_method="mineru_ocr",
                    ocr_failed=False,
                    layout={"page_no": no, "blocks": [{"type": "image", "text": "", "bbox": [100, 100, 900, 900]}]},
                )
                for no in range(1, count + 1)
            }
        )

        _pages, summary = PageTextExtractor(ocr_handler=handler).extract(
            pdf, ocr_profile="accurate", template_key=TEMPLATE_KEY
        )

        assert len(handler.rescue_calls) == _RESCUE_MAX_PAGES
        assert len(summary["image_rescue_pages"]) == _RESCUE_MAX_PAGES

    def test_补救失败不拖垮整本取字(self, tmp_path: Path) -> None:
        pdf = tmp_path / "scan.pdf"
        _make_scan_pdf(pdf)
        handler = _RescueHandler(rescue_error=RuntimeError("vl down"))

        pages, summary = PageTextExtractor(ocr_handler=handler).extract(
            pdf, ocr_profile="accurate", template_key=TEMPLATE_KEY
        )

        assert len(pages) == 1
        assert pages[0].text  # 原有取字结果仍在
        assert summary["image_rescue_pages"] == []

    def test_补救读不出内容时不写空块(self, tmp_path: Path) -> None:
        pdf = tmp_path / "scan.pdf"
        _make_scan_pdf(pdf)
        handler = _RescueHandler(rescue_empty=True)

        pages, summary = PageTextExtractor(ocr_handler=handler).extract(
            pdf, ocr_profile="accurate", template_key=TEMPLATE_KEY
        )

        assert pages[0].text == ID_CARD_TEXT
        assert summary["image_rescue_pages"] == []

    def test_补救过的块不再被重复targeting(self, tmp_path: Path) -> None:
        """重跑保护：补救成果已进缓存，原空 image 块必须打标，否则每次重跑再付一次钱。"""
        from apps.pdf_splitting.services.split.page_quality import rescue_image_region

        pdf = tmp_path / "scan.pdf"
        _make_scan_pdf(pdf)
        handler = _RescueHandler()

        pages, _summary = PageTextExtractor(ocr_handler=handler).extract(
            pdf, ocr_profile="accurate", template_key=TEMPLATE_KEY
        )

        page = pages[0]
        quality = assess_page_quality(page_no=1, text=page.text, layout=page.layout)
        assert rescue_image_region(page, quality) is None
        assert any(block.get("rescued") for block in page.layout["blocks"])
