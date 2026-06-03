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

    def _compute_relative_path(self, owner: Any, folder_path: str) -> str | None:
        """计算案件文件夹相对合同文件夹的相对路径.

        仅案件绑定有效：如果 owner 有合同且合同有文件夹绑定，
        则计算 folder_path 相对合同路径的相对路径。
        其他类型（合同绑定）返回 None。

        Args:
            owner: 绑定所属的 owner 对象
            folder_path: 绑定的文件夹绝对路径

        Returns:
            相对路径字符串或 None
        """
        from pathlib import PurePosixPath

        # 仅对案件 owner 计算 relative_path
        contract = getattr(owner, "contract", None)
        if contract is None:
            return None

        contract_binding = getattr(contract, "folder_binding", None)
        if contract_binding is None or not contract_binding.folder_path:
            return None

        case_path = PurePosixPath(folder_path)
        contract_path = PurePosixPath(contract_binding.folder_path)

        if case_path.is_relative_to(contract_path):
            return str(case_path.relative_to(contract_path))
        return None

    def create_binding(self, *, owner_id: int, folder_path: str, **kwargs: Any) -> Any:
        if self.binding_model is None:
            raise RuntimeError("FolderBindingCrudService.binding_model 未配置")
        if not self.owner_rel_field:
            raise RuntimeError("FolderBindingCrudService.owner_rel_field 未配置")

        owner = self._require_owner(owner_id=owner_id, **kwargs)

        # ── Resolve storage_type and storage_account from kwargs ──
        storage_type = kwargs.pop("storage_type", "local")
        storage_account = kwargs.pop("storage_account", None)

        # Cloud storage paths don't need local path format validation
        if storage_type == "local":
            is_valid, error_msg = self.validate_folder_path(folder_path)
            if not is_valid:
                raise ValidationException(
                    message="文件夹路径格式无效",
                    code="INVALID_PATH_FORMAT",
                    errors={"folder_path": error_msg},
                )

        stripped_path = folder_path.strip()

        # Compute inode info (only for local storage)
        inode_info = None
        if storage_type == "local":
            inode_info = self.inode_resolver.get_inode_info(stripped_path)

        defaults: dict[str, Any] = {"folder_path": stripped_path}
        has_inode_fields = hasattr(self.binding_model, "folder_inode")
        if inode_info is not None and has_inode_fields:
            defaults["folder_inode"] = inode_info[0]
            defaults["folder_device"] = inode_info[1]

        # Set cloud storage fields
        if storage_type != "local":
            defaults["storage_type"] = storage_type
            if storage_account is not None:
                defaults["storage_account"] = storage_account

        # 案件文件夹绑定时计算 relative_path
        relative_path = self._compute_relative_path(owner, stripped_path)
        if relative_path is not None:
            defaults["relative_path"] = relative_path

        binding, created = self.binding_model.objects.update_or_create(
            **{self.owner_rel_field: owner},
            defaults=defaults,
        )

        action = "create_binding" if created else "update_binding"
        logger.info(
            "文件夹绑定成功",
            extra={
                "owner_id": owner_id,
                "folder_path": stripped_path,
                "action": action,
                "owner_label": self.owner_label,
                "inode": inode_info[0] if inode_info else None,
                "device": inode_info[1] if inode_info else None,
                "relative_path": relative_path,
                "storage_type": storage_type,
            },
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
        resolved_path = getattr(binding, "resolved_folder_path", None) or binding.folder_path

        # ── Cloud storage: use provider ──
        if self._is_cloud_storage(binding):
            provider = self._get_provider_for_binding(binding)
            try:
                cloud_path = "/".join([resolved_path.strip("/")] + relative_dir_parts + [safe_name])
                provider.write_file(cloud_path, file_content)
            except Exception as e:
                error_msg = f"文件保存失败（云存储）: {e}"
                logger.error(error_msg, extra={"owner_id": owner_id, "file_name": safe_name})
                raise ValidationException(
                    message="文件保存失败",
                    code="FILE_SAVE_FAILED",
                    errors={"file_operation": error_msg},
                ) from e
            logger.info(
                "文件保存到绑定文件夹成功（云存储）",
                extra={
                    "owner_id": owner_id,
                    "file_name": safe_name,
                    "cloud_path": cloud_path,
                    "subdir_key": subdir_key,
                },
            )
            return cloud_path

        # ── Local filesystem: existing logic ──
        try:
            abs_file_path = self.filesystem_service.save_bytes(
                base_path=resolved_path,
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

        resolved_path = getattr(binding, "resolved_folder_path", None) or binding.folder_path

        # ── Cloud storage: use provider ──
        if self._is_cloud_storage(binding):
            provider = self._get_provider_for_binding(binding)
            try:
                import io
                import zipfile

                with zipfile.ZipFile(io.BytesIO(zip_content)) as zf:
                    for member in zf.infolist():
                        if member.is_dir():
                            provider.mkdir(f"{resolved_path.strip('/')}/{member.filename.rstrip('/')}")
                            continue
                        safe_name = self.path_validator.sanitize_file_name(member.filename.split("/")[-1])
                        # Build path relative to zip root
                        parts = [p for p in member.filename.split("/") if p and p != safe_name]
                        cloud_path = "/".join([resolved_path.strip("/")] + parts + [safe_name])
                        with zf.open(member) as f:
                            provider.write_file(cloud_path, f.read())
            except Exception as e:
                error_msg = f"ZIP解压失败（云存储）: {e}"
                logger.error(error_msg, extra={"owner_id": owner_id})
                raise ValidationException(message=error_msg, code="ZIP_EXTRACT_FAILED") from e
            logger.info("ZIP解压到绑定文件夹成功（云存储）", extra={"owner_id": owner_id, "cloud_path": resolved_path})
            return str(resolved_path)

        # ── Local filesystem: existing logic ──
        try:
            base_path = self.filesystem_service.extract_zip_bytes(resolved_path, zip_content)
        except (OSError, PermissionError, ValidationException) as e:
            error_msg = f"ZIP解压失败: {e}"
            logger.error(error_msg, extra={"owner_id": owner_id})
            raise ValidationException(message=error_msg, code="ZIP_EXTRACT_FAILED") from e

        logger.info("ZIP解压到绑定文件夹成功", extra={"owner_id": owner_id, "extract_path": str(base_path)})
        return str(base_path)
