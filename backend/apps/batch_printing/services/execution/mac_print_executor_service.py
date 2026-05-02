from __future__ import annotations

import re
import subprocess
from pathlib import Path

from apps.core.exceptions import ValidationException


class MacPrintExecutorService:
    def print_pdf(self, *, printer_name: str, options: dict[str, str], pdf_path: Path) -> str:
        if not pdf_path.exists():
            raise ValidationException(message="待打印文件不存在", errors={"pdf": str(pdf_path)})
        if not printer_name.strip():
            raise ValidationException(message="未指定打印机", errors={"printer": "请选择打印机"})

        command: list[str] = ["lp", "-d", printer_name]
        for key, value in options.items():
            if not key or value is None:
                continue
            text = str(value).strip()
            if text == "":
                continue
            command.extend(["-o", f"{key}={text}"])

        command.append(str(pdf_path))
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise ValidationException(
                message="静默打印失败",
                errors={"stderr": (result.stderr or "").strip()[:500], "stdout": (result.stdout or "").strip()[:200]},
            )

        output = (result.stdout or "").strip()
        # 常见格式: request id is Canonprinter-123 (1 file(s))
        match = re.search(r"request id is\s+([^\s]+)", output)
        if match:
            return match.group(1)
        return output[:64] or "submitted"
