"""对话附件的「页图」渲染 —— 让模型真正**看到**扫描件 / 图片。

## 为什么需要这一层

``read_agent_attachment`` 走的是文本提取链路。扫描版 PDF 没有文字层，
PyMuPDF 的 ``page.get_text()`` 返回空串而解析端点仍报 ``success=True``，
于是模型拿到 ``chars: 0`` 的正文，只能回答「我没看到内容」——用户以为
附件已发送，实际整份材料对模型不可见。

图片文件同理：``get_text()`` 对图片没有意义，必须走视觉通道。而视觉通道
要求「把页面渲染成图片交回模型」，不是文本。所以本模块只做一件事：
**把指定的页变成模型能吃的图片字节**，并把「为什么变不出来」讲清楚。

## 三层取舍

1. **页粒度决定要不要图**：PDF 的文字层判断按**页**做，不按文档做。
   一份合同常是前几页扫描件、后几页电子签，按文档判会把电子页也白渲染。
2. **体积受控**：单页长边 ≤ :data:`MAX_EDGE_PX`、单页 ≤ :data:`MAX_PAGE_BYTES`。
   超了就按 :data:`DPI_LADDER` 逐档降 dpi 重渲染；仍超限的页标
   ``too_large`` **留在结果里**，不静默丢页——丢页会让模型把缺页当「文档就这么长」。
3. **向模型隐藏失败**：渲染结果是统一的 content blocks，失败原因只进服务端日志
   与 ``RenderResult.pages``，模型看到的是「第 3 页读取失败（加密，未解密）」这类
   人话，而不是空内容。

## 缓存为什么要放独立目录

渲染一页扫描件要 100-500ms，同一份材料在一次对话里会被反复引用。缓存落在
``MEDIA_ROOT/agent_attachment_cache/``（**不**在 ``agent_attachments/`` 下）：
附件清理逻辑按 ``agent_attachments/<年>/<月>/`` 扫物理文件，缓存混在里面会被误删；
反过来缓存目录也可以整体清空而不影响任何附件记录。

缓存键含源文件 ``size``/``mtime`` 指纹：用户删掉附件重传时 uuid 会变，但同名覆盖
写入同一个 attachment_id 的场景不能让它命中旧图（脏命中会让模型看到上一份文件）。
"""

from __future__ import annotations

import enum
import hashlib
import io
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

#: 页图长边上限。对齐主流多模态模型的原生视觉输入尺寸（1568 是各家 tokenizer
#: 的常用切块边长）：再大的图会被服务端缩回去，白白多传几十万字节。
MAX_EDGE_PX = 1568
#: 单页字节上限。按 base64 后 4/3 膨胀估算，1.5MB 原始 ≈ 2MB 传输，
#: 10 页就在一次工具返回的可接受范围内。
MAX_PAGE_BYTES = 1536 * 1024
#: 降 dpi 的档位（从高到低）。300 是印刷件细节底线，72 是「能看出有这页」的底线。
DPI_LADDER = (300, 200, 150, 120, 96, 72)
#: 页文字层判定阈值：短于这个字符数的页当作扫描页。
#: 取 50 是因为真实电子页几乎不会只有几十字（标题页例外，但标题页用图也无害，
#: 而无文字层的扫描页渲染出来才对模型有价值——宁可多渲染一页，不可漏页）。
MIN_TEXT_CHARS = 50
#: 单次调用最多渲染页数（防一次拖 300 页扫描件打爆时间与上下文）。
DEFAULT_MAX_PAGES = 20
#: 缓存存活时间与磁盘上限。
DEFAULT_CACHE_TTL_SECONDS = 7 * 24 * 3600
DEFAULT_CACHE_MAX_BYTES = 512 * 1024 * 1024


class RenderError(enum.StrEnum):
    """渲染失败的原因分类。

    必须区分而不是统一成「失败」：``encrypted`` 要提示用户「请上传解密版」，
    ``page_out_of_range`` 要提示用户「这份材料只有 5 页」，``too_large`` 是
    「这页太复杂，请分开查询」——三者的下一步动作完全不同。
    """

    NOT_FOUND = "not_found"
    FORBIDDEN = "forbidden"
    PARSE_EMPTY = "parse_empty"
    ENCRYPTED = "encrypted"
    UNSUPPORTED_MIME = "unsupported_mime"
    TOO_LARGE = "too_large"
    PAGE_OUT_OF_RANGE = "page_out_of_range"


