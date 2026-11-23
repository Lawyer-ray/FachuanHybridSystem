"""按月归档 + ZIP 导出"""

from __future__ import annotations

import base64
import io
import logging
import uuid
import zipfile
from typing import Any

from django.utils import timezone

from apps.core.utils.path import Path

from .reconciler import STATUS_UNMATCHED, DeliveryNote, MonthGroup, ReconcileResult, StatementInfo

logger = logging.getLogger("apps.finance_doc_sorting")


class ExporterService:
    """导出整理好的案件材料为 ZIP"""

    def export_zip(self, reconcile_result: ReconcileResult) -> dict[str, Any]:  # pragma: no cover
        """
        根据比对结果生成 ZIP

        S01-03（2026-11-23 二轮审计）：原实现逐张图片吞掉解码/写入异常后仍返回
        `success: True`，用户下载到缺页 ZIP 而界面显示成功 → 现在汇总跳过的条目：
        部分失败附 `warnings`，一张也没写进去时 `success: False`（与
        ImageRotationService.export_images 口径一致）。

        Returns:
            {"success": True, "zip_url": str[, "warnings": [str]]}，或
            {"success": False, "message": str[, "errors": [str]]}
        """
        skipped: list[str] = []
        try:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                # 1. 按月份文件夹
                for group in reconcile_result.month_groups:
                    skipped.extend(self._write_month_group(zf, group))

                # 2. 未签名文件夹
                if reconcile_result.unsigned_statements:
                    skipped.extend(self._write_unsigned(zf, reconcile_result.unsigned_statements))

                # 3. 收款情况文件夹
                if reconcile_result.receipts:
                    skipped.extend(self._write_category(zf, "收款情况", reconcile_result.receipts))

                # 4. 其他文件
                if reconcile_result.others:
                    skipped.extend(self._write_category(zf, "其他", reconcile_result.others))

                # 5. 未匹配的出库单
                if reconcile_result.unmatched_deliveries:
                    skipped.extend(self._write_unmatched(zf, reconcile_result.unmatched_deliveries))

                written = len(zf.namelist())

            if written == 0:
                logger.warning("ZIP 导出未写入任何文件: skipped=%d", len(skipped))
                if skipped:
                    return {
                        "success": False,
                        "message": f"所有图片写入失败（{len(skipped)} 张），未生成 ZIP",
                        "errors": skipped,
                    }
                return {"success": False, "message": "没有可导出的文件"}

            # 保存到 MEDIA_ROOT
            buf.seek(0)
            filename = _build_filename()
            rel_path = f"evidence_sorting/{filename}"
            from django.core.files.base import ContentFile
            from django.core.files.storage import default_storage

            default_storage.save(rel_path, ContentFile(buf.getvalue()))

            url = f"/media/evidence_sorting/{filename}"
            logger.info("ZIP 导出成功: %s（%d 个文件，跳过 %d 个）", url, written, len(skipped))
            result: dict[str, Any] = {"success": True, "zip_url": url}
            if skipped:
                result["warnings"] = skipped
            return result

        except (OSError, ValueError) as e:
            logger.exception("ZIP 导出失败: %s", e)
            return {"success": False, "message": str(e)}

    def _write_month_group(self, zf: zipfile.ZipFile, group: MonthGroup) -> list[str]:
        """写入某个月份文件夹，返回未能写入的 ZIP 路径。"""
        folder = group.folder_name
        skipped: list[str] = []

        # 写入对账单
        if group.statement and group.statement.image_data:
            st = group.statement
            total_str = ""
            if st.total_amount is not None:
                total_str = f"_{st.total_amount}"
            sign_str = "已签名" if st.signed else "未签名"
            ext = _get_ext(st.filename)
            st_name = f"{group.month}对账单{total_str}({sign_str}){ext}"
            skipped.extend(_write_or_skip(zf, f"{folder}/{st_name}", st.image_data))

        # 写入出库单
        # 按日期排序
        sorted_deliveries = sorted(
            group.deliveries,
            key=lambda d: d.date or "99999999",
        )
        # 同日期计数器
        date_counter: dict[str, int] = {}
        for dn in sorted_deliveries:
            name = self._build_delivery_filename(dn, date_counter)
            skipped.extend(_write_or_skip(zf, f"{folder}/{name}", dn.image_data))

        return skipped

    def _build_delivery_filename(self, dn: DeliveryNote, date_counter: dict[str, int]) -> str:
        date_str = dn.date or "未知日期"
        amount_str = f"_{dn.amount}" if dn.amount else ""
        ext = _get_ext(dn.filename)

        # 同日期序号
        count = date_counter.get(date_str, 0) + 1
        date_counter[date_str] = count
        seq = f"_{count}" if count > 1 else ""

        # 备注
        remark = ""
        if dn.match_status == STATUS_UNMATCHED and dn.remark:
            remark = f"（{dn.remark}）"

        doc_type = "出库单" if "出库" in dn.ocr_text else "出仓单"
        return f"{date_str}_{doc_type}{seq}{amount_str}{remark}{ext}"

    def _write_unsigned(self, zf: zipfile.ZipFile, statements: list[StatementInfo]) -> list[str]:
        """写入「未签名」文件夹，返回未能写入的 ZIP 路径。"""
        folder = "未签名"
        skipped: list[str] = []
        for st in statements:
            if not st.image_data:
                logger.warning("跳过无图片数据的对账单: %s", st.filename)
                continue
            ext = _get_ext(st.filename)
            total_str = ""
            if st.total_amount is not None:
                total_str = f"_{st.total_amount}"
            name = f"{st.month or '未知月份'}对账单{total_str}（未签名）{ext}"
            skipped.extend(_write_or_skip(zf, f"{folder}/{name}", st.image_data))
        return skipped

    def _write_category(self, zf: zipfile.ZipFile, folder: str, items: list[dict[str, Any]]) -> list[str]:
        """写入某个分类文件夹，返回未能写入的 ZIP 路径。"""
        skipped: list[str] = []
        for item in items:
            filename = item.get("filename", "unknown.jpg")
            data = item.get("image_data", "")
            path = f"{folder}/{filename}"
            if not data:
                # 空 image_data 既不写进 ZIP 也没有任何提示（S01-03），按跳过计入
                logger.warning("跳过空图片数据: %s", path)
                skipped.append(path)
                continue
            skipped.extend(_write_or_skip(zf, path, data))
        return skipped

    def _write_unmatched(self, zf: zipfile.ZipFile, deliveries: list[DeliveryNote]) -> list[str]:
        """写入「未匹配出库单」文件夹，返回未能写入的 ZIP 路径。"""
        folder = "未匹配出库单"
        date_counter: dict[str, int] = {}
        skipped: list[str] = []
        for dn in deliveries:
            name = self._build_delivery_filename(dn, date_counter)
            skipped.extend(_write_or_skip(zf, f"{folder}/{name}", dn.image_data))
        return skipped


