"""记收款：粘贴一张图（银行回单截图）→ 文本。

律师手上的「到账凭据」一半是短信，另一半是**网银 App 里的电子回单截图**：
以前只能手抄金额/日期/付款人，抄错一位就是财务事故。

本服务只解决「图片 → 文本」这一段，**不解析字段**、不落库、不建 Invoice：
字段推导交给 `ReceiptTextParser` / `PaymentSmsParser`（纯函数、可单测），
API 层负责把两边的结果合成一份草稿。

文本提取**直接复用** `document_recognition.TextExtractionService`，不另起一套：

1. 文本层（粘贴的 PDF 回单）直接提取；
2. 图片走 VLM 视觉转写（AI 平台配了 `vision_model` 时）→ 本地 OCR 兜底
   （macOS Vision / RapidOCR）。

这样「识别引擎」全仓只有一份，换供给只改 AI 平台一行。本层额外做两件
`TextExtractionService` 不负责的事：**大小/MIME 校验**与**临时文件清理**
（粘贴来的图没有文件名，也不该落进 media）。
"""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from apps.core.exceptions import ValidationException

logger = logging.getLogger("apps.contracts.services.payment")

__all__ = [
    "PastedImageText",
    "PaymentImageReader",
    "MAX_PASTE_BYTES",
]

#: 粘贴体积上限：一张网银回单截图通常 200KB~2MB，20MB 与发票上传口径一致
MAX_PASTE_BYTES = 20 * 1024 * 1024

#: 允许的扩展名 / MIME（浏览器粘贴图片时 type 常有 image/png、image/jpeg）
_ALLOWED_SUFFIX = {".jpg", ".jpeg", ".png", ".pdf", ".webp", ".heic"}
_MIME_SUFFIX = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "application/pdf": ".pdf",
}


@dataclass(frozen=True)
class PastedImageText:
    """粘贴识别结果。

    Attributes:
        text: 提取到的原始文本（**保留换行**——回单是分栏表格，换行即栏位边界）
        method: `pdf_direct` / `vlm` / `ocr` / `empty`
        chars: 文本长度（0 说明一个字都没认出来）
    """

    text: str
    method: str
    chars: int

    @property
    def ok(self) -> bool:
        return self.chars > 0


def _resolve_suffix(filename: str, content_type: str) -> str:
    """扩展名优先取文件名，文件名没有（粘贴的 blob）时按 MIME 补。"""
    suffix = Path(filename or "").suffix.lower()
    if suffix in _ALLOWED_SUFFIX:
        return suffix
    by_mime = _MIME_SUFFIX.get((content_type or "").split(";")[0].strip().lower())
    if by_mime:
        return by_mime
    raise ValidationException(
        "只支持图片（PNG / JPG）或 PDF 回单",
        code="UNSUPPORTED_PASTE_FORMAT",
        errors={"file": f"无法识别的类型：{content_type or filename or '未知'}"},
    )


class PaymentImageReader:
    """粘贴图片 / PDF → 文本（薄封装，识别引擎全在 TextExtractionService）。"""

    def __init__(self, extractor: Any | None = None) -> None:
        # 不在构造期取服务：避免导入即触发 OCR 引擎加载（单测无 django_db 也能跑）
        self._extractor = extractor

    def _get_extractor(self) -> Any:
        if self._extractor is None:
            from apps.document_recognition.services.text_extraction_service import TextExtractionService

            self._extractor = TextExtractionService()
        return self._extractor

    def read(self, *, data: bytes, filename: str = "", content_type: str = "") -> PastedImageText:
        """把一份粘贴上来的字节流读成文本。

        **失败语义**：引擎识别不出文字时返回 `ok=False`（不是异常）——前端据此
        提示「没认出文字，请手动填写」，而不是报错卡住整个记收款流程。
        格式/体积不合法才抛 `ValidationException`（400）。
        """
        if not data:
            raise ValidationException("粘贴内容为空", code="EMPTY_PASTE", errors={"file": "空"})
        if len(data) > MAX_PASTE_BYTES:
            raise ValidationException(
                f"文件超过 {MAX_PASTE_BYTES // (1024 * 1024)}MB",
                code="PASTE_TOO_LARGE",
                errors={"file": "文件过大"},
            )

        suffix = _resolve_suffix(filename, content_type)
        tmp_path = self._write_temp(data, suffix)
        try:
            result = self._get_extractor().extract_text(tmp_path)
        except ValidationException:
            raise
        except Exception:
            # 引擎整体挂掉：不阻断记账，返回空文本让前端提示手填
            logger.warning("payment_paste_extract_failed", exc_info=True)
            return PastedImageText(text="", method="empty", chars=0)
        finally:
            tmp_path.unlink(missing_ok=True)

        text = str(getattr(result, "text", "") or "")
        method = str(getattr(result, "extraction_method", "") or "empty")
        if not text.strip():
            return PastedImageText(text="", method=method or "empty", chars=0)

        logger.info(
            "payment_paste_extracted",
            extra={"extraction_method": method, "chars": len(text), "bytes": len(data)},
        )
        return PastedImageText(text=text, method=method, chars=len(text))

    def _write_temp(self, data: bytes, suffix: str) -> Path:
        """落到系统临时目录。

        刻意**不用** MEDIA_ROOT：粘贴来的图是中间产物，不该进 media 被当成正式
        材料（否则每贴一次回单就多一个孤儿文件）。`TextExtractionService` 只要求
        路径存在，不关心它在哪。
        """
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as fh:
            fh.write(data)
            return Path(fh.name)