class RenderStrategy(enum.StrEnum):
    """该页最终交给模型的形态。"""

    #: 文字层足够，模型不需要图（页图里 text 字段有正文）
    TEXT = "text"
    #: 把页渲染成图片，模型走视觉通道
    PAGE_IMAGE = "page_image"
    #: 图片附件直接透传原字节（不重复编码，避免二次压缩损失）
    SOURCE_IMAGE = "source_image"


@dataclass
class RenderedPage:
    """一页的渲染结果。

    ``image_bytes`` 与 ``error`` 互斥：有图就是成功，没图必须带原因——
    这正是本模块存在的目的（禁止「空内容 + 假装成功」）。
    """

    page_no: int
    """1-based 页码（对外唯一编号口径）。"""

    strategy: RenderStrategy
    mime: str = ""
    image_bytes: bytes | None = None
    text: str = ""
    width: int = 0
    height: int = 0
    dpi: int = 0
    error: RenderError | None = None
    detail: str = ""
    cached: bool = False

    @property
    def size_bytes(self) -> int:
        return len(self.image_bytes) if self.image_bytes else 0


@dataclass
class RenderResult:
    """一次渲染的完整结果（含失败页，缺页信息不能被丢掉）。"""

    attachment_id: str
    filename: str = ""
    mime: str = ""
    #: 1-based 的原始页码清单（未截断前）
    requested_pages: list[int] = field(default_factory=list)
    #: 实际处理的页码（受 max_pages 限制）
    pages: list[RenderedPage] = field(default_factory=list)
    #: 文档总页数（非 PDF 恒为 1）
    total_pages: int = 0
    #: 超出 max_pages 而未处理的页数
    truncated_pages: int = 0
    error: RenderError | None = None
    detail: str = ""

    @property
    def ok(self) -> bool:
        """至少有一页真的拿到了内容。"""
        return self.error is None and any(p.image_bytes or p.text for p in self.pages)

    @property
    def total_bytes(self) -> int:
        return sum(p.size_bytes for p in self.pages)


# ── 页码解析 ──────────────────────────────────────────────────────


_RANGE_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")


def parse_pages(
    spec: str | int | list[int] | tuple[int, ...] | None,
    total_pages: int,
    max_pages: int = DEFAULT_MAX_PAGES,
) -> tuple[list[int], int]:
    """把用户给的页范围解成 1-based 页码列表，返回 ``(pages, truncated_count)``。

    支持形态：``"1-3"``（区间）/ ``"7"``（单页）/ ``"all"`` / ``"1,3,5"`` /
    ``[1, 5]`` / ``None``（默认前 ``max_pages`` 页）。对外一律 1-based——
    对律师说「第 0 页」没有意义。

    Raises:
        ValueError: 页码超出 ``[1, total_pages]``（调用方转 ``page_out_of_range``）。
            这里用异常而不是返回值，是因为「越界」不是可降级的结果：整次请求
            没有意义，必须让调用方拿到明确的失败信号，不能悄悄夹逼到边界页。
    """
    limit = max(1, int(max_pages))
    if spec is None or (isinstance(spec, str) and not spec.strip()) or spec == "all":
        pages = list(range(1, total_pages + 1))
    else:
        pages = _expand_spec(spec, total_pages)
    unique = sorted(set(pages))
    if not unique:
        raise ValueError(f"没有可用的页码：{spec!r}")
    return unique[:limit], max(0, len(unique) - limit)


def _expand_spec(spec: str | int | list[int] | tuple[int, ...], total_pages: int) -> list[int]:
    if isinstance(spec, int):
        _check_page(spec, total_pages)
        return [spec]
    if isinstance(spec, list | tuple):
        out: list[int] = []
        for item in spec:
            _check_page(int(item), total_pages)
            out.append(int(item))
        return out

    out = []
    for part in str(spec).replace("，", ",").split(","):
        token = part.strip()
        if not token:
            continue
        matched = _RANGE_RE.match(token)
        if matched:
            start, end = int(matched.group(1)), int(matched.group(2))
            if start > end:
                raise ValueError(f"页区间起点大于终点：{token!r}")
            _check_page(start, total_pages)
            _check_page(end, total_pages)
            out.extend(range(start, end + 1))
            continue
        if not token.isdigit():
            raise ValueError(f"无法解析的页范围：{token!r}（应形如 '1-3' / '7' / 'all'）")
        _check_page(int(token), total_pages)
        out.append(int(token))
    return out


