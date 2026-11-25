"""收件箱附件首页缩略图：让律师「扫一眼就知道这是什么材料」。

## 为什么必须服务端出图

收件箱里需要判断的是「这条要不要进材料预处理」，而列表能给的线索只有主题行。
扫描件的主题往往毫无信息（`Attached Image`、`1153_001.pdf`），真正能判断的是
**第 1 页长什么样**。前端要拿到这一页图只有两条路：

* 整份下载再本地渲染 —— 一本 40 页扫描件 26MB（`v27.23.9` 实测），二十行列表
  就是几百 MB，律师在会议里点开收件箱就卡住；
* 服务端渲染一张 320px 的 JPEG —— 约 15KB。

后者是唯一可用的那条。

## 三条纪律

1. **只在用户要「看」的时候出图**：端点由前端在展开附件条 / 点预览时调用，
   绝不随列表预取。200 行 × 一次 fitz 渲染 = 把服务端当渲图农场。
2. **落盘缓存，键含内容标识**：附件字节对 (message, part_index) 不可变，但
   「同名替换 / 重新同步」会换内容，所以 size + 文件名 + content_type 一起进
   键——否则会给出上一版文件的图。代价是「改名」会让旧键失效、白留一个约
   10KB 的孤儿（不清理也无害）；整条消息删除时 `purge_message_thumbnails`
   会把整目录收掉，这比「改名顺手清空、下次再全渲一遍」划算。
3. **渲染成本有上限**：目标宽度的 zoom 夹在 [0.12, 4.0] 之间；非 PDF / 位图
   在**取字节之前**就拒绝——不为一枚缩略图去 IMAP 拉一份 20MB 的 docx。

## 与 `attachment_page_service` 的分工

那边管**页数**（列表/阅读器拿去做初始分段，纯数字，永不失败）；这边管**图**
（重活、可失败、可缓存）。两者都读同一份 `attachments_meta`，所以 PDF 判定
复用 `is_pdf_attachment`，不各写一份。

## 为什么不复用 `apps.agent.services.attachment_render`

那个包是**给模型看**的页图渲染，与本模块有三处硬分歧，硬套只会两败俱伤：

* 它对有文字层的页**直接返回 `RenderStrategy.TEXT`、不出图**（模型读文本更便宜
  更准）——而缩略图要的就是图，文字层有没有都得画；
* 它的键是 `(attachment_id, page, dpi, fmt)` + 7 天 TTL + LRU，给对话里的
  反复引用设计；缩略图键要含内容指纹、而且一落盘就一直有效（附件不可变）；
* 它长在 `apps/agent` 下，message_hub 反过来依赖 agent 是分层倒置（实测两包
  互相没有 import，不应从本模块开这个头）。
"""

from __future__ import annotations

import hashlib
import io
import logging
import tempfile
from pathlib import Path
from typing import Any

from django.conf import settings

from apps.core.exceptions import NotFoundError, ValidationException
from apps.message_hub.models import InboxMessage
from apps.message_hub.services.attachment_page_service import is_pdf_attachment

logger = logging.getLogger("apps.message_hub")

#: 默认缩略图宽度（px）。320 在 2x 屏上够填满行内 44px 高的小样，也够抽屉里的
#: 96px 卡片；再大只是白花带宽——这一页永远不是用来读字的。
DEFAULT_THUMB_WIDTH = 320
#: 宽度上下限。下限 64：再小看不清版式；上限 640：超过这个宽度已经能读标题，
#: 该走「预览」而不是缩略图。
MIN_THUMB_WIDTH = 64
MAX_THUMB_WIDTH = 640

#: 缩略图缓存目录（MEDIA_ROOT 下）。按消息分目录，删除消息时整目录回收即可。
THUMB_DIR_NAME = "inbox_thumbnails"

