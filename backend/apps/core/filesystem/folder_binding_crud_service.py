"""Business logic services."""

from __future__ import annotations

import logging
from typing import Any

from apps.core.exceptions import NotFoundError, ValidationException

from .folder_binding_base import BaseFolderBindingService

logger = logging.getLogger("apps.core.filesystem")


class FolderBindingCrudService(BaseFolderBindingService):
    binding_model: Any | None = None
    owner_model: Any | None = None
    owner_rel_field: str = ""
    owner_id_field: str = ""
    owner_label: str = "资源"

    def _get_owner(self, *, owner_id: int) -> Any:
        if self.owner_model is None:
            raise RuntimeError("FolderBindingCrudService.owner_model 未配置")
        owner = self.owner_model.objects.filter(id=owner_id).first()
        if owner is None:
            raise NotFoundError(
                message=f"{self.owner_label}不存在",
                code="OWNER_NOT_FOUND",
                errors={"id": f"ID 为 {owner_id} 的{self.owner_label}不存在"},
            )
        return owner

    def _require_owner(self, *, owner_id: int, **kwargs: Any) -> Any:
        return self._get_owner(owner_id=owner_id)

    def _get_owner_type(self, owner: Any) -> str:
        return str(getattr(owner, "case_type", "") or "").strip()

    def _resolve_subdir_path(self, *, owner_type: str, subdir_key: str) -> str | None:
        return None

    def create_binding(self, *, owner_id: int, folder_path: str, **kwargs: Any) -> Any:
        if self.binding_model is None:
            raise RuntimeError("FolderBindingCrudService.binding_model 未配置")
        if not self.owner_rel_field:
            raise RuntimeError("FolderBindingCrudService.owner_rel_field 未配置")

        owner = self._require_owner(owner_id=owner_id, **kwargs)

        is_valid, error_msg = self.validate_folder_path(folder_path)
        if not is_valid:
            raise ValidationException(
                message="文件夹路径格式无效",
                code="INVALID_PATH_FORMAT",
                errors={"folder_path": error_msg},
            )

        binding, created = self.binding_model.objects.update_or_create(
            **{self.owner_rel_field: owner},
            defaults={"folder_path": folder_path.strip()},
        )

        action = "create_binding" if created else "update_binding"
        logger.info(
            "文件夹绑定成功",
            extra={"owner_id": owner_id, "folder_path": folder_path, "action": action, "owner_label": self.owner_label},
        )
        return binding

    def update_binding(self, *, owner_id: int, folder_path: str, **kwargs: Any) -> Any:
        return self.create_binding(owner_id=owner_id, folder_path=folder_path, **kwargs)

    def delete_binding(self, *, owner_id: int, **kwargs: Any) -> bool:
        if self.binding_model is None:
            raise RuntimeError("FolderBindingCrudService.binding_model 未配置")
        if not self.owner_id_field:
            raise RuntimeError("FolderBindingCrudService.owner_id_field 未配置")

        self._require_owner(owner_id=owner_id, **kwargs)
        deleted_count, _ = self.binding_model.objects.filter(**{self.owner_id_field: owner_id}).delete()
        return bool(deleted_count > 0)

    def get_binding(self, *, owner_id: int, **kwargs: Any) -> Any | None:
        if self.binding_model is None:
            raise RuntimeError("FolderBindingCrudService.binding_model 未配置")
        if not self.owner_id_field:
            raise RuntimeError("FolderBindingCrudService.owner_id_field 未配置")

        self._require_owner(owner_id=owner_id, **kwargs)
        return self.binding_model.objects.filter(**{self.owner_id_field: owner_id}).first()

    def save_file_to_bound_folder(
        self,
        *,
        owner_id: int,
        file_content: bytes,
        file_name: str,
        subdir_key: str,
        **kwargs: Any,
    ) -> str | None:
        binding = self.get_binding(owner_id=owner_id, **kwargs)
        if not binding:
            return None

        owner = self._get_owner(owner_id=owner_id)
        owner_type = self._get_owner_type(owner)
        subdir_path = self._resolve_subdir_path(owner_type=owner_type, subdir_key=subdir_key)
        if not subdir_path:
            subdir_path = self.DEFAULT_SUBDIRS.get(subdir_key, "其他文件")

        safe_name = self.path_validator.sanitize_file_name(file_name)
        relative_dir_parts = self.path_validator.sanitize_relative_dir(subdir_path)

        try:
            abs_file_path = self.filesystem_service.save_bytes(
                base_path=binding.folder_path,
                relative_dir_parts=relative_dir_parts,
                file_name=safe_name,
                content=file_content,
            )
        except (OSError, PermissionError) as e:
            error_msg = f"文件保存失败: {e}"
            logger.error(error_msg, extra={"owner_id": owner_id, "file_name": safe_name})
            raise ValidationException(
                message="文件保存失败",
                code="FILE_SAVE_FAILED",
                errors={"file_operation": error_msg},
            ) from e

        logger.info(
            "文件保存到绑定文件夹成功",
            extra={
                "owner_id": owner_id,
                "file_name": safe_name,
                "file_path": str(abs_file_path),
                "subdir_key": subdir_key,
            },
        )
        return str(abs_file_path)

    def extract_zip_to_bound_folder(self, *, owner_id: int, zip_content: bytes, **kwargs: Any) -> str | None:
        binding = self.get_binding(owner_id=owner_id, **kwargs)
        if not binding:
            return None

        try:
            base_path = self.filesystem_service.extract_zip_bytes(binding.folder_path, zip_content)
        except (OSError, PermissionError, ValidationException) as e:
            error_msg = f"ZIP解压失败: {e}"
            logger.error(error_msg, extra={"owner_id": owner_id})
            raise ValidationException(message=error_msg, code="ZIP_EXTRACT_FAILED") from e

        logger.info("ZIP解压到绑定文件夹成功", extra={"owner_id": owner_id, "extract_path": str(base_path)})
        return str(base_path)