def _check_page(page_no: int, total_pages: int) -> None:
    if page_no < 1 or page_no > max(1, total_pages):
        raise ValueError(f"页码 {page_no} 超出范围 [1, {total_pages}]")


# ── 渲染 ──────────────────────────────────────────────────────────


def render_pdf_pages(
    file_bytes: bytes,
    pages: list[int],
    *,
    attachment_id: str = "",
    dpi: int = 200,
    fmt: str = "png",
    use_cache: bool = True,
    size_limit: int = MAX_PAGE_BYTES,
    edge_limit: int = MAX_EDGE_PX,
    ladder: tuple[int, ...] = DPI_LADDER,
) -> list[RenderedPage]:
    """把 PDF 指定页渲染为图片，逐页返回（含失败页）。

    流程：打开 → 页粒度文字层判断 → 需要图的页按 ``dpi`` 渲染 → 超长边等比
    降采样 → 超字节上限按 ``ladder`` 逐档降 dpi 重渲染 → 仍超限标 ``too_large``。
    """
    import pymupdf as fitz

    doc = _open_pdf(file_bytes)
    if isinstance(doc, RenderedPage):
        # 整份打不开（加密/损坏）：每一页都带上同样的原因，页数不丢
        return [
            RenderedPage(page_no=p, strategy=RenderStrategy.PAGE_IMAGE, error=doc.error, detail=doc.detail)
            for p in pages
        ]

    try:
        results: list[RenderedPage] = []
        for page_no in pages:
            if page_no > doc.page_count:
                results.append(
                    RenderedPage(
                        page_no=page_no,
                        strategy=RenderStrategy.PAGE_IMAGE,
                        error=RenderError.PAGE_OUT_OF_RANGE,
                        detail=f"文档只有 {doc.page_count} 页",
                    )
                )
                continue
            results.append(
                _render_one_pdf_page(
                    doc,
                    page_no,
                    attachment_id=attachment_id,
                    dpi=dpi,
                    fmt=fmt,
                    use_cache=use_cache,
                    size_limit=size_limit,
                    edge_limit=edge_limit,
                    ladder=ladder,
                )
            )
        return results
    finally:
        doc.close()


def _open_pdf(file_bytes: bytes) -> Any:
    """打开 PDF；打不开或加密未解密时返回一个「只带错误」的 ``RenderedPage`` 作哨兵。"""
    import pymupdf as fitz

    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as exc:
        logger.warning("PDF 打开失败: %s", exc)
        return RenderedPage(
            page_no=0,
            strategy=RenderStrategy.PAGE_IMAGE,
            error=RenderError.UNSUPPORTED_MIME,
            detail=f"不是可解析的 PDF：{exc}",
        )
    if not doc.needs_pass:
        return doc

    # 无口令的「权限加密」PDF 很常见（下载站批量化加水印），authenticate("") 能过。
    # 空串都过不了说明真需要口令——不要尝试爆破，直接告诉用户原因。
    if doc.authenticate(""):
        return doc
    doc.close()
    return RenderedPage(
        page_no=0,
        strategy=RenderStrategy.PAGE_IMAGE,
        error=RenderError.ENCRYPTED,
        detail="PDF 需要打开口令，未解密无法读取内容",
    )


