"""``OCRService.recognize_layout`` 的失败降级契约：云端异常不外抛，本地兜底才走得到。

## 为什么要锁这一条

`PaddleOCRApiEngine` 的失败出口（未配置 / Key 全冷却 / 轮询 4xx / Job 失败 / 超时）
**全部是 `RuntimeError`**（`paddleocr_api_service.py` 共 18 处 `raise RuntimeError`）。
`recognize_layout` 原来只捕 `(OSError, ValueError)`，于是云端一挂异常就穿透
`ocr_handler._recognize_page`（它自己不捕获）→ `_ocr_pages_worker` 的 except 分支 →
那页被标成 `ocr_failed`，**跳过本地 RapidOCR 兜底**（617-p12 整页丢字的帮凶）。

所以这里锁两件事：
1. `recognize_layout` 遇到 `RuntimeError` 返回 `None`（调用方据此走「无版面」分支），
   而不是把异常抛出去；
2. 同一份异常在 `recognize_bytes` 上走本地兜底——两条路径的捕获口径必须一致，
   只补一边等于没补。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from apps.automation.services.ocr.ocr_service import OCRService


def _raise_runtime_error(*_args: object, **_kwargs: object) -> None:
    """引擎侧真实失败形态（超时那一条的原文）。"""
    raise RuntimeError("PaddleOCR API Job 超时（600s）")


def _service(provider: str, *, engine: object | None = None) -> OCRService:
    """provider 与引擎都直接注入：不读 SystemConfig、不建真实 RapidOCR 会话。"""
    service = OCRService.__new__(OCRService)
    service.use_v5 = False
    service._provider = provider
    service._ocr = MagicMock()
    service._paddleocr_engine = engine
    return service


class TestRecognizeLayoutFallback:
    def test_引擎抛RuntimeError时返回None而不穿透(self, monkeypatch: pytest.MonkeyPatch) -> None:
        engine = MagicMock()
        monkeypatch.setattr(engine, "recognize_bytes", _raise_runtime_error)
        service = _service("paddleocr_api", engine=engine)

        assert service.recognize_layout(b"page-image") is None

    def test_非paddleocr_api的provider仍返回None(self) -> None:
        """本地 RapidOCR 没有版面概念：不能返回一个带空 images 的假结果。"""
        service = _service("local")

        assert service.recognize_layout(b"page-image") is None

    def test_recognize_bytes对同一异常走本地兜底(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """与 `recognize_layout` 共用同一异常族：云端失败时本地引擎必须接得住。"""
        engine = MagicMock()
        monkeypatch.setattr(engine, "recognize_bytes", _raise_runtime_error)
        service = _service("paddleocr_api", engine=engine)
        local_result = MagicMock()
        local_result.txts = ["本地兜底读出的字"]
        service._ocr = MagicMock(return_value=local_result)

        assert service.recognize_bytes(b"page-image") == "本地兜底读出的字"


class TestCloudLayoutFailurePaysOnce:
    """云端版面失败后**不得再打一次云端**：同一页一次 600s 超时就够贵了。

    `_recognize_page` 拿到 `recognize_layout() is None` 时会走纯文本兜底，而云端
    provider 的 `recognize_bytes` 内部**还会再调云端**。修好 `RuntimeError` 穿透之后
    这条分支第一次可达，于是「版面超时 + 纯文本超时」会叠成两倍墙钟。这里把它锁住。
    """

    def test_recognize_bytes_local一次云端调用都不发(self) -> None:
        engine = MagicMock()
        service = _service("paddleocr_api", engine=engine)
        local_result = MagicMock()
        local_result.txts = ["本地读出的字"]
        service._ocr = MagicMock(return_value=local_result)

        assert service.recognize_bytes_local(b"page-image") == "本地读出的字"
        engine.recognize_bytes.assert_not_called()

    def test_云端版面失败后只走本地不再调云端(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from apps.pdf_splitting.services.split.ocr_handler import _recognize_page

        engine = MagicMock()
        monkeypatch.setattr(engine, "recognize_bytes", _raise_runtime_error)
        service = _service("paddleocr_api", engine=engine)
        local_result = MagicMock()
        local_result.txts = ["本地兜底读出的字"]
        service._ocr = MagicMock(return_value=local_result)
        cloud_text_calls: list[bytes] = []
        monkeypatch.setattr(service, "recognize_bytes", lambda data: cloud_text_calls.append(data) or "")

        text, layout = _recognize_page(service, b"page-image", page_no=7)

        assert text == "本地兜底读出的字"
        assert layout is None
        # 关键：只剩 recognize_layout 那一次云端调用，纯文本兜底没再打云端
        assert cloud_text_calls == []
