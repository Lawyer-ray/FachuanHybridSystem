from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

from django.conf import settings

from apps.batch_printing.models import BatchPrintFileType, BatchPrintItem
from apps.batch_printing.services.storage import BatchPrintStorage
from apps.core.exceptions import ValidationException

logger = logging.getLogger("apps.batch_printing")


class FilePrepareService:
    def get_capability_snapshot(self) -> dict[str, Any]:
        soffice_path = self._resolve_soffice_path()
        return {
            "docx_supported": bool(soffice_path),
            "docx_converter": soffice_path or "",
        }

    def prepare_for_print(self, *, item: BatchPrintItem, storage: BatchPrintStorage) -> Path:
        source_abs = Path(settings.MEDIA_ROOT) / item.source_relpath
        if not source_abs.exists():
            raise ValidationException(message="源文件不存在", errors={"item_id": item.id})

        source_stem = Path(item.source_original_name).stem or f"file_{item.order}"
        target_pdf = storage.prepared_pdf_path(order=item.order, filename_stem=source_stem)
        target_pdf.parent.mkdir(parents=True, exist_ok=True)

        if item.file_type == BatchPrintFileType.PDF:
            shutil.copyfile(source_abs, target_pdf)
            return target_pdf

        if item.file_type == BatchPrintFileType.DOCX:
            return self._convert_docx_to_pdf(source_abs=source_abs, target_pdf=target_pdf)

        raise ValidationException(message="不支持的文件类型", errors={"file_type": item.file_type})

    def _resolve_soffice_path(self) -> str:
        for cmd in ("soffice", "libreoffice"):
            path = shutil.which(cmd)
            if path:
                return path

        for candidate in self._candidate_soffice_paths():
            if candidate.is_file():
                return str(candidate)
        return ""

    def _candidate_soffice_paths(self) -> tuple[Path, ...]:
        home = Path.home()
        return (
            Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"),
            Path("/Applications/LibreOffice.app/Contents/program/soffice"),
            home / "Applications" / "LibreOffice.app" / "Contents" / "MacOS" / "soffice",
            home / "Applications" / "LibreOffice.app" / "Contents" / "program" / "soffice",
        )

    def _convert_docx_to_pdf(self, *, source_abs: Path, target_pdf: Path) -> Path:
        soffice_path = self._resolve_soffice_path()
        if not soffice_path:
            raise ValidationException(
                message="当前机器未安装 DOCX 转换器",
                errors={"docx": "请安装 LibreOffice（soffice）后再启用 DOCX 打印"},
            )

        out_dir = target_pdf.parent
        command = [
            soffice_path,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(out_dir),
            str(source_abs),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise ValidationException(
                message="DOCX 转 PDF 失败",
                errors={"stderr": (result.stderr or "").strip()[:500]},
            )

        converted_name = source_abs.with_suffix(".pdf").name
        converted_path = out_dir / converted_name
        if not converted_path.exists():
            raise ValidationException(message="DOCX 转换未生成 PDF", errors={"file": source_abs.name})

        if converted_path != target_pdf:
            if target_pdf.exists():
                target_pdf.unlink()
            converted_path.rename(target_pdf)
        return target_pdf
