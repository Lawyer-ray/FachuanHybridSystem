from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from apps.batch_printing.models import BatchPrintFileType, BatchPrintItem
from apps.batch_printing.services.storage import BatchPrintStorage
from apps.core.exceptions import ValidationException
from apps.core.services.libreoffice import find_libreoffice
from apps.core.services.storage_service import to_media_abs

logger = logging.getLogger("apps.batch_printing")


class FilePrepareService:
    def get_capability_snapshot(self) -> dict[str, Any]:
        soffice_path = find_libreoffice()
        return {
            "docx_supported": bool(soffice_path),
            "docx_converter": soffice_path or "",
        }

    def prepare_for_print(self, *, item: BatchPrintItem, storage: BatchPrintStorage) -> Path:  # pragma: no cover
        source_abs = to_media_abs(item.source_relpath)
        if not source_abs.exists():
            raise ValidationException(message="源文件不存在", errors={"item_id": item.id})

        source_stem = Path(item.source_original_name).stem or f"file_{item.order}"
        target_pdf = storage.prepared_pdf_path(order=item.order, filename_stem=source_stem)

        if item.file_type == BatchPrintFileType.PDF:
            storage.save_prepared(target_pdf, source_abs.read_bytes())
            return target_pdf

        if item.file_type == BatchPrintFileType.DOCX:
            return self._convert_docx_to_pdf(source_abs=source_abs, target_pdf=target_pdf, storage=storage)

        raise ValidationException(message="不支持的文件类型", errors={"file_type": item.file_type})

    def _convert_docx_to_pdf(
        self, *, source_abs: Path, target_pdf: Path, storage: BatchPrintStorage
    ) -> Path:  # pragma: no cover
        soffice_path = find_libreoffice()
        if not soffice_path:
            raise ValidationException(
                message="当前机器未安装 DOCX 转换器",
                errors={"docx": "请安装 LibreOffice（soffice）后再启用 DOCX 打印"},
            )

        # soffice 工作输出属系统临时目录（非业务产物），最终 PDF 经 default_storage 落盘
        with tempfile.TemporaryDirectory(prefix="batch_print_soffice_") as tmp_dir:
            command = [
                soffice_path,
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                tmp_dir,
                str(source_abs),
            ]
            result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=120)
            if result.returncode != 0:
                raise ValidationException(
                    message="DOCX 转 PDF 失败",
                    errors={"stderr": (result.stderr or "").strip()[:500]},
                )

            converted_path = Path(tmp_dir) / source_abs.with_suffix(".pdf").name
            if not converted_path.exists():
                raise ValidationException(message="DOCX 转换未生成 PDF", errors={"file": source_abs.name})

            storage.save_prepared(target_pdf, converted_path.read_bytes())
        return target_pdf
