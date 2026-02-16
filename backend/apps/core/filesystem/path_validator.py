"""Module for path validator."""

import re
from typing import Any

from apps.core.exceptions import ValidationException
from apps.core.path import Path


class FolderPathValidator:
    def is_network_path(self, path: str) -> bool:
        value = (path or "").strip()
        return value.lower().startswith("smb://") or value.startswith("\\\\")

    def validate_folder_path(self, path: str) -> tuple[bool, str | None]:
        if not path or not path.strip():
            return False, "请输入文件夹路径"

        value = path.strip()

        if value.startswith("/"):
            if re.search(r'[<>:"|?*]', value):
                return False, "路径包含非法字符"
            return True, None

        if re.match(r"^[A-Za-z]:[\\/]", value):
            rest = value[2:]
            if ":" in rest:
                return False, "路径包含非法字符"
            if re.search(r'[<>"|?*]', rest):
                return False, "路径包含非法字符"
            return True, None

        if value.lower().startswith("smb://") or value.startswith("\\\\"):
            return True, None

        return False, "请输入有效的文件夹路径"

    def sanitize_file_name(self, file_name: str) -> str:
        raw = "" if file_name is None else str(file_name)
        if not raw or not raw.strip():
            raise ValidationException(
                message="文件名不能为空", code="INVALID_FILE_NAME", errors={"file_name": "文件名不能为空"}
            )

        name = raw
        if "/" in name or "\\" in name:
            raise ValidationException(
                message="文件名包含非法路径分隔符",
                code="INVALID_FILE_NAME",
                errors={"file_name": "文件名不能包含路径分隔符"},
            )

        base = Path(name).name
        if not str(base).strip() or base in {".", ".."}:
            raise ValidationException(
                message="文件名无效", code="INVALID_FILE_NAME", errors={"file_name": "文件名无效"}
            )

        return str(base)

    def sanitize_relative_dir(self, dir_path: str) -> list[str]:
        if not dir_path or not str(dir_path).strip():
            raise ValidationException(
                message="子目录路径无效", code="INVALID_SUBDIR", errors={"subdir": "子目录路径不能为空"}
            )

        raw = str(dir_path).strip().replace("\\", "/")
        if raw.startswith("/"):
            raise ValidationException(
                message="子目录路径必须为相对路径", code="INVALID_SUBDIR", errors={"subdir": "子目录路径必须为相对路径"}
            )
        if re.match(r"^[A-Za-z]:[\\/]", raw):
            raise ValidationException(
                message="子目录路径必须为相对路径", code="INVALID_SUBDIR", errors={"subdir": "子目录路径必须为相对路径"}
            )

        parts = [p for p in raw.split("/") if p not in {"", "."}]
        if not parts or any(part == ".." for part in parts):
            raise ValidationException(
                message="子目录路径包含非法片段", code="INVALID_SUBDIR", errors={"subdir": "子目录路径不能包含 .."}
            )

        return parts

    def normalize_relative_path(self, relative_path: str) -> str:
        if relative_path is None:
            raise ValidationException(
                message="相对路径不能为空", code="INVALID_RELATIVE_PATH", errors={"relative_path": relative_path}
            )

        raw = str(relative_path).strip().replace("\\", "/")
        if raw.startswith("/") or raw.startswith("~"):
            raise ValidationException(
                message="禁止使用绝对路径", code="INVALID_RELATIVE_PATH", errors={"relative_path": relative_path}
            )
        if re.match(r"^[A-Za-z]:[\\/]", raw):
            raise ValidationException(
                message="禁止使用绝对路径", code="INVALID_RELATIVE_PATH", errors={"relative_path": relative_path}
            )

        parts = [p for p in raw.split("/") if p not in {"", "."}]
        if any(p == ".." for p in parts):
            raise ValidationException(
                message="路径包含非法跳转", code="INVALID_RELATIVE_PATH", errors={"relative_path": relative_path}
            )

        for p in parts:
            if re.search(r'[<>:"|?*]', p):
                raise ValidationException(
                    message="路径包含非法字符", code="INVALID_RELATIVE_PATH", errors={"relative_path": relative_path}
                )

        return "/".join(parts)

    def sanitize_zip_member_path(self, member_name: str) -> list[str]:
        if not member_name:
            raise ValidationException(message="压缩包条目无效", code="INVALID_ZIP_ENTRY", errors={"entry": "空条目"})

        name = member_name.replace("\\", "/")
        while name.startswith("/"):
            name = name[1:]

        if not name or name in {".", ".."}:
            raise ValidationException(message="压缩包条目无效", code="INVALID_ZIP_ENTRY", errors={"entry": member_name})

        if ":" in name.split("/", 1)[0]:
            raise ValidationException(
                message="压缩包条目包含非法路径", code="INVALID_ZIP_ENTRY", errors={"entry": member_name}
            )

        parts = [p for p in name.split("/") if p not in {"", "."}]
        if not parts or any(p == ".." for p in parts):
            raise ValidationException(
                message="压缩包条目包含非法片段", code="INVALID_ZIP_ENTRY", errors={"entry": member_name}
            )

        return parts

    def ensure_within_base(self, base_dir: Path, target_path: Path) -> None:
        base_abs = str(Path(str(base_dir))).rstrip("/\\")
        target_abs = str(Path(str(target_path)))
        if target_abs == base_abs:
            return
        if not target_abs.startswith(base_abs + "/") and not target_abs.startswith(base_abs + "\\"):
            raise ValidationException(message="路径越界", code="PATH_TRAVERSAL", errors={"path": str(target_path)})

    def mkdirs(self, path_obj: Any) -> None:
        if hasattr(path_obj, "makedirs_p"):
            path_obj.makedirs_p()
            return
        if hasattr(path_obj, "mkdir"):
            try:
                path_obj.mkdir(parents=True, exist_ok=True)
            except TypeError:
                path_obj.mkdir()
            return
        raise ValidationException(message="无法创建目录", code="MKDIR_FAILED", errors={"path": str(path_obj)})
