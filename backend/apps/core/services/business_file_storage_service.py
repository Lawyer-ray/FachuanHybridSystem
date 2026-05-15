"""Business file storage selection and resolution helpers."""

from __future__ import annotations

import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from apps.core.exceptions import ValidationException

from .storage_service import _DefaultFileValidator, _get_media_root, is_absolute_path, sanitize_upload_filename

CASE_PURPOSES: set[str] = {
    "case_material",
    "log_attachment",
}

CONTRACT_PURPOSES: set[str] = {
    "archive_case_material",
    "archive_upload",
    "contract_attachment",
    "finalized_material",
}


@dataclass(frozen=True)
class StorageTarget:
    """Where a newly uploaded file should be stored."""

    root_type: str
    root_path: str
    subdir_path: str
    relative_dir: str
    is_fallback: bool = False
    reason: str = ""

    @property
    def absolute_dir(self) -> Path:
        base = Path(self.root_path).expanduser().resolve()
        if self.relative_dir:
            return (base / self.relative_dir).resolve()
        return base


@dataclass(frozen=True)
class ResolvedBusinessFile:
    """Resolved file location for read/delete/sync operations."""

    root_type: str
    abs_path: str
    relative_file_path: str
    exists: bool
    root_path: str = ""


@dataclass(frozen=True)
class StoredBusinessFile:
    """Result of storing a file under a business root."""

    root_type: str
    root_path: str
    subdir_path: str
    relative_file_path: str
    legacy_file_path: str
    original_filename: str
    absolute_file_path: str
    is_fallback: bool = False
    reason: str = ""

    def __iter__(self):
        yield self.legacy_file_path
        yield self.original_filename


