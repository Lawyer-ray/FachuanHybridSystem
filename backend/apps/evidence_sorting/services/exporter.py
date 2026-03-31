"""按月归档 + ZIP 导出"""

from __future__ import annotations

import base64
import io
import logging
import uuid
import zipfile
from datetime import datetime
from typing import Any

from apps.core.utils.path import Path

from .reconciler import STATUS_UNMATCHED, DeliveryNote, MonthGroup, ReconcileResult, StatementInfo

logger = logging.getLogger("apps.evidence_sorting")


class ExporterService:
    """导出整理好的案件材料为 ZIP"""

    def export_zip(self, reconcile_result: ReconcileResult) -> dict[str, Any]:
        """
        根据比对结果生成 ZIP

        Returns:
            {"success": True, "zip_url": str} 或 {"success": False, "message": str}
        """
        try:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                # 1. 按月份文件夹
                for group in reconcile_result.month_groups:
                    self._write_month_group(zf, group)

                # 2. 未签名文件夹
                if reconcile_result.unsigned_statements:
                    self._write_unsigned(zf, reconcile_result.unsigned_statements)

                # 3. 收款情况文件夹
                if reconcile_result.receipts:
                    self._write_category(zf, "收款情况", reconcile_result.receipts)

                # 4. 其他文件
                if reconcile_result.others:
                    self._write_category(zf, "其他", reconcile_result.others)

                # 5. 未匹配的出库单
                if reconcile_result.unmatched_deliveries:
                    self._write_unmatched(zf, reconcile_result.unmatched_deliveries)

            # 保存到 MEDIA_ROOT
            buf.seek(0)
            output_dir = self._ensure_output_dir()
            filename = self._build_filename()
            filepath = output_dir / filename
            filepath.write_bytes(buf.getvalue())

            url = f"/media/evidence_sorting/{filename}"
            logger.info("ZIP 导出成功: %s", url)
            return {"success": True, "zip_url": url}

        except Exception as e:
            logger.error("ZIP 导出失败: %s", e, exc_info=True)
            return {"success": False, "message": str(e)}

    def _write_month_group(self, zf: zipfile.ZipFile, group: MonthGroup) -> None:
        folder = group.folder_name

        # 写入对账单
        if group.statement and group.statement.image_data:
            st = group.statement
            total_str = ""
            if st.total_amount is not None:
                total_str = f"_{st.total_amount}"
            sign_str = "已签名" if st.signed else "未签名"
            ext = self._get_ext(st.filename)
            st_name = f"{group.month}对账单{total_str}({sign_str}){ext}"
            self._write_image(zf, f"{folder}/{st_name}", st.image_data)

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
            self._write_image(zf, f"{folder}/{name}", dn.image_data)

    def _build_delivery_filename(self, dn: DeliveryNote, date_counter: dict[str, int]) -> str:
        date_str = dn.date or "未知日期"
        amount_str = f"_{dn.amount}" if dn.amount else ""
        ext = self._get_ext(dn.filename)

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

    def _write_unsigned(self, zf: zipfile.ZipFile, statements: list[StatementInfo]) -> None:
        folder = "未签名"
        for st in statements:
            if not st.image_data:
                continue
            ext = self._get_ext(st.filename)
            total_str = ""
            if st.total_amount is not None:
                total_str = f"_{st.total_amount}"
            name = f"{st.month or '未知月份'}对账单{total_str}（未签名）{ext}"
            self._write_image(zf, f"{folder}/{name}", st.image_data)

    def _write_category(self, zf: zipfile.ZipFile, folder: str, items: list[dict[str, Any]]) -> None:
        for item in items:
            filename = item.get("filename", "unknown.jpg")
            data = item.get("image_data", "")
            if data:
                self._write_image(zf, f"{folder}/{filename}", data)

    def _write_unmatched(self, zf: zipfile.ZipFile, deliveries: list[DeliveryNote]) -> None:
        folder = "未匹配出库单"
        date_counter: dict[str, int] = {}
        for dn in deliveries:
            name = self._build_delivery_filename(dn, date_counter)
            self._write_image(zf, f"{folder}/{name}", dn.image_data)

    @staticmethod
    def _write_image(zf: zipfile.ZipFile, path: str, data: str) -> None:
        """将 base64 图片数据写入 ZIP"""
        try:
            raw = data.split(",", 1)[-1] if "," in data else data
            image_bytes = base64.b64decode(raw)
            zf.writestr(path, image_bytes)
        except Exception as e:
            logger.warning("写入 ZIP 失败: %s - %s", path, e)

    @staticmethod
    def _get_ext(filename: str) -> str:
        if "." in filename:
            return filename[filename.rfind(".") :]
        return ".jpg"

    @staticmethod
    def _ensure_output_dir() -> Path:
        from django.conf import settings

        media_root = getattr(settings, "MEDIA_ROOT", None)
        if not media_root:
            raise RuntimeError("MEDIA_ROOT 未配置")
        output_dir = Path(str(media_root)) / "evidence_sorting"
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    @staticmethod
    def _build_filename() -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        uid = uuid.uuid4().hex[:8]
        return f"evidence_sorting_{ts}_{uid}.zip"
