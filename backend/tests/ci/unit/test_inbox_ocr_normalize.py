"""收件箱 OCR 端点归一化 helper 的纯单测（不加载 OCR 引擎，用假结果）。"""

from __future__ import annotations

import numpy as np

from apps.message_hub.api.inbox_api import _normalize_ocr_blocks


class _FakeResult:
    """模拟 RapidOCR 原始结果：numpy boxes/txts/scores。"""

    def __init__(self) -> None:
        # 两张图：左框 (0,0)-(100,40)，右框 (200,100)-(300,220)
        self.boxes = np.array(
            [
                [[0.0, 0.0], [100.0, 0.0], [100.0, 40.0], [0.0, 40.0]],
                [[200.0, 100.0], [300.0, 100.0], [300.0, 220.0], [200.0, 220.0]],
            ],
            dtype=np.float32,
        )
        self.txts = ["甲方", "乙方"]
        self.scores = [0.98, 0.91]


def test_normalize_single_block_centered():
    fake = _FakeResult()
    fake.boxes = np.array([[[0.0, 0.0], [100.0, 0.0], [100.0, 40.0], [0.0, 40.0]]], dtype=np.float32)
    fake.txts = ["借条"]
    blocks = _normalize_ocr_blocks(fake, width=1000, height=2000)
    assert len(blocks) == 1
    b = blocks[0]
    assert b.x == 0.0 and b.y == 0.0
    assert b.w == 0.1 and b.h == 0.02
    assert b.text == "借条"
    assert b.score == 0.98


def test_normalize_multiple_blocks_and_no_result():
    fake = _FakeResult()
    blocks = _normalize_ocr_blocks(fake, width=1000, height=2000)
    assert len(blocks) == 2
    assert blocks[0].text == "甲方" and blocks[1].text == "乙方"
    assert blocks[1].x == 0.2 and blocks[1].y == 0.05
    assert blocks[1].w == 0.1 and blocks[1].h == 0.06

    assert _normalize_ocr_blocks(None, 100, 100) == []
    assert _normalize_ocr_blocks(_FakeResult(), 0, 0) == []  # 无损尺寸时退化为全 0 坐标


def test_strips_whitespace_in_text():
    fake = _FakeResult()
    fake.txts = ["  身份证 号码  "]
    blocks = _normalize_ocr_blocks(fake, width=1000, height=1000)
    assert blocks[0].text == "身份证 号码"
