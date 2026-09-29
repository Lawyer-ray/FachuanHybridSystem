"""macOS Vision 框架本地 OCR 引擎（PyObjC 桥接）。

完全本地、零成本、离线，作为文书识别管线的本地 OCR 档（优先于 RapidOCR，
后者保留为跨平台兜底）。仅 darwin 可用；``pyobjc-framework-Vision`` 以
``sys_platform == 'darwin'`` 平台标记安装，Linux/CI 自动跳过。

实测基准（2026-09-28，扫描件财产清单）：accurate 档 6/9 关键点、~1.2s/页，
显著优于 RapidOCR（3/9）。

注意：``VNRecognizeTextRequest`` 的 ``recognitionLevel`` 是 **0=accurate、
1=fast**（反直觉）。fast 档不支持中文，设反会输出整篇乱码——必须用 accurate。
"""

from __future__ import annotations

import logging
import platform
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Vision 框架常量（0=accurate，1=fast，见模块 docstring）
_RECOGNITION_LEVEL_ACCURATE = 0
_RECOGNITION_LANGUAGES = ["zh-Hans", "en-US"]


def is_mac_vision_available() -> bool:
    """当前环境能否使用 macOS Vision OCR（平台 + 依赖双重检测）。"""
    if platform.system() != "Darwin":
        return False
    try:
        importlib_import("Vision")
        importlib_import("Foundation")
        return True
    except Exception:
        return False


def importlib_import(module_name: str) -> Any:
    """动态导入 PyObjC 模块（无类型存根，importlib 规避 mypy 缺 stub 报错）。"""
    import importlib

    return importlib.import_module(module_name)


class MacVisionOCREngine:
    """macOS Vision OCR（zh-Hans + en-US，accurate 档）。

    接口对齐 ``OCRService.recognize``：输入图片路径，返回识别文本（行以换行拼接）。
    """

    def recognize(self, image_path: str) -> str:  # pragma: no cover -- darwin 专用
        Vision = importlib_import("Vision")
        Foundation = importlib_import("Foundation")

        url = Foundation.NSURL.fileURLWithPath_(str(image_path))
        handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, None)

        request = Vision.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLevel_(_RECOGNITION_LEVEL_ACCURATE)
        request.setUsesLanguageCorrection_(True)
        request.setRecognitionLanguages_(_RECOGNITION_LANGUAGES)

        ok, error = handler.performRequests_error_([request], None)
        if not ok:
            raise RuntimeError(f"macOS Vision OCR 执行失败: {error}")

        lines: list[str] = []
        for observation in request.results() or []:
            candidates = observation.topCandidates_(1)
            if candidates:
                lines.append(str(candidates[0].string()))
        text = "\n".join(lines)
        logger.info("macOS Vision OCR 完成: %s, %d 行", image_path, len(lines))
        return text

    def recognize_bytes(self, image_bytes: bytes) -> str:  # pragma: no cover -- darwin 专用
        """图片字节转写（落临时文件后走 Vision URL 接口）。"""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(image_bytes)
            temp_path = tmp.name
        try:
            return self.recognize(temp_path)
        finally:
            Path(temp_path).unlink(missing_ok=True)
