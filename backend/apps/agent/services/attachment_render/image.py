"""图片附件渲染：合规原图透传，其余用 Pillow 转码。"""

from __future__ import annotations

import io
import logging

from .pdf import _fmt_mime, _page_from_image
from .types import MAX_EDGE_PX, MAX_PAGE_BYTES, RenderedPage, RenderError, RenderStrategy

logger = logging.getLogger(__name__)

#: 可直接透传的图片 MIME：解码再编码只会掉质量，且会抹掉原始 EXIF 方向信息
_PASSTHROUGH_MIMES = {"image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png", "image/webp": "webp"}


def render_image(
    file_bytes: bytes,
    mime: str,
    *,
    page_no: int = 1,
    fmt: str = "png",
    edge_limit: int = MAX_EDGE_PX,
    size_limit: int = MAX_PAGE_BYTES,
) -> RenderedPage:
    """把图片附件变成一页「页图」。

    jpg/png/webp 原样透传（尺寸合规时）；其余（tiff/bmp/heic…）用 Pillow 转码，
    Pillow 打不开再交给 PyMuPDF 的图片文档兜底。**任何一步失败都返回带
    ``error`` 的页**，绝不返回空白图冒充成功。
    """
    normalized = (mime or "").lower().strip()
    if normalized in _PASSTHROUGH_MIMES and len(file_bytes) <= size_limit:
        size = _image_size(file_bytes)
        if size is not None and max(size) <= edge_limit:
            return RenderedPage(
                page_no=page_no,
                strategy=RenderStrategy.SOURCE_IMAGE,
                mime="image/jpeg" if normalized == "image/jpg" else normalized,
                image_bytes=file_bytes,
                width=size[0],
                height=size[1],
            )

    converted = _convert_image(file_bytes, fmt=fmt, edge_limit=edge_limit, size_limit=size_limit)
    if isinstance(converted, RenderedPage):
        return converted
    image_bytes, width, height = converted
    return _page_from_image(page_no, image_bytes, width, height, mime=_fmt_mime(fmt), dpi=0, cached=False)


def _image_size(file_bytes: bytes) -> tuple[int, int] | None:
    from PIL import Image

    try:
        with Image.open(io.BytesIO(file_bytes)) as image:
            return int(image.width), int(image.height)
    except Exception:
        return None


def _convert_image(
    file_bytes: bytes,
    *,
    fmt: str,
    edge_limit: int,
    size_limit: int,
) -> tuple[bytes, int, int] | RenderedPage:
    from PIL import Image

    try:
        with Image.open(io.BytesIO(file_bytes)) as image:
            image.load()
            working = image.convert("RGB") if image.mode not in ("RGB", "L") else image
            if max(working.width, working.height) > edge_limit:
                scale = edge_limit / max(working.width, working.height)
                working = working.resize(
                    (max(1, round(working.width * scale)), max(1, round(working.height * scale))),
                    Image.Resampling.LANCZOS,
                )
            for quality in (85, 70, 55):
                buf = io.BytesIO()
                if fmt == "jpeg":
                    working.save(buf, format="JPEG", quality=quality)
                else:
                    working.save(buf, format="PNG")
                payload = buf.getvalue()
                if len(payload) <= size_limit:
                    return payload, working.width, working.height
                if fmt != "jpeg":
                    break  # PNG 无损，降「质量」无意义，直接走失败分支
            return RenderedPage(
                page_no=1,
                strategy=RenderStrategy.SOURCE_IMAGE,
                error=RenderError.TOO_LARGE,
                detail=f"图片超过 {size_limit // 1024}KB 上限且无法再压缩",
            )
    except Exception as exc:
        logger.warning("图片转码失败: %s", exc)
        return RenderedPage(
            page_no=1,
            strategy=RenderStrategy.SOURCE_IMAGE,
            error=RenderError.UNSUPPORTED_MIME,
            detail=f"不支持或已损坏的图片：{exc}",
        )