#: PDF 渲染的 zoom 夹取范围。0.12 对应「A0 大图纸缩到 320px」，4.0 对应
#: 「名片大小的单据」，再往外就没有信息增量了。
_MIN_ZOOM = 0.12
_MAX_ZOOM = 4.0
#: 渲染结果的像素上限（宽 × 高）：极端长边（法院卷宗里的长表格）不至于
#: 生成一张 320×20000 的图把 PIL 内存打爆。
_MAX_PIXELS = 320 * 4000

_IMAGE_CONTENT_TYPES = frozenset(
    {
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/webp",
        "image/gif",
        "image/bmp",
        "image/tiff",
    }
)
_IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"})


def _fetch_errors() -> tuple[type[BaseException], ...]:
    """取字节可能抛的异常族（**不放宽成 Exception**，见 CLAUDE.md 红线）。

    三类来源各有一套异常：手工上传与本地读盘（``OSError`` / ``ValueError``）、
    IMAP（``imaplib.IMAP4.error``，含 abort）、一张网插件（``httpx.HTTPError`` /
    ``RuntimeError``）。按需拼装，缺哪个库就少一类——不因为可选依赖缺失让模块
    导入失败。
    """
    errors: tuple[type[BaseException], ...] = (ValueError, OSError, RuntimeError)
    try:
        import imaplib

        errors += (imaplib.IMAP4.error,)
    except ImportError:  # pragma: no cover - 标准库恒在
        pass
    try:
        import httpx

        errors += (httpx.HTTPError,)
    except ImportError:  # pragma: no cover - httpx 是硬依赖，理论上进不来
        pass
    return errors


def _safe_int(value: Any, default: int = -1) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def find_attachment_meta(message: InboxMessage, part_index: int) -> dict[str, Any]:
    """取 `attachments_meta` 里 part_index 对应的那份（找不到抛 NotFoundError）。

    Raises:
        NotFoundError: 该 part_index 不在 meta 里。
    """
    for att in message.attachments_meta or []:
        if isinstance(att, dict) and _safe_int(att.get("part_index", -1)) == int(part_index):
            return att
    raise NotFoundError(f"附件 part_index={part_index} 不存在")


def thumbnail_kind(att: dict[str, Any]) -> str | None:
    """这份附件能出什么图：``"pdf"`` / ``"image"`` / ``None``（不支持）。

    判定只看 meta（content_type + 文件名），**不碰字节**——不支持的类型要能在
    发起网络拉取之前就被拒掉。
    """
    if is_pdf_attachment(att):
        return "pdf"
    content_type = str(att.get("content_type") or "").split(";")[0].strip().lower()
    if content_type in _IMAGE_CONTENT_TYPES:
        return "image"
    name = str(att.get("filename") or att.get("original_filename") or "").lower()
    if Path(name).suffix in _IMAGE_SUFFIXES:
        return "image"
    return None


def thumbnail_dir(message_pk: int) -> Path:
    """该消息的缩略图目录（按消息隔离，删除消息时整目录可回收）。"""
    return Path(settings.MEDIA_ROOT) / THUMB_DIR_NAME / str(int(message_pk))


def thumbnail_cache_key(message_pk: int, part_index: int, att: dict[str, Any], *, page: int, width: int) -> str:
    """缓存键：内容标识 + 渲染参数。

    size / 文件名 / content_type 一起进键，是因为「同名文件被替换」在真实数据里
    会发生（重新同步同一封邮件、客户重传同名扫描件）——只按 (message, part)
    做键会给出上一版内容的图。
    """
    raw = "|".join(
        [
            str(int(message_pk)),
            str(int(part_index)),
            str(int(page)),
            str(int(width)),
            str(_safe_int(att.get("size", 0), default=0)),
            str(att.get("filename") or att.get("original_filename") or ""),
            str(att.get("content_type") or ""),
        ]
    )
    # 用途是缓存键而非安全凭证，但 bandit 仍会拦 md5/sha1；用 sha256 免争议
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def clamp_width(width: int) -> int:
    """把请求宽度夹进 [MIN, MAX]（前端传 0 / 负 / 巨大值都不该打穿服务）。"""
    return max(MIN_THUMB_WIDTH, min(MAX_THUMB_WIDTH, int(width)))