# ↓↓ 由 ExporterService 下沉的模块级纯函数（四层架构静态方法棘轮）
def _write_image(zf: zipfile.ZipFile, path: str, data: str) -> bool:
    """将 base64 图片数据写入 ZIP，返回是否写入成功。

    S01-03（2026-11-23 二轮审计）：原实现只打一条 warning 吞掉单张失败、返回值
    恒为 None，调用方无从得知丢了哪几张 → 现在由 `_write_or_skip` 汇总成
    `export_zip` 的 `warnings` / `success: False`。
    """
    try:
        raw = data.split(",", 1)[-1] if "," in data else data
        image_bytes = base64.b64decode(raw)
        zf.writestr(path, image_bytes)
    except Exception as e:
        logger.warning("写入 ZIP 失败: %s - %s", path, e)
        return False
    return True


# ↓↓ 由 ExporterService 下沉的模块级纯函数（四层架构静态方法棘轮）
def _write_or_skip(zf: zipfile.ZipFile, path: str, data: str) -> list[str]:
    """写一张图；失败时返回 `[path]`，成功返回空列表，方便调用方 extend 汇总。"""
    return [] if _write_image(zf, path, data) else [path]


# ↓↓ 由 ExporterService 下沉的模块级纯函数（四层架构静态方法棘轮）
def _get_ext(filename: str) -> str:
    if "." in filename:
        return filename[filename.rfind(".") :]
    return ".jpg"


# ↓↓ 由 ExporterService 下沉的模块级纯函数（四层架构静态方法棘轮）
def _ensure_output_dir() -> Path:
    from django.conf import settings

    media_root = getattr(settings, "MEDIA_ROOT", None)
    if not media_root:
        raise RuntimeError("MEDIA_ROOT 未配置")
    output_dir = Path(str(media_root)) / "evidence_sorting"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


# ↓↓ 由 ExporterService 下沉的模块级纯函数（四层架构静态方法棘轮）
def _build_filename() -> str:
    ts = timezone.localtime().strftime("%Y%m%d_%H%M%S")
    uid = uuid.uuid4().hex[:8]
    return f"evidence_sorting_{ts}_{uid}.zip"
