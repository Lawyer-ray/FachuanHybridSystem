"""``field_verification``：千分比 bbox → 裁块 → 送判定 的适配层单测（全程 monkeypatch，不发请求）。

## 守的是什么

判定器的 ``p`` 对「候选文本是否与裁块同域」极度敏感：同一张身份证块，只送 18 位号码
``p=0.0011``，连带图上的前缀词 ``p=0.3892``（差 350 倍）。但「同域」还有另一半——**裁块本身
必须不多不少就是那一块**：裁宽了就带进相邻字，带进去一个词，p 一样掉回噪声区。

所以这里把裁块**逐像素**钉住，而不是「图能打开就算过」：页图上画已知的墨迹矩形，裁完在
裁块里找墨迹的像素包围盒。包围盒的偏移 = 裁块从页面哪个位置切下来的，尺寸 = 内边距生效多少。

## 三条红线

1. **量纲只认千分比**：越出千分比量级的坐标（像素框）按 ``bad_bbox`` 拒，不去猜单位；
2. **两种「不用问」都别发请求**：``bad_bbox`` / ``crop_empty`` 必须**一次判定器都不调**
   （每次调用都是一次云端请求，也是钱）；
3. **越界必须自己夹**：``Image.crop`` 越界不报错，而是补黑边——补出来的黑边在判定器眼里
   就是「图上有内容」，于是「框画到页外」会伪装成一次正常的核验。

## 跑法（红线：只能连测试库）

```bash
cd backend
DB_NAME=test_fachuan_dev .venv/bin/python -m pytest tests/ci/unit/pdf_splitting/test_field_verification.py -q
```
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import pytest
from PIL import Image, ImageOps

from apps.pdf_splitting.services.split import field_verification
from apps.pdf_splitting.services.split.field_verification import FieldVerification, candidates_from_block, verify_field

#: 虚构的身份证号（明显假号）：真实证件号不许写进测试；本文件全程 monkeypatch，真判定器不会被调。
_FAKE_ID = "110101198001011234"

#: 同域的候选：图上印的前缀词 + 号码本身（实测只有这种取法 p 才过 0.38）。
_BLOCK_TEXT = f"公民身份号码 {_FAKE_ID}"


@dataclass(frozen=True)
class _Judgement:
    """``disagreement_judge.Judgement`` 的最小替身：本层只透传它的四个属性。"""

    decision: str
    winner: str | None
    reason: str
    ratio: float | None = None


class _JudgeRecorder:
    """替换 ``field_verification.judge_candidates``：记下每次入参，回放固定结论。"""

    def __init__(self, judgement: _Judgement) -> None:
        self.judgement = judgement
        self.calls: list[dict] = []

    def __call__(self, image_bytes: bytes, candidates: list[str], *, domain: str = "text") -> _Judgement:
        self.calls.append({"image_bytes": image_bytes, "candidates": list(candidates), "domain": domain})
        return self.judgement


@pytest.fixture
def judge(monkeypatch: pytest.MonkeyPatch) -> _JudgeRecorder:
    """把判定器换成记录器（真实实现要发 HTTP，单测里一次都不许调）。"""
    recorder = _JudgeRecorder(_Judgement(decision="accept", winner=_FAKE_ID, reason="scored", ratio=0.996))
    monkeypatch.setattr(field_verification, "judge_candidates", recorder)
    return recorder


def _page_png(width: int, height: int, *, ink: tuple[int, int, int, int] | None = None, luma: int = 0) -> bytes:
    """造一张白底页图；``ink`` 是墨迹矩形（像素），``luma`` 是墨迹亮度（0 = 纯黑）。"""
    image = Image.new("RGB", (width, height), (255, 255, 255))
    if ink is not None:
        image.paste((luma, luma, luma), ink)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _size_of(png: bytes) -> tuple[int, int]:
    """裁块尺寸（宽, 高）。"""
    with Image.open(io.BytesIO(png)) as image:
        return image.size


def _ink_bbox(png: bytes) -> tuple[int, int, int, int] | None:
    """裁块里「非白像素」的包围盒；全白返回 None。

    反推裁块位置的唯一办法：页图上的墨迹位置已知，墨迹在裁块里的偏移就是内边距，
    偏移加墨迹尺寸就是裁块右/下边界。
    """
    with Image.open(io.BytesIO(png)) as image:
        return ImageOps.invert(image.convert("L")).getbbox()


class TestCoordinateConversion:
    """千分比 → 像素：``px = milli / 1000 × 页边长``，x/y 各用自己的边长。"""

    def test_块位置按千分比换算_裁块不多不少(self, judge: _JudgeRecorder) -> None:
        # 400×200 页，墨迹占 (100,50)-(200,100)；千分比 [250,250,500,500] 正好是同一块
        page = _page_png(400, 200, ink=(100, 50, 200, 100))

        result = verify_field(page, [250, 250, 500, 500], [_FAKE_ID], pad_ratio=0.0)

        assert result.crop_bbox_px == (100, 50, 200, 100)
        assert _ink_bbox(result.crop_bytes) == (0, 0, 100, 50)

    def test_x_y_各用自己的页边长_不共用公分母(self, judge: _JudgeRecorder) -> None:
        # 非方形页：x 除以页宽 400、y 除以页高 200。拿短边当公分母会把 y 压掉一半
        page = _page_png(400, 200, ink=(210, 10, 390, 90))

        result = verify_field(page, [500, 0, 1000, 500], [_FAKE_ID], pad_ratio=0.0)

        assert result.crop_bbox_px == (200, 0, 400, 100)
        assert _ink_bbox(result.crop_bytes) == (10, 10, 190, 90)


class TestPaddingAndClamp:
    """内边距四边都生效；越界部分自己夹回页内（不靠 PIL 补黑边）。"""

    def test_内边距按块高外扩_上下左右各一份(self, judge: _JudgeRecorder) -> None:
        page = _page_png(400, 200, ink=(100, 50, 200, 100))

        # 块 px = (100,50)-(200,100)，块高 50 → pad = 0.2 × 50 = 10
        result = verify_field(page, [250, 250, 500, 500], [_FAKE_ID], pad_ratio=0.2)

        assert result.crop_bbox_px == (90, 40, 210, 110)
        assert _size_of(result.crop_bytes) == (120, 70)
        assert _ink_bbox(result.crop_bytes) == (10, 10, 110, 60)  # 四边各让出 10px

    def test_默认内边距是块高的四分之一(self, judge: _JudgeRecorder) -> None:
        page = _page_png(400, 200, ink=(100, 50, 200, 90))

        # 块 px = (100,50)-(200,90)，块高 40 → 默认 pad_ratio=0.25 → pad = 10
        result = verify_field(page, [250, 250, 500, 450], [_FAKE_ID])

        assert result.crop_bbox_px == (90, 40, 210, 100)

    def test_右下越界夹回页内_不补黑边(self, judge: _JudgeRecorder) -> None:
        page = _page_png(200, 100, ink=(160, 60, 200, 100))

        # 块 px = (160,60)-(200,100)，块高 40 → pad 20 → (140,40)-(220,140) → 夹回页内
        result = verify_field(page, [800, 600, 1000, 1000], [_FAKE_ID], pad_ratio=0.5)

        assert result.crop_bbox_px == (140, 40, 200, 100)
        assert _size_of(result.crop_bytes) == (60, 60)
        assert _ink_bbox(result.crop_bytes) == (20, 20, 60, 60)

    def test_左上越界夹回原点(self, judge: _JudgeRecorder) -> None:
        page = _page_png(200, 100, ink=(0, 0, 40, 30))

        # 块 px = (0,0)-(40,30)，块高 30 → pad 15 → (-15,-15)-(55,45) → 夹回 (0,0)-(55,45)
        result = verify_field(page, [0, 0, 200, 300], [_FAKE_ID], pad_ratio=0.5)

        assert result.crop_bbox_px == (0, 0, 55, 45)
        assert _ink_bbox(result.crop_bytes) == (0, 0, 40, 30)

    def test_轻微负坐标夹回页内(self, judge: _JudgeRecorder) -> None:
        page = _page_png(200, 100, ink=(0, 0, 40, 30))

        # 引擎偶尔给轻微越界（-20 千分比 = -4px）：块 px = (-4,-2)-(40,30)，块高 32 → pad 8
        result = verify_field(page, [-20, -20, 200, 300], [_FAKE_ID])

        assert result.crop_bbox_px == (0, 0, 48, 38)


class TestBadBbox:
    """框不可用：一次都不许调判定器（那是一次白花的云端请求）。"""

    @pytest.mark.parametrize(
        "bbox_milli",
        [
            pytest.param([500, 500, 300, 300], id="反向框_x1<x0"),
            pytest.param([500, 500, 500, 900], id="零宽框"),
            pytest.param([500, 500, 505, 505], id="宽高正好2px"),
            pytest.param([209, 89, 2666, 2118], id="像素坐标_越出千分比量级"),
            pytest.param([100, 100, 200], id="只有三点"),
            pytest.param(["a", "b", "c", "d"], id="非数字"),
            pytest.param([float("nan"), 0, 400, 400], id="NaN"),
            pytest.param([1200, 1200, 1500, 1500], id="整块落在页外"),
        ],
    )
    def test_坏框直接进人工且不发请求(self, judge: _JudgeRecorder, bbox_milli: list) -> None:
        page = _page_png(400, 200, ink=(100, 50, 200, 100))

        result = verify_field(page, bbox_milli, [_FAKE_ID])

        assert (result.decision, result.reason) == ("human", "bad_bbox")
        assert (result.crop_bytes, result.crop_bbox_px, result.judgement) == (None, None, None)
        assert judge.calls == []

    def test_刚好超过最小边长就放行(self, judge: _JudgeRecorder) -> None:
        page = _page_png(400, 200, ink=(100, 100, 200, 103))

        # 页高 200px：千分比 500→515 正好 3px 高，比 MIN_BLOCK_PX=2 多 1px
        result = verify_field(page, [250, 500, 500, 515], [_FAKE_ID])

        assert result.reason != "bad_bbox"
        assert len(judge.calls) == 1


class TestCropEmpty:
    """裁块没有墨迹：白块/黑块都不会有可判定的文字，直接进人工。"""

    def test_纯白块不发请求_裁块照给人工抽屉(self, judge: _JudgeRecorder) -> None:
        page = _page_png(400, 200)  # 白底无墨

        result = verify_field(page, [250, 250, 500, 500], [_FAKE_ID], pad_ratio=0.2)

        assert (result.decision, result.reason) == ("human", "crop_empty")
        assert judge.calls == []
        assert result.crop_bbox_px == (90, 40, 210, 110)
        assert _ink_bbox(result.crop_bytes) is None  # 人工要能看见「这块是白的」，才判得下去

    def test_纯黑块不发请求(self, judge: _JudgeRecorder) -> None:
        page = _page_png(400, 200, ink=(0, 0, 400, 200))

        result = verify_field(page, [250, 250, 500, 500], [_FAKE_ID], pad_ratio=0.2)

        assert (result.decision, result.reason) == ("human", "crop_empty")
        assert judge.calls == []

    @pytest.mark.parametrize(("luma", "expected_reason"), [(250, "crop_empty"), (240, "scored")])
    def test_判空阈值的两侧(self, judge: _JudgeRecorder, luma: int, expected_reason: str) -> None:
        # 250 是扫描件空白区底纹的常态（判空），240 是可读的灰字/灰线（必须送判定）
        page = _page_png(400, 200, ink=(120, 60, 180, 90), luma=luma)

        result = verify_field(page, [250, 250, 500, 500], [_FAKE_ID], pad_ratio=0.2)

        assert result.reason == expected_reason
        assert len(judge.calls) == (0 if expected_reason == "crop_empty" else 1)


class TestPassThrough:
    """正常路径：裁块 + 候选原样交判定器，结论原样透传回来。"""

    def test_结论透传_裁块就是送出去的那份(self, judge: _JudgeRecorder) -> None:
        page = _page_png(400, 200, ink=(100, 50, 200, 100))
        candidates = [_BLOCK_TEXT, _FAKE_ID]

        result = verify_field(page, [250, 250, 500, 500], candidates, pad_ratio=0.2)

        assert (result.decision, result.winner, result.reason) == ("accept", _FAKE_ID, "scored")
        assert result.judgement is judge.judgement  # 原样保留，不重新拼一个结论
        assert judge.calls == [{"image_bytes": result.crop_bytes, "candidates": candidates, "domain": "text"}]
        with Image.open(io.BytesIO(result.crop_bytes)) as crop:
            assert (crop.format, crop.size) == ("PNG", (120, 70))

    def test_域名原样传给判定器(self, judge: _JudgeRecorder) -> None:
        page = _page_png(400, 200, ink=(100, 50, 200, 100))

        verify_field(page, [250, 250, 500, 500], [_FAKE_ID], domain="id_card", pad_ratio=0.2)

        assert [call["domain"] for call in judge.calls] == ["id_card"]

    def test_放大只改裁块尺寸_不改页坐标(self, judge: _JudgeRecorder) -> None:
        page = _page_png(400, 200, ink=(100, 50, 200, 100))

        result = verify_field(page, [250, 250, 500, 500], [_FAKE_ID], pad_ratio=0.2, upscale=2.0)

        # 人工抽屉要在页面上画框，所以 crop_bbox_px 与 upscale 无关
        assert result.crop_bbox_px == (90, 40, 210, 110)
        assert _size_of(result.crop_bytes) == (240, 140)

    def test_与_candidates_from_block_接得上(self, judge: _JudgeRecorder) -> None:
        page = _page_png(400, 200, ink=(100, 50, 200, 100))

        candidates = candidates_from_block(_BLOCK_TEXT, [_FAKE_ID, "张三"])
        verify_field(page, [250, 250, 500, 500], candidates, pad_ratio=0.2)

        assert judge.calls[0]["candidates"] == [_BLOCK_TEXT, _FAKE_ID]

    @pytest.mark.parametrize("kwargs", [{"pad_ratio": -0.1}, {"upscale": 0.0}])
    def test_非法参数直接抛(self, judge: _JudgeRecorder, kwargs: dict) -> None:
        page = _page_png(400, 200, ink=(100, 50, 200, 100))

        with pytest.raises(ValueError):
            verify_field(page, [250, 250, 500, 500], [_FAKE_ID], **kwargs)


class TestCandidatesFromBlock:
    """``candidates_from_block``：块文本永远第一，只收「真出现过」的字段值。"""

    def test_块文本排第一_只收块里出现的字段(self) -> None:
        assert candidates_from_block(_BLOCK_TEXT, [_FAKE_ID, "张三"]) == [_BLOCK_TEXT, _FAKE_ID]

    def test_块文本在首位_即使字段是它的前缀(self) -> None:
        assert candidates_from_block(_BLOCK_TEXT, ["公民身份号码"]) == [_BLOCK_TEXT, "公民身份号码"]

    def test_去重且保序(self) -> None:
        assert candidates_from_block("张三", ["张三", "张三", "李四", " 张三 "]) == ["张三"]

    def test_字段首尾空白不影响命中(self) -> None:
        assert candidates_from_block(_BLOCK_TEXT, [f" {_FAKE_ID}\n"]) == [_BLOCK_TEXT, _FAKE_ID]

    def test_空块文本没有候选(self) -> None:
        assert candidates_from_block("   ", [_FAKE_ID]) == []


def test_公开契约字段齐全() -> None:
    """冻结的字段集合：装配层按名字取值，少一个就是 AttributeError。"""
    assert list(FieldVerification.__dataclass_fields__) == [
        "decision",
        "winner",
        "reason",
        "crop_bytes",
        "crop_bbox_px",
        "judgement",
    ]