def build_attachment_thumbnail(
    message: InboxMessage,
    part_index: int,
    *,
    page: int = 1,
    width: int = DEFAULT_THUMB_WIDTH,
) -> tuple[Path, str]:
    """生成（或命中缓存）一份缩略图，返回 ``(文件路径, etag)``。

    etag 就是缓存键：同一份附件 + 同一套渲染参数恒得同一个值，可直接用于
    ``If-None-Match``。

    Raises:
        NotFoundError: part_index 不存在。
        ValidationException: 类型不支持 / 页码越界 / 取字节或渲染失败。
    """
    att = find_attachment_meta(message, part_index)
    safe_width = clamp_width(width)
    safe_page = max(1, int(page))

    kind = thumbnail_kind(att)
    if kind is None:
        raise ValidationException(
            message="该附件不是 PDF 或图片，无法生成预览图",
            code="INBOX_NO_THUMBNAIL",
            errors={"part_index": part_index},
        )

    key = thumbnail_cache_key(message.pk, part_index, att, page=safe_page, width=safe_width)
    cached = thumbnail_dir(message.pk) / f"{key}.jpg"
    if cached.is_file() and cached.stat().st_size > 0:
        logger.debug("缩略图命中缓存 message=%s part=%s page=%s", message.pk, part_index, safe_page)
        return cached, key

    content = _load_attachment_bytes(message, part_index)
    data = _render_jpeg(
        content, kind=kind, page=safe_page, width=safe_width, message_pk=message.pk, part_index=part_index
    )
    _write_atomic(cached, data)
    logger.info(
        "生成附件缩略图 message=%s part=%s page=%s width=%s bytes=%d",
        message.pk,
        part_index,
        safe_page,
        safe_width,
        len(data),
    )
    return cached, key


def purge_message_thumbnails(message_pk: int) -> int:
    """回收某条消息的全部缩略图，返回删除的文件数。

    尽力而为：删消息本身已经成功，缩略图清不掉不该反过来报错。
    """
    import shutil

    target = thumbnail_dir(message_pk)
    if not target.is_dir():
        return 0
    removed = sum(1 for p in target.glob("*.jpg"))
    try:
        shutil.rmtree(target)
    except OSError as exc:
        logger.warning("回收缩略图目录失败 message=%s path=%s: %s", message_pk, target, exc)
        return 0
    return removed


# ---------------------------------------------------------------------------
# 内部实现
# ---------------------------------------------------------------------------


def _load_attachment_bytes(message: InboxMessage, part_index: int) -> bytes:
    """按需取附件字节（本地优先，IMAP / 一张网回落到各自的 fetcher）。

    与 API 层 ``_serve_attachment`` 走同一条路：本地上传读 media、IMAP 先查
    `attachments_meta[].local_path` 再连服务器——所以**能命中本地就绝不联网**。
    """
    from apps.message_hub.services import get_fetcher

    try:
        fetcher = get_fetcher(message.source.source_type)
        content, _filename, _content_type = fetcher.download_attachment(message.source, message.message_id, part_index)
    except _fetch_errors() as exc:
        logger.warning(
            "取附件字节失败，无法生成缩略图 message=%s part=%s: %s",
            message.pk,
            part_index,
            exc,
        )
        raise ValidationException(
            message="附件读取失败，无法生成预览图",
            code="INBOX_THUMBNAIL_FETCH_FAILED",
            errors={"part_index": part_index},
        ) from exc
    return bytes(content)