def _render_one_pdf_page(
    doc: Any,
    page_no: int,
    *,
    attachment_id: str,
    dpi: int,
    fmt: str,
    use_cache: bool,
    size_limit: int,
    edge_limit: int,
    ladder: tuple[int, ...],
) -> RenderedPage:
    page = doc.load_page(page_no - 1)
    text = (page.get_text() or "").strip()
    if len(text) >= MIN_TEXT_CHARS:
        # 有文字层：模型读文本比读图更快更准（且不烧视觉 token）
        return RenderedPage(page_no=page_no, strategy=RenderStrategy.TEXT, text=text)

    tried: list[int] = []
    # 首轮用调用方要求的 dpi，其后按阶梯降档；阶梯里比要求值更高的档跳过
    # （用户选了 150 就没必要先用 300 渲染一遍）。
    candidates = [int(dpi)] + [d for d in ladder if d < int(dpi)]
    for candidate in candidates:
        tried.append(candidate)
        cached = _cache_lookup(attachment_id, page_no, candidate, fmt) if use_cache else None
        if cached is not None:
            return _page_from_image(
                page_no,
                cached[0],
                cached[1],
                cached[2],
                mime=_fmt_mime(fmt),
                dpi=candidate,
                cached=True,
            )

        image_bytes, width, height = _rasterize(page, candidate, fmt, edge_limit)
        if len(image_bytes) > size_limit:
            continue
        if use_cache and attachment_id:
            _cache_store(attachment_id, page_no, candidate, fmt, image_bytes, width, height)
        return _page_from_image(page_no, image_bytes, width, height, mime=_fmt_mime(fmt), dpi=candidate, cached=False)

    return RenderedPage(
        page_no=page_no,
        strategy=RenderStrategy.PAGE_IMAGE,
        dpi=tried[-1] if tried else 0,
        error=RenderError.TOO_LARGE,
        detail=f"该页在 dpi={tried} 各档下均超过 {size_limit // 1024}KB 上限",
    )