class BusinessFileStorageService:
    """Choose storage targets and resolve stored file records."""

    def move_existing_file(
        self,
        record: Any,
        *,
        purpose: str,
        case_id: int | None = None,
        contract_id: int | None = None,
        target_subdir: str = "",
        preferred_filename: str | None = None,
    ) -> StoredBusinessFile:
        resolved = self.resolve_file(record)
        if not resolved.abs_path or not resolved.exists:
            raise ValidationException(
                message="Source file does not exist",
                code="SOURCE_FILE_NOT_FOUND",
                errors={"file_path": self._extract_stored_file_path(record)},
            )

        source_path = Path(resolved.abs_path).expanduser().resolve()
        target = self.choose_storage_target(
            purpose=purpose,
            case_id=case_id,
            contract_id=contract_id,
            target_subdir=target_subdir,
        )

        base_dir = target.absolute_dir
        base_dir.mkdir(parents=True, exist_ok=True)

        original_name = preferred_filename or getattr(record, "original_filename", "") or source_path.name
        safe_original_name = sanitize_upload_filename(str(original_name))
        ext = source_path.suffix or Path(safe_original_name).suffix
        filename = safe_original_name
        if not filename:
            filename = f"{uuid.uuid4().hex}{ext if ext and len(ext) <= 16 else ''}"

        target_abs = base_dir / filename
        while target_abs.exists() and target_abs.resolve() != source_path:
            target_abs = base_dir / f"{uuid.uuid4().hex}{ext if ext and len(ext) <= 16 else ''}"

        if target_abs.resolve() != source_path:
            shutil.move(str(source_path), str(target_abs))

        relative_file_path = self._normalize_relative_path(
            str((Path(target.relative_dir) / target_abs.name).as_posix()),
            allow_empty=False,
        )
        legacy_file_path = relative_file_path if target.root_type == "media" else str(target_abs.resolve())
        return StoredBusinessFile(
            root_type=target.root_type,
            root_path=target.root_path,
            subdir_path=target.subdir_path,
            relative_file_path=relative_file_path,
            legacy_file_path=legacy_file_path,
            original_filename=safe_original_name or source_path.name,
            absolute_file_path=str(target_abs.resolve()),
            is_fallback=target.is_fallback,
            reason=target.reason,
        )

    def save_uploaded_file(
        self,
        *,
        uploaded_file: Any,
        purpose: str,
        case_id: int | None = None,
        contract_id: int | None = None,
        target_subdir: str = "",
        preferred_filename: str | None = None,
        use_uuid_name: bool = True,
        max_size_bytes: int | None = None,
        allowed_extensions: list[str] | None = None,
        file_validator: Any | None = None,
    ) -> StoredBusinessFile:
        target = self.choose_storage_target(
            purpose=purpose,
            case_id=case_id,
            contract_id=contract_id,
            target_subdir=target_subdir,
        )
        original_name = str(getattr(uploaded_file, "name", "") or "")
        safe_original_name = sanitize_upload_filename(original_name)

        validator = file_validator if file_validator is not None else _DefaultFileValidator()
        _max_size_bytes = max_size_bytes if max_size_bytes is not None else 20 * 1024 * 1024
        validator.validate_uploaded_file(
            uploaded_file,
            field_name="file",
            max_size_bytes=_max_size_bytes,
            allowed_extensions=allowed_extensions,
        )

        base_dir = target.absolute_dir
        base_dir.mkdir(parents=True, exist_ok=True)

        preferred = preferred_filename or safe_original_name
        preferred = sanitize_upload_filename(preferred)
        preferred_ext = Path(preferred).suffix or Path(safe_original_name).suffix
        ext = preferred_ext if preferred_ext and len(preferred_ext) <= 16 else ""

        if use_uuid_name:
            filename = f"{uuid.uuid4().hex}{ext}"
        else:
            filename = preferred

        target_abs = base_dir / filename
        while target_abs.exists():
            filename = f"{uuid.uuid4().hex}{ext}" if use_uuid_name else f"{uuid.uuid4().hex}_{preferred}"
            target_abs = base_dir / filename

        with open(target_abs, "wb+") as f:
            if hasattr(uploaded_file, "chunks"):
                for chunk in uploaded_file.chunks():
                    f.write(chunk)
            else:
                f.write(uploaded_file.read())

        relative_file_path = self._normalize_relative_path(str((Path(target.relative_dir) / filename).as_posix()), allow_empty=False)
        legacy_file_path = relative_file_path if target.root_type == "media" else str(target_abs.resolve())
        return StoredBusinessFile(
            root_type=target.root_type,
            root_path=target.root_path,
            subdir_path=target.subdir_path,
            relative_file_path=relative_file_path,
            legacy_file_path=legacy_file_path,
            original_filename=safe_original_name,
            absolute_file_path=str(target_abs.resolve()),
            is_fallback=target.is_fallback,
            reason=target.reason,
        )

    def choose_storage_target(
        self,
        *,
        purpose: str,
        case_id: int | None = None,
        contract_id: int | None = None,
        target_subdir: str = "",
    ) -> StorageTarget:
        normalized_subdir = self._normalize_relative_path(target_subdir, allow_empty=True)
        preferred_root = self._infer_root_type(purpose=purpose, case_id=case_id, contract_id=contract_id)

        if preferred_root == "media":
            media_root = self._get_media_root_path()
            relative_dir = self._build_media_relative_dir(
                purpose=purpose,
                contract_id=contract_id,
                requested_subdir=normalized_subdir,
            )
            return StorageTarget(
                root_type="media",
                root_path=str(media_root),
                subdir_path=normalized_subdir,
                relative_dir=relative_dir,
                is_fallback=False,
                reason="media_selected",
            )

        selected_root = self._resolve_root_directory(
            root_type=preferred_root,
            case_id=case_id,
            contract_id=contract_id,
            require_writable=True,
        )
        if selected_root is not None:
            return StorageTarget(
                root_type=preferred_root,
                root_path=str(selected_root),
                subdir_path=normalized_subdir,
                relative_dir=normalized_subdir,
                is_fallback=False,
                reason=f"{preferred_root}_selected",
            )

        media_root = self._get_media_root_path()
        relative_dir = self._build_media_relative_dir(
            purpose=purpose,
            contract_id=contract_id,
            requested_subdir=normalized_subdir,
        )
        return StorageTarget(
            root_type="media",
            root_path=str(media_root),
            subdir_path=normalized_subdir,
            relative_dir=relative_dir,
            is_fallback=True,
            reason=f"{preferred_root}_unavailable_fallback_media",
        )

    def resolve_file(self, record: Any) -> ResolvedBusinessFile:
        root_type = str(getattr(record, "storage_root_type", "") or "").strip() or "media"
        stored_path = self._extract_stored_file_path(record)
        if not stored_path:
            return ResolvedBusinessFile(
                root_type=root_type,
                abs_path="",
                relative_file_path="",
                exists=False,
            )

        if root_type == "media":
            root_path = self._get_media_root_path()
        elif root_type == "case_folder":
            case_id = self._extract_case_id(record)
            root_path = self._resolve_root_directory(
                root_type="case_folder",
                case_id=case_id,
                contract_id=None,
                require_writable=False,
            )
        elif root_type == "contract_folder":
            contract_id = self._extract_contract_id(record)
            root_path = self._resolve_root_directory(
                root_type="contract_folder",
                case_id=None,
                contract_id=contract_id,
                require_writable=False,
            )
        else:
            return ResolvedBusinessFile(
                root_type=root_type,
                abs_path="",
                relative_file_path=stored_path,
                exists=False,
            )

        if root_path is None:
            return ResolvedBusinessFile(
                root_type=root_type,
                abs_path="",
                relative_file_path=stored_path,
                exists=False,
            )

        abs_path, relative_path = self._resolve_path_under_root(root_path, stored_path)
        return ResolvedBusinessFile(
            root_type=root_type,
            abs_path=str(abs_path),
            relative_file_path=relative_path,
            exists=abs_path.exists(),
            root_path=str(root_path),
        )

    def delete_file(self, record_or_path: Any) -> bool:
        if hasattr(record_or_path, "__dict__") and not isinstance(record_or_path, (str, bytes, os.PathLike)):
            resolved = self.resolve_file(record_or_path)
            if not resolved.abs_path:
                return False
            return self._unlink_path(Path(resolved.abs_path))
        return self._unlink_path(self._coerce_file_path(str(record_or_path or "").strip()))

    def _infer_root_type(self, *, purpose: str, case_id: int | None, contract_id: int | None) -> str:
        if purpose in CONTRACT_PURPOSES:
            return "contract_folder"
        if purpose in CASE_PURPOSES:
            return "case_folder"
        if contract_id:
            return "contract_folder"
        if case_id:
            return "case_folder"
        return "media"

    def _resolve_root_directory(
        self,
        *,
        root_type: str,
        case_id: int | None,
        contract_id: int | None,
        require_writable: bool,
    ) -> Path | None:
        if root_type == "case_folder":
            return self._get_case_folder_root(case_id=case_id, require_writable=require_writable)
        if root_type == "contract_folder":
            return self._get_contract_folder_root(contract_id=contract_id, require_writable=require_writable)
        if root_type == "media":
            return self._get_media_root_path()
        return None

    def _get_case_folder_root(self, *, case_id: int | None, require_writable: bool) -> Path | None:
        if not case_id:
            return None

        try:
            from apps.cases.services.template.folder_binding_service import CaseFolderBindingService

            resolved_root = CaseFolderBindingService().get_case_storage_root(owner_id=case_id)
            if resolved_root is not None:
                return self._coerce_accessible_directory(str(resolved_root), require_writable=require_writable)
        except Exception:
            pass

        from apps.cases.models.material import CaseFolderBinding

        binding = CaseFolderBinding.objects.filter(case_id=case_id).first()
        if not binding:
            return None
        resolved = getattr(binding, "resolved_folder_path", "") or getattr(binding, "folder_path", "")
        return self._coerce_accessible_directory(resolved, require_writable=require_writable)

    def _get_contract_folder_root(self, *, contract_id: int | None, require_writable: bool) -> Path | None:
        if not contract_id:
            return None

        try:
            from apps.contracts.services.folder.folder_binding_service import FolderBindingService

            resolved_root = FolderBindingService().get_contract_storage_root(owner_id=contract_id)
            if resolved_root is not None:
                return self._coerce_accessible_directory(str(resolved_root), require_writable=require_writable)
        except Exception:
            pass

        from apps.contracts.models.folder_binding import ContractFolderBinding

        binding = ContractFolderBinding.objects.filter(contract_id=contract_id).first()
        if not binding:
            return None
        resolved = getattr(binding, "folder_path", "")
        return self._coerce_accessible_directory(resolved, require_writable=require_writable)

    def _coerce_accessible_directory(self, folder_path: str, *, require_writable: bool) -> Path | None:
        raw = str(folder_path or "").strip()
        if not raw:
            return None
        try:
            path = Path(raw).expanduser().resolve()
        except Exception:
            return None
        if not path.exists() or not path.is_dir():
            return None
        if require_writable and not os.access(path, os.W_OK):
            return None
        return path

    def _coerce_file_path(self, file_path: str) -> Path | None:
        raw = str(file_path or "").strip()
        if not raw:
            return None
        if is_absolute_path(raw):
            try:
                return Path(raw).expanduser().resolve()
            except Exception:
                return None
        media_root = self._get_media_root_path()
        return (media_root / raw).resolve()

    def _get_media_root_path(self) -> Path:
        media_root = _get_media_root()
        if not media_root:
            raise ValidationException(
                message="MEDIA_ROOT not configured",
                code="MEDIA_ROOT_NOT_CONFIGURED",
                errors={"MEDIA_ROOT": "not configured"},
            )
        return Path(media_root).expanduser().resolve()

    def _build_media_relative_dir(
        self,
        *,
        purpose: str,
        contract_id: int | None,
        requested_subdir: str,
    ) -> str:
        if purpose in {"archive_case_material", "archive_upload", "contract_attachment", "finalized_material"}:
            base = f"contracts/finalized/{contract_id}" if contract_id else "contracts/finalized"
        elif purpose in {"case_material", "log_attachment"}:
            base = "case_logs"
        else:
            base = "uploads"

        if requested_subdir:
            return f"{base}/{requested_subdir}"
        return base

    def _resolve_path_under_root(self, root_path: Path, stored_path: str) -> tuple[Path, str]:
        raw = str(stored_path or "").strip()
        if not raw:
            raise ValidationException(
                message="File path cannot be empty",
                code="INVALID_FILE_PATH",
                errors={"file_path": "empty"},
            )

        root = root_path.expanduser().resolve()
        if is_absolute_path(raw):
            try:
                abs_path = Path(raw).expanduser().resolve()
            except Exception:
                raise ValidationException(
                    message="Invalid file path",
                    code="INVALID_FILE_PATH",
                    errors={"file_path": raw},
                ) from None
            try:
                rel_path = abs_path.relative_to(root)
            except ValueError:
                raise ValidationException(
                    message="File path outside allowed root",
                    code="FILE_PATH_OUTSIDE_ROOT",
                    errors={"file_path": raw},
                ) from None
            return abs_path, str(rel_path).replace("\\", "/")

        relative_path = self._normalize_relative_path(raw, allow_empty=False)
        abs_path = (root / relative_path).resolve()
        try:
            abs_path.relative_to(root)
        except ValueError:
            raise ValidationException(
                message="File path outside allowed root",
                code="FILE_PATH_OUTSIDE_ROOT",
                errors={"file_path": raw},
            ) from None
        return abs_path, relative_path

    def _extract_stored_file_path(self, record: Any) -> str:
        value = str(getattr(record, "relative_file_path", "") or "").strip()
        if value:
            return value

        value = str(getattr(record, "file_path", "") or "").strip()
        if value:
            return value

        file_field = getattr(record, "file", None)
        value = str(getattr(file_field, "name", "") or "").strip()
        if value:
            return value
        return ""

    def _extract_case_id(self, record: Any) -> int | None:
        case_id = getattr(record, "case_id", None)
        if case_id:
            return int(case_id)

        case = getattr(record, "case", None)
        case_id = getattr(case, "id", None)
        if case_id:
            return int(case_id)

        log = getattr(record, "log", None)
        case_id = getattr(log, "case_id", None)
        if case_id:
            return int(case_id)
        return None

    def _extract_contract_id(self, record: Any) -> int | None:
        contract_id = getattr(record, "contract_id", None)
        if contract_id:
            return int(contract_id)

        contract = getattr(record, "contract", None)
        contract_id = getattr(contract, "id", None)
        if contract_id:
            return int(contract_id)
        return None

    def _normalize_relative_path(self, value: str, *, allow_empty: bool) -> str:
        raw = str(value or "").strip().replace("\\", "/")
        if not raw:
            if allow_empty:
                return ""
            self._raise_invalid_relative_path("empty")
        if raw.startswith(("/", "~")) or is_absolute_path(raw):
            self._raise_invalid_relative_path(raw)

        parts = [part for part in raw.split("/") if part not in {"", "."}]
        if not parts and allow_empty:
            return ""
        if not parts:
            self._raise_invalid_relative_path(raw)
        if any(part == ".." for part in parts):
            self._raise_invalid_relative_path(raw)
        if any(part.startswith(".") for part in parts):
            self._raise_invalid_relative_path(raw)
        return "/".join(parts)

    def _unlink_path(self, abs_path: Path | None) -> bool:
        if abs_path is None:
            return False
        try:
            abs_path.unlink(missing_ok=True)
        except Exception:
            return False
        return True

    def _raise_invalid_relative_path(self, raw: str) -> None:
        raise ValidationException(
            message="Relative path is invalid",
            code="INVALID_RELATIVE_PATH",
            errors={"path": raw},
        )