def _render_jpeg(content: bytes, *, kind: str, page: int, width: int, message_pk: int, part_index: int) -> bytes:
    """把 PDF 的一页 / 一张位图渲染成目标宽度的 JPEG。"""
    from PIL import Image

    try:
        if kind == "pdf":
            image = _pdf_page_image(content, page=page, width=width, message_pk=message_pk, part_index=part_index)
        else:
            image = _image_page_image(content, width=width)
    except (ValueError, RuntimeError, OSError) as exc:
        # PyMuPDF 的 FileDataError / EmptyFileError 都是 RuntimeError 族，
        # PIL 解码失败是 OSError/ValueError —— 三类都在这里收口
        logger.warning("缩略图渲染失败 message=%s part=%s page=%s: %s", message_pk, part_index, page, exc)
        raise ValidationException(
            message="附件已损坏或格式无法解析，无法生成预览图",
            code="INBOX_THUMBNAIL_RENDER_FAILED",
            errors={"part_index": part_index},
        ) from exc

    encoded = io.BytesIO()
    image.save(encoded, format="JPEG", quality=82, optimize=True)
    return encoded.getvalue()


def _pdf_page_image(content: bytes, *, page: int, width: int, message_pk: int, part_index: int) -> Any:
    """PDF 的第 page 页（1 起）→ PIL Image，宽度收敛到 target。"""
    import pymupdf as fitz
    from PIL import Image

    with fitz.open(stream=content, filetype="pdf") as doc:
        total = int(doc.page_count)
        if total <= 0:
            raise ValueError("PDF 没有页面")
        if page > total:
            raise ValidationException(
                message=f"页码超出范围：该附件只有 {total} 页",
                code="INBOX_THUMBNAIL_PAGE_OUT_OF_RANGE",
                errors={"page": page, "page_count": total},
            )
        pdf_page = doc.load_page(page - 1)
        base_width = float(pdf_page.rect.width) or 595.0
        zoom = max(_MIN_ZOOM, min(_MAX_ZOOM, width / base_width))
        pix = pdf_page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        raw = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

    logger.debug("PDF 缩略图渲染 message=%s part=%s size=%sx%s", message_pk, part_index, pix.width, pix.height)
    return _fit_size(raw, width)


def _image_page_image(content: bytes, *, width: int) -> Any:
    """位图附件 → PIL Image（取首帧，转换到 RGB 以便编码 JPEG）。"""
    from PIL import Image

    with Image.open(io.BytesIO(content)) as opened:
        # GIF / TIFF 多帧：缩略图只取第一帧（与「这是哪份材料」的用途一致）
        converted = opened.convert("RGB")
    return _fit_size(converted, width)


def _resample_lanczos() -> Any:
    """Pillow 的 LANCZOS 常量。

    Pillow ≥ 9.1 把它挪进了 `Image.Resampling`，旧版只有 `Image.LANCZOS`；
    用 getattr 兼容两代（同 `chat_records/services/export/pdf_export_service.py`
    的取法），同时让 mypy 拿到 Any 而不是被常量搬家打红。
    """
    from PIL import Image as pil_image

    return getattr(pil_image, "Resampling", pil_image).LANCZOS


def _fit_size(image: Any, width: int) -> Any:
    """把 PIL 图收敛到目标宽度（等比缩放 + 像素总量上限）。"""
    target_w = min(int(width), int(image.width)) or 1
    target_h = max(1, round(image.height * target_w / max(1, image.width)))
    if target_w * target_h > _MAX_PIXELS:
        # 极端长边（超长表格扫描件）：按像素预算再压一次高度
        target_h = max(1, _MAX_PIXELS // target_w)
    if (target_w, target_h) == (image.width, image.height):
        return image
    return image.resize((target_w, target_h), _resample_lanczos())


def _write_atomic(path: Path, data: bytes) -> None:
    """同目录临时文件 + rename，避免并发读到写了一半的 JPEG。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".thumb-", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with open(fd, "wb") as handle:
            handle.write(data)
        tmp_path.replace(path)
    except OSError:
        tmp_path.unlink(missing_ok=True)
        raise