def _rasterize(page: Any, dpi: int, fmt: str, edge_limit: int) -> tuple[bytes, int, int]:
    """渲染一页并按长边上限等比降采样，返回 ``(bytes, width, height)``。

    降采样用 Pillow 的 LANCZOS：PyMuPDF 直接按更小 dpi 重渲染在文字上更锐利，
    但「已经是最高档 dpi 还超长边」时只能后缩（否则要反向猜一个正好 1568 的 dpi），
    两者在视觉上对模型等价。
    """
    pix = page.get_pixmap(dpi=dpi)
    width, height = pix.width, pix.height
    if max(width, height) <= edge_limit:
        return pix.tobytes(fmt), width, height

    from PIL import Image

    scale = edge_limit / max(width, height)
    new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    image = Image.frombytes("RGB", (width, height), pix.samples).resize(new_size, Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    image.save(buf, format="JPEG" if fmt == "jpeg" else "PNG", **({"quality": 85} if fmt == "jpeg" else {}))
    return buf.getvalue(), new_size[0], new_size[1]


def _page_from_image(
    page_no: int,
    image_bytes: bytes,
    width: int,
    height: int,
    *,
    mime: str,
    dpi: int,
    cached: bool,
) -> RenderedPage:
    return RenderedPage(
        page_no=page_no,
        strategy=RenderStrategy.PAGE_IMAGE,
        mime=mime,
        image_bytes=image_bytes,
        width=width,
        height=height,
        dpi=dpi,
        cached=cached,
    )


def _fmt_mime(fmt: str) -> str:
    return "image/jpeg" if fmt == "jpeg" else "image/png"


# ── 图片附件 ──────────────────────────────────────────────────────

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


# ── 缓存 ──────────────────────────────────────────────────────────


class RenderCache:
    """页图磁盘缓存：LRU（按 mtime）+ TTL + 总量上限。

    键 = ``(attachment_id, page_no, dpi, format)`` + 源文件 ``size``/``mtime``
    指纹，摘要成文件名。指纹放在键里而不是只放 mtime 校验：同一 attachment_id
    被覆盖写入后（重传同名文件）旧图必然失配，不需要额外的失效通知。
    """

    def __init__(
        self,
        root: Path,
        *,
        ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
        max_bytes: int = DEFAULT_CACHE_MAX_BYTES,
    ) -> None:
        self.root = Path(root)
        self.ttl_seconds = ttl_seconds
        self.max_bytes = max_bytes

    def key(
        self, attachment_id: str, page_no: int, dpi: int, fmt: str, *, source_size: int = 0, source_mtime: float = 0.0
    ) -> str:
        raw = f"{attachment_id}|{page_no}|{dpi}|{fmt}|{source_size}|{int(source_mtime)}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def path_for(self, key: str) -> Path:
        # 两级散列目录：单目录塞几十万小文件会让 readdir 变慢
        return self.root / key[:2] / f"{key}.bin"

    def get(self, key: str, *, now: float | None = None) -> tuple[bytes, int, int] | None:
        path = self.path_for(key)
        try:
            stat = path.stat()
        except OSError:
            return None
        current = time.time() if now is None else now
        if current - stat.st_mtime > self.ttl_seconds:
            _unlink(path)
            return None
        try:
            payload = path.read_bytes()
        except OSError:
            return None
        # 首 8 字节存宽高（各 4 字节），省一次图片解码就知道尺寸
        if len(payload) < 8:
            _unlink(path)
            return None
        width = int.from_bytes(payload[0:4], "big")
        height = int.from_bytes(payload[4:8], "big")
        os.utime(path, None)  # 命中即刷新 mtime，实现「最久未用先淘汰」
        return payload[8:], width, height

    def put(self, key: str, image_bytes: bytes, width: int, height: int) -> None:
        path = self.path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        header = width.to_bytes(4, "big") + height.to_bytes(4, "big")
        # 先写临时文件再 rename：并发读不会看到半截文件
        tmp = path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_bytes(header + image_bytes)
        tmp.replace(path)
        self.evict()

    def evict(self, *, now: float | None = None) -> int:
        """按 TTL 删过期，再按 mtime 最旧先删直到总量达标；返回删除的条目数。"""
        current = time.time() if now is None else now
        entries: list[tuple[float, int, Path]] = []
        removed = 0
        for path in self.root.rglob("*.bin") if self.root.exists() else []:
            try:
                stat = path.stat()
            except OSError:
                continue
            if current - stat.st_mtime > self.ttl_seconds:
                _unlink(path)
                removed += 1
                continue
            entries.append((stat.st_mtime, stat.st_size, path))

        total = sum(size for _, size, _ in entries)
        if total <= self.max_bytes:
            return removed
        for _mtime, size, path in sorted(entries):
            _unlink(path)
            removed += 1
            total -= size
            if total <= self.max_bytes:
                break
        return removed

    def clear(self) -> None:
        for path in self.root.rglob("*.bin") if self.root.exists() else []:
            _unlink(path)


def _unlink(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        # 缓存清理是尽力而为：文件可能已被其他进程（或上一个请求）先删掉。
        # 这类失败不影响渲染结果，走降级分支正常继续，记 debug 即可。
        logger.debug("删除渲染缓存文件失败（已忽略）: %s", path, exc_info=True)


def cache_root() -> Path:
    """缓存根目录：独立于 ``agent_attachments/``，见模块 docstring。"""
    return Path(settings.MEDIA_ROOT) / "agent_attachment_cache"


def get_cache() -> RenderCache:
    return RenderCache(cache_root())


def _cache_lookup(attachment_id: str, page_no: int, dpi: int, fmt: str) -> tuple[bytes, int, int] | None:
    cache = get_cache()
    return cache.get(cache.key(attachment_id, page_no, dpi, fmt))


def _cache_store(attachment_id: str, page_no: int, dpi: int, fmt: str, payload: bytes, width: int, height: int) -> None:
    cache = get_cache()
    cache.put(cache.key(attachment_id, page_no, dpi, fmt), payload, width, height)


# ── 审计日志 ──────────────────────────────────────────────────────


def log_render(
    *,
    who: Any,
    result: RenderResult,
    strategy: str = "",
    elapsed_ms: int = 0,
) -> None:
    """渲染审计：谁、读了哪个附件、读了几页、走什么策略、多大。

    用 ``extra`` 结构化输出（不拼字符串），日志系统可按字段聚合——
    「附件读不出来」是这类问题的唯一线索，必须能按 attachment_id 反查。
    """
    logger.info(
        "agent 附件渲染 attachment_id=%s who=%s pages=%s strategy=%s bytes=%s ok=%s error=%s elapsed_ms=%s",
        result.attachment_id,
        who,
        [p.page_no for p in result.pages],
        strategy or ",".join(sorted({str(p.strategy) for p in result.pages})),
        result.total_bytes,
        result.ok,
        result.error or "",
        elapsed_ms,
        extra={
            "who": who,
            "attachment_id": result.attachment_id,
            "pages": [p.page_no for p in result.pages],
            "strategy": strategy,
            "bytes": result.total_bytes,
            "ok": result.ok,
            "error": str(result.error or ""),
            "elapsed_ms": elapsed_ms,
        },
    )
