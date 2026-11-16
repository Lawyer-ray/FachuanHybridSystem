"""OCR 子系统：并行识别 / 缓存 / 配置解析。"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pymupdf as fitz
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from apps.automation.services.ocr.ocr_service import OCRService  # 保留直接构造：需要运行时 use_v5 参数控制精度/速度
from apps.document_parsing.protocols.document_parser_protocol import normalize_block_type
from apps.pdf_splitting.models import PdfSplitOcrProfile

from .dual_engine import normalize_paddleocr_vl_blocks
from .split_models import OCRPageResult, OCRRuntimeProfile

logger = logging.getLogger("apps.pdf_splitting")

#: VL 兜底页版面的坐标基准：与 MinerU 同为千分比，页尺寸随之记 1000×1000。
#:
#: 为什么不保留 VL 的绝对像素：``bbox.resolve_bbox_unit`` 只认 mineru（千分比）与
#: textin（绝对）两种单位，而 ``build_segments_markdown`` 整段只收**一个** bbox_backend。
#: 一份卷宗里混着 MinerU 页与 VL 兜底页时，只有把两者收敛到同一套量纲，
#: 兜底页的绿框才不会按千分比去除绝对像素（框会飘到页外）。
#: 记 width/height=1000 后，绝对单位分支除以页宽高也得到同一结果。
_VL_LAYOUT_SIDE = 1000.0

#: 云端平台的 source_method 前缀（``mineru_ocr`` / ``textin_empty`` …）。
#: 缓存命中时靠它恢复真实来源——档案名记的是**首选**平台，容灾后可能名不副实。
_CLOUD_METHOD_PREFIXES = ("mineru", "textin")


def cloud_backend_of_method(source_method: str) -> str:
    """从取字来源标记里认出云端平台；认不出返回空串（本地 OCR / 文本层没有平台）。"""
    name = str(source_method or "").strip().lower()
    for prefix in _CLOUD_METHOD_PREFIXES:
        if name == prefix or name.startswith(f"{prefix}_"):
            return prefix
    return ""


def vl_page_layout(layout_results: Any, *, page_no: int, text: str) -> dict[str, Any] | None:
    """PaddleOCR-VL 的 ``layoutParsingResults`` → ``PageDescriptor.layout`` 形状。

    块类型走 document_parsing 现成的归一化表（``doc_title`` → title 等），不在这里
    另造一套词汇；坐标复用 ``normalize_paddleocr_vl_blocks``（它已处理多边形回退、
    缺页尺寸、退化框）。算不出坐标的块**只保留文字**：前端不画框，但正文不丢。

    拿不到任何块时返回 None——调用方据此走「无版面」分支，而不是拿一个空壳
    冒充结构化结果。
    """
    pruned = [item.get("prunedResult") for item in layout_results or [] if isinstance(item, dict)]
    blocks = normalize_paddleocr_vl_blocks(pruned)
    if not blocks:
        return None
    out: list[dict[str, Any]] = []
    for block in blocks:
        item: dict[str, Any] = {
            "type": normalize_block_type(block.block_type),
            "text": block.text,
            "text_level": None,
        }
        rect = block.rect or {}
        if rect:
            x, y = float(rect["x"]), float(rect["y"])
            item["bbox"] = [
                round(x * _VL_LAYOUT_SIDE, 2),
                round(y * _VL_LAYOUT_SIDE, 2),
                round((x + float(rect["w"])) * _VL_LAYOUT_SIDE, 2),
                round((y + float(rect["h"])) * _VL_LAYOUT_SIDE, 2),
            ]
        out.append(item)
    return {
        "page_no": page_no,
        "blocks": out,
        "text": text,
        "width": _VL_LAYOUT_SIDE,
        "height": _VL_LAYOUT_SIDE,
    }


def _rescale_region_blocks(blocks: list[dict[str, Any]], *, region: list[float]) -> list[dict[str, Any]]:
    """裁剪图内的千分比坐标 → 整页千分比坐标。

    裁剪图自己也是一整页（VL 按它自己的宽高归一），所以先按区域宽高放大，
    再平移到区域在整页里的起点。没有 bbox 的块原样保留（正文不丢，只是画不出框）。
    """
    x0, y0, x1, y1 = region
    span_x, span_y = (x1 - x0) / _VL_LAYOUT_SIDE, (y1 - y0) / _VL_LAYOUT_SIDE
    out: list[dict[str, Any]] = []
    for block in blocks:
        bbox = block.get("bbox")
        if not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
            out.append(dict(block))
            continue
        shifted = dict(block)
        shifted["bbox"] = [
            round(x0 + float(bbox[0]) * span_x, 2),
            round(y0 + float(bbox[1]) * span_y, 2),
            round(x0 + float(bbox[2]) * span_x, 2),
            round(y0 + float(bbox[3]) * span_y, 2),
        ]
        out.append(shifted)
    return out


def _recognize_page(ocr_service: Any, image_bytes: bytes, *, page_no: int) -> tuple[str, dict[str, Any] | None]:
    """识别一页渲染图：优先拿**完整版面结果**，拿不到才退回纯文本。

    为什么不再直接调 ``recognize_bytes``：那层只返回拼好的文字，同一次响应里的
    ``layout_results``（块坐标）与印章图当场被丢掉。164 页实测有 29 页走这条兜底路径，
    它们本来就只有纯文本、没有坐标——而版面结果就在已经付过费的那次响应里。
    """
    result = ocr_service.recognize_layout(image_bytes)
    if result is None:
        # 本地引擎没有版面概念；云端版面调用失败时也走这里（与改动前同样的纯文本兜底）
        return str(ocr_service.recognize_bytes(image_bytes) or ""), None
    text = str(getattr(result, "text", "") or "")
    return text, vl_page_layout(getattr(result, "layout_results", None), page_no=page_no, text=text)


def _ocr_pages_worker(
    *,
    pdf_path: str,
    page_numbers: list[int],
    use_v5: bool,
    dpi: int,
) -> list[OCRPageResult]:  # pragma: no cover
    results: list[OCRPageResult] = []
    ocr_service = OCRService(use_v5=use_v5)
    try:
        with fitz.open(pdf_path) as doc:
            matrix = fitz.Matrix(dpi / 72, dpi / 72)
            for page_no in page_numbers:
                layout: dict[str, Any] | None = None
                try:
                    page = doc.load_page(page_no - 1)
                    pix = page.get_pixmap(matrix=matrix)
                    image_bytes = pix.tobytes("png")
                    text, layout = _recognize_page(ocr_service, image_bytes, page_no=page_no)
                    ocr_failed = not bool(text)
                except Exception:
                    logger.exception("pdf_split_page_ocr_worker_failed", extra={"page_no": page_no})
                    text = ""
                    ocr_failed = True
                results.append(
                    OCRPageResult(
                        page_no=page_no,
                        text=text,
                        source_method="ocr" if text else "ocr_failed",
                        ocr_failed=ocr_failed,
                        layout=layout,
                    )
                )
    except Exception:
        logger.exception("pdf_split_ocr_worker_failed", extra={"pdf_path": pdf_path})
        for page_no in page_numbers:
            results.append(
                OCRPageResult(
                    page_no=page_no,
                    text="",
                    source_method="ocr_failed",
                    ocr_failed=True,
                )
            )
    return results


class OCRHandler:
    """OCR 子系统的入口，封装并行识别、缓存、配置解析。"""

    def resolve_cloud_backend(self, cloud_backend: str | None = None) -> str | None:
        """首选云端识别后端（兼容旧调用方；需要容灾顺序请用 resolve_cloud_backends）。"""
        candidates = self.resolve_cloud_backends(cloud_backend)
        return candidates[0] if candidates else None

    def resolve_cloud_backends(self, cloud_backend: str | None = None) -> list[str]:
        """按尝试顺序给出云端平台列表。

        ``auto`` 返回全部可用平台（首个失败可切下一个 = 容灾）；
        锁定 mineru / textin 时只返回它本身（不允许偷偷降级）。
        """
        from apps.document_parsing.services.parser_factory import resolve_cloud_backends

        return [b for b in resolve_cloud_backends(cloud_backend) if b in {"mineru", "textin"}]

    def parse_cloud_pages(self, *, pdf_path: Path, backend: str) -> dict[int, OCRPageResult]:
        """一次解析整份 PDF，并恢复各解析块对应的原始页码。"""
        from apps.document_parsing.services import get_document_parser

        parsed = get_document_parser(backend=backend).parse_document(
            file_path=pdf_path.as_posix(),
            file_type="pdf",
            extract_tables=True,
            extract_images=False,
            return_markdown=False,
        )
        layout = parsed.layout or {}
        results: dict[int, OCRPageResult] = {}
        for page in layout.get("pages", []):
            if not isinstance(page, dict):
                continue
            try:
                page_no = int(str(page.get("page_no")))
            except (TypeError, ValueError):
                continue
            if page_no < 1:
                continue
            text = str(page.get("text") or "")
            results[page_no] = OCRPageResult(
                page_no=page_no,
                text=text,
                source_method=f"{backend}_ocr" if text else f"{backend}_empty",
                ocr_failed=not bool(text),
                layout=page,
            )
        if not results:
            raise ValueError(f"{backend} returned no page-indexed PDF results")
        return results

    def ocr_page_region(
        self,
        *,
        pdf_path: Path,
        page_no: int,
        region: list[float],
        runtime_profile: OCRRuntimeProfile,
    ) -> dict[str, Any] | None:  # pragma: no cover
        """只渲染并识别整页里的一块区域（千分比坐标），返回**整页坐标系**下的版面。

        为什么裁剪而不是整页重识别：MinerU 把照片/手写页当纯图片返回时，整页识别的
        有效分辨率被整页尺寸摊薄（579 实测身份证页只读出 45 字印章语，姓名/证号/住址
        全丢）。把图片区域单独按 OCR 档位 DPI 渲染出来，同一页的字段才有足够像素可读。

        返回 ``{"text": ..., "blocks": [...]}``；识别不出内容返回 None。块坐标已从
        裁剪图换算回整页千分比，调用方可以直接并进该页的版面。
        """
        try:
            with fitz.open(pdf_path) as doc:
                page = doc.load_page(page_no - 1)
                scale_x, scale_y = page.rect.width / 1000.0, page.rect.height / 1000.0
                clip = fitz.Rect(region[0] * scale_x, region[1] * scale_y, region[2] * scale_x, region[3] * scale_y)
                pix = page.get_pixmap(matrix=fitz.Matrix(runtime_profile.dpi / 72, runtime_profile.dpi / 72), clip=clip)
                image_bytes = pix.tobytes("png")
        except Exception:
            logger.exception("pdf_split_rescue_render_failed", extra={"page_no": page_no})
            return None

        text, layout = _recognize_page(OCRService(use_v5=runtime_profile.use_v5), image_bytes, page_no=page_no)
        if not text.strip():
            return None
        # 无版面（本地引擎）时整块文字就是整个裁剪图：坐标记裁剪图自己的千分比，
        # 下面统一换算回整页，避免两种来源走两套坐标口径。
        blocks = (layout or {}).get("blocks") or [
            {"type": "text", "text": text, "bbox": [0.0, 0.0, _VL_LAYOUT_SIDE, _VL_LAYOUT_SIDE]}
        ]
        return {"text": text, "blocks": _rescale_region_blocks(blocks, region=region)}

    def resolve_runtime_profile(self, profile_key: str) -> OCRRuntimeProfile:
        normalized = str(profile_key or "").strip().lower()
        cpu = max(1, os.cpu_count() or 1)
        profiles: dict[str, OCRRuntimeProfile] = {
            PdfSplitOcrProfile.FAST: OCRRuntimeProfile(
                key=PdfSplitOcrProfile.FAST,
                use_v5=False,
                dpi=140,
                workers=min(6, cpu),
            ),
            PdfSplitOcrProfile.BALANCED: OCRRuntimeProfile(
                key=PdfSplitOcrProfile.BALANCED,
                use_v5=True,
                dpi=200,
                workers=min(3, cpu),
            ),
            PdfSplitOcrProfile.ACCURATE: OCRRuntimeProfile(
                key=PdfSplitOcrProfile.ACCURATE,
                use_v5=True,
                dpi=220,
                workers=min(2, cpu),
            ),
        }
        return profiles.get(normalized, profiles[PdfSplitOcrProfile.BALANCED])

    def parallel_ocr(
        self,
        *,
        pdf_path: Path,
        page_numbers: list[int],
        runtime_profile: OCRRuntimeProfile,
    ) -> dict[int, OCRPageResult]:  # pragma: no cover
        if not page_numbers:
            return {}

        if runtime_profile.workers <= 1 or len(page_numbers) <= 1:
            result_list = _ocr_pages_worker(
                pdf_path=pdf_path.as_posix(),
                page_numbers=page_numbers,
                use_v5=runtime_profile.use_v5,
                dpi=runtime_profile.dpi,
            )
            return {item.page_no: item for item in result_list}

        results: dict[int, OCRPageResult] = {}
        chunks = _chunk_pages(page_numbers=page_numbers, chunk_count=runtime_profile.workers)
        with ThreadPoolExecutor(max_workers=runtime_profile.workers) as executor:
            future_map = {
                executor.submit(
                    _ocr_pages_worker,
                    pdf_path=pdf_path.as_posix(),
                    page_numbers=chunk,
                    use_v5=runtime_profile.use_v5,
                    dpi=runtime_profile.dpi,
                ): chunk
                for chunk in chunks
                if chunk
            }
            for future in as_completed(future_map):
                chunk = future_map[future]
                try:
                    for item in future.result():
                        results[item.page_no] = item
                except Exception:
                    logger.exception("pdf_split_parallel_ocr_failed_chunk", extra={"chunk_size": len(chunk)})
                    for item in _ocr_pages_worker(
                        pdf_path=pdf_path.as_posix(),
                        page_numbers=chunk,
                        use_v5=runtime_profile.use_v5,
                        dpi=runtime_profile.dpi,
                    ):
                        results[item.page_no] = item

        if len(results) < len(page_numbers):
            missing_pages = [page_no for page_no in page_numbers if page_no not in results]
            logger.warning(
                "pdf_split_parallel_ocr_missing_results",
                extra={"missing_pages": len(missing_pages), "total_pages": len(page_numbers)},
            )
            for item in _ocr_pages_worker(
                pdf_path=pdf_path.as_posix(),
                page_numbers=missing_pages,
                use_v5=runtime_profile.use_v5,
                dpi=runtime_profile.dpi,
            ):
                results[item.page_no] = item
        return results

    def sha256_file(self, file_path: Path) -> str:
        digest = hashlib.sha256()
        with file_path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def read_ocr_cache(self, *, pdf_hash: str, profile_key: str, page_no: int) -> OCRPageResult | None:
        cache_dir = _ocr_cache_dir(pdf_hash=pdf_hash, profile_key=profile_key)
        canonical_name = _ocr_cache_page_filename(page_no=page_no)
        names = [canonical_name] + [
            name for name in _ocr_cache_candidate_names(cache_dir=cache_dir, page_no=page_no) if name != canonical_name
        ]
        entries: list[_OcrCacheEntry] = []
        for name in names:
            entry = _load_ocr_cache_entry(
                storage=default_storage,
                rel_path=f"{cache_dir}/{name}",
                page_no=page_no,
            )
            if entry is not None:
                entries.append(entry)
        if not entries:
            return None

        best = max(entries, key=_ocr_cache_entry_key)
        best_name = best.name
        best_result = best.result

        if best_name != canonical_name:
            _promote_ocr_cache_entry(
                pdf_hash=pdf_hash,
                profile_key=profile_key,
                page_no=page_no,
                chosen_name=best_name,
            )
        return best_result

    def write_ocr_cache(self, *, pdf_hash: str, profile_key: str, result: OCRPageResult) -> None:
        rel_path = _ocr_cache_rel_path(pdf_hash=pdf_hash, profile_key=profile_key, page_no=result.page_no)
        payload = {
            "text": result.text,
            "ocr_failed": result.ocr_failed,
            "source_method": result.source_method,
            "layout": result.layout,
        }
        content = ContentFile(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        # default_storage.save 遇同名不覆盖而是改名（page_0001_0fm4T2l.json），
        # 于是一页会攒下几十份残档、固定名那份是哪次写的完全随机。先删再写保证幂等。
        try:
            if default_storage.exists(rel_path):
                default_storage.delete(rel_path)
            default_storage.save(rel_path, content)
        except OSError:
            logger.exception("pdf_split_ocr_cache_write_failed", extra={"cache_file": rel_path})
            raise
        _cleanup_ocr_cache_history(pdf_hash=pdf_hash, profile_key=profile_key, page_no=result.page_no)


@dataclass(frozen=True)
class _OcrCacheEntry:
    """缓存目录里的一个候选文件（可能是固定名，也可能是 `page_0001_xxx.json` 残档）。"""

    name: str
    result: OCRPageResult
    modified_at: float


def _ocr_cache_entry_key(entry: _OcrCacheEntry) -> tuple[int, int, float]:
    """排序键：先「没失败」，再「文字量最多」，最后「修改时间最新」。

    内容多少是质量信号，时间不是：实测同页不同次识别文字量差 475 倍（32 vs 15217），
    一次偶然的失败识别不该盖住之前成功的结果。
    """
    return (0 if entry.result.ocr_failed else 1, len(entry.result.text), entry.modified_at)


# ↓↓ 由 OCRHandler 下沉的模块级纯函数（四层架构静态方法棘轮）
def _ocr_cache_dir(*, pdf_hash: str, profile_key: str) -> str:
    return f"pdf_splitting/ocr_cache/{pdf_hash}/{profile_key}"


# ↓↓ 由 OCRHandler 下沉的模块级纯函数（四层架构静态方法棘轮）
def _ocr_cache_page_filename(*, page_no: int) -> str:
    return f"page_{page_no:04d}.json"


# ↓↓ 由 OCRHandler 下沉的模块级纯函数（四层架构静态方法棘轮）
def _ocr_cache_rel_path(*, pdf_hash: str, profile_key: str, page_no: int) -> str:
    cache_dir = _ocr_cache_dir(pdf_hash=pdf_hash, profile_key=profile_key)
    return f"{cache_dir}/{_ocr_cache_page_filename(page_no=page_no)}"


# ↓↓ 由 OCRHandler 下沉的模块级纯函数（四层架构静态方法棘轮）
def _is_ocr_cache_page_name(*, name: str, page_no: int) -> bool:
    """文件名是否属于第 page_no 页（固定名或 `page_0001_xxxxxxx.json` 残档）。

    必须用完整前缀比对：`page_0001*` 会把 `page_00010.json` 也匹进来，
    那样第 1 页的清理/读取就会误伤第 10 页。
    """
    prefix = f"page_{page_no:04d}"
    if not name.startswith(prefix):
        return False
    if not name.endswith(".json"):
        return False
    middle = name[len(prefix) : -len(".json")]
    return middle == "" or (middle.startswith("_") and len(middle) > 1)


# ↓↓ 由 OCRHandler 下沉的模块级纯函数（四层架构静态方法棘轮）
def _list_ocr_cache_files(*, cache_dir: str) -> list[str]:
    """缓存目录下的文件名列表；存储后端不支持列目录（或返回异常形状）时返回空。"""
    try:
        listing = default_storage.listdir(cache_dir)
        if not isinstance(listing, (tuple, list)) or len(listing) != 2:
            raise ValueError(f"unexpected listdir result: {listing!r}")
        _, files = listing
        return [str(name) for name in files]
    except (OSError, NotImplementedError, ValueError, TypeError):
        logger.warning("pdf_split_ocr_cache_list_failed", extra={"cache_dir": cache_dir})
        return []


# ↓↓ 由 OCRHandler 下沉的模块级纯函数（四层架构静态方法棘轮）
def _ocr_cache_candidate_names(*, cache_dir: str, page_no: int) -> list[str]:
    """该页在缓存目录里的全部候选文件名（固定名 + 历史残档）。"""
    files = _list_ocr_cache_files(cache_dir=cache_dir)
    names = [name for name in files if _is_ocr_cache_page_name(name=name, page_no=page_no)]
    fixed_name = _ocr_cache_page_filename(page_no=page_no)
    if not names and default_storage.exists(f"{cache_dir}/{fixed_name}"):
        # 列目录不可用的存储后端：只能退回固定名。
        return [fixed_name]
    return names


# ↓↓ 由 OCRHandler 下沉的模块级纯函数（四层架构静态方法棘轮）
def _load_ocr_cache_entry(*, storage: Any, rel_path: str, page_no: int) -> _OcrCacheEntry | None:
    if not storage.exists(rel_path):
        return None
    try:
        with storage.open(rel_path) as f:
            payload = json.loads(f.read().decode("utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.exception("pdf_split_ocr_cache_read_failed", extra={"cache_file": rel_path})
        return None
    text = str(payload.get("text") or "")
    layout = payload.get("layout")
    result = OCRPageResult(
        page_no=page_no,
        text=text,
        source_method=_cached_source_method(str(payload.get("source_method") or ""), text=text),
        ocr_failed=bool(payload.get("ocr_failed")),
        layout=layout if isinstance(layout, dict) else None,
    )
    return _OcrCacheEntry(
        name=rel_path.rsplit("/", 1)[-1],
        result=result,
        modified_at=_ocr_cache_entry_mtime(rel_path=rel_path),
    )


# ↓↓ 由 OCRHandler 下沉的模块级纯函数（四层架构静态方法棘轮）
def _cached_source_method(payload_method: str, *, text: str) -> str:
    """缓存命中时的来源标记：**云端平台必须保留真实的那一个**。

    缓存档案名记的是**首选**平台（``..._mineru_text_v2``），而容灾生效时写进去的
    其实是 TextIn 的结果。命中缓存那一轮不再调云端，无从知道发生过容灾——
    只有条目里的 ``source_method`` 还记着真实来源。丢掉它，下游就会拿 MinerU 的
    千分比去换算 TextIn 的绝对坐标，绿框整体错位。

    本地 OCR / 文本层没有平台可言，沿用 ``ocr_cache`` / ``ocr_failed_cache``。
    """
    backend = cloud_backend_of_method(payload_method)
    if backend:
        return payload_method
    return "ocr_cache" if text else "ocr_failed_cache"


# ↓↓ 由 OCRHandler 下沉的模块级纯函数（四层架构静态方法棘轮）
def _ocr_cache_entry_mtime(*, rel_path: str) -> float:
    """缓存条目的修改时间；存储后端不提供路径时按「最早」处理。"""
    try:
        return default_storage.get_modified_time(rel_path).timestamp()
    except (OSError, NotImplementedError, AttributeError, ValueError):
        return 0.0


# ↓↓ 由 OCRHandler 下沉的模块级纯函数（四层架构静态方法棘轮）
def _promote_ocr_cache_entry(*, pdf_hash: str, profile_key: str, page_no: int, chosen_name: str) -> None:
    """自愈：把选中的残档回写成固定名，下次读取就不必再扫全量候选。"""
    cache_dir = _ocr_cache_dir(pdf_hash=pdf_hash, profile_key=profile_key)
    canonical_name = _ocr_cache_page_filename(page_no=page_no)
    try:
        with default_storage.open(f"{cache_dir}/{chosen_name}") as f:
            raw = f.read()
        canonical_path = f"{cache_dir}/{canonical_name}"
        if default_storage.exists(canonical_path):
            default_storage.delete(canonical_path)
        default_storage.save(canonical_path, ContentFile(raw))
    except OSError:
        logger.exception(
            "pdf_split_ocr_cache_promote_failed",
            extra={"cache_file": f"{cache_dir}/{chosen_name}", "page_no": page_no},
        )


# ↓↓ 由 OCRHandler 下沉的模块级纯函数（四层架构静态方法棘轮）
def _cleanup_ocr_cache_history(*, pdf_hash: str, profile_key: str, page_no: int) -> None:
    """删掉该页的历史残档（`page_0001_xxxxxxx.json`）。失败只记日志，不影响主写入。"""
    cache_dir = _ocr_cache_dir(pdf_hash=pdf_hash, profile_key=profile_key)
    fixed_name = _ocr_cache_page_filename(page_no=page_no)
    for name in _list_ocr_cache_files(cache_dir=cache_dir):
        if name == fixed_name or not _is_ocr_cache_page_name(name=name, page_no=page_no):
            continue
        try:
            default_storage.delete(f"{cache_dir}/{name}")
        except OSError:
            logger.warning(
                "pdf_split_ocr_cache_stale_delete_failed",
                extra={"cache_file": f"{cache_dir}/{name}"},
            )


# ↓↓ 由 OCRHandler 下沉的模块级纯函数（四层架构静态方法棘轮）
def _chunk_pages(*, page_numbers: list[int], chunk_count: int) -> list[list[int]]:
    if not page_numbers:
        return []
    chunk_count = max(1, min(chunk_count, len(page_numbers)))
    buckets: list[list[int]] = [[] for _ in range(chunk_count)]
    for index, page_no in enumerate(page_numbers):
        buckets[index % chunk_count].append(page_no)
    return [bucket for bucket in buckets if bucket]
