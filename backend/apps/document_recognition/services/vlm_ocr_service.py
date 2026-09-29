"""VLM 视觉转写服务：扫描件/图片 → 多模态模型逐页转写。

依赖 AI 平台的视觉模型配置（``LLMProvider.vision_model``，经
``LLMConfig.get_vision_model()`` 读取；空 = 视觉档禁用）。换供给只改
「AI 平台」一行，代码零模型名硬编码。

失败语义：本服务**抛异常**，由 ``text_extraction_service`` 捕获后降级到
本地 OCR（macOS Vision / RapidOCR）——视觉档挂掉任务不会失败。

实测基准（2026-09-28，扫描件财产清单）：kimi-2.6 视觉 7/9 关键点、
~6s/页；本地 RapidOCR 3/9。转写输出的 CJK-数字间空格由下游
``_remove_all_spaces`` 统一清除，无需在本层处理。
"""

from __future__ import annotations

import base64
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger("apps.document_recognition")

TRANSCRIBE_PROMPT = (
    "请逐字转录这张法院文书图片中的全部文字，保持原文顺序，"
    "不要遗漏、总结或改写。输出纯文本，不要任何前言、解释或 Markdown 代码块标记。"
)

# 页面渲染精度与页数/时长保护（超限走本地 OCR，任务不失败）
RENDER_DPI = 150
MAX_VLM_PAGES = 5
CHAT_TIMEOUT_SECONDS = 120
MAX_OUTPUT_TOKENS = 4000

_CODE_FENCE_RE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


def _clean_transcription(text: str) -> str:
    """去掉模型偶尔包裹的 Markdown 代码块围栏与首尾空白。"""
    cleaned = text.strip()
    cleaned = _CODE_FENCE_RE.sub("", cleaned).strip()
    return cleaned


class VLMTranscriptionService:
    """多模态模型视觉转写（图片 / 扫描 PDF 逐页）。"""

    def __init__(self, llm_service: Any | None = None) -> None:
        # 不读系统配置，避免构造期触发 DB 访问（无 django_db 标记的单测会被阻断）
        self._llm_service = llm_service

    @staticmethod
    def is_available() -> bool:
        """视觉档开关：AI 平台配置了 vision_model 即启用。"""
        from apps.core.llm.config import LLMConfig

        return bool(LLMConfig.get_vision_model())

    def _get_llm_service(self) -> Any:
        if self._llm_service is None:
            from apps.core.interfaces import ServiceLocator

            self._llm_service = ServiceLocator.get_llm_service()
        return self._llm_service

    def transcribe_pdf(self, file_path: str, max_pages: int | None = None) -> str:
        """扫描 PDF 逐页渲染为 PNG 并转写，页间以空行拼接。

        超过 MAX_VLM_PAGES 的页不再送 VLM（调用方拿到前若干页文本自行
        判断是否够用；不够则整体降级本地 OCR）。
        """
        import pymupdf as fitz

        effective_pages = min(max_pages or MAX_VLM_PAGES, MAX_VLM_PAGES)
        pages: list[str] = []
        with fitz.open(file_path) as doc:
            for page_num in range(min(doc.page_count, effective_pages)):
                pix = doc.load_page(page_num).get_pixmap(dpi=RENDER_DPI)
                pages.append(self._transcribe_image_bytes(pix.tobytes("png"), "image/png", page_num))
        text = "\n\n".join(p for p in pages if p)
        logger.info(
            "VLM 视觉转写完成: file=%s, pages=%d, chars=%d",
            file_path,
            len(pages),
            len(text),
            extra={"action": "vlm_transcribe_pdf", "vision_model": self._vision_model()},
        )
        return text

    def transcribe_image(self, file_path: str) -> str:
        """单张图片（jpg/jpeg/png）转写。"""
        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}.get(
            Path(file_path).suffix.lower(), "image/jpeg"
        )
        text = self._transcribe_image_bytes(Path(file_path).read_bytes(), mime, 0)
        logger.info(
            "VLM 视觉转写完成: file=%s, chars=%d",
            file_path,
            len(text),
            extra={"action": "vlm_transcribe_image", "vision_model": self._vision_model()},
        )
        return text

    @staticmethod
    def _vision_model() -> str:
        from apps.core.llm.config import LLMConfig

        return LLMConfig.get_vision_model()

    def _transcribe_image_bytes(self, image_bytes: bytes, mime: str, page_num: int) -> str:
        vision_model = self._vision_model()
        if not vision_model:
            raise RuntimeError("视觉模型未配置（AI 平台 vision_model 为空）")

        b64 = base64.b64encode(image_bytes).decode()
        response = self._get_llm_service().chat(
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                        {"type": "text", "text": TRANSCRIBE_PROMPT},
                    ],
                }
            ],
            model=vision_model,
            temperature=0.1,
            max_tokens=MAX_OUTPUT_TOKENS,
            timeout_seconds=CHAT_TIMEOUT_SECONDS,
            fallback=False,
            caller="document_recognition.vlm_transcribe",
        )
        content = _clean_transcription(str(getattr(response, "content", "") or ""))
        logger.debug("VLM 转写第 %d 页: %d 字", page_num, len(content))
        return content
