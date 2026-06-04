"""邮件往来文件夹扫描导入服务."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction

from apps.cases.models import CaseFolderBinding, CaseLog, CaseLogAttachment
from apps.cases.utils import CASE_LOG_ALLOWED_EXTENSIONS, CASE_LOG_MAX_FILE_SIZE
from apps.core.exceptions import NotFoundError, ValidationException

from .case_log_mutation_service import CaseLogMutationService
from .case_log_query_service import CaseLogQueryService

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser

    from apps.core.cloud_storage.protocols import CloudStorageProvider

logger = logging.getLogger("apps.cases")

_DATE_PATTERN = re.compile(r"^(\d{4})[.\-](\d{1,2})[.\-](\d{1,2})")


class EmailFolderScanService:
    """扫描案件绑定文件夹下子文件夹，将每个子目录的内容分别导入为独立日志+附件."""

    def __init__(
        self,
        mutation_service: CaseLogMutationService | None = None,
        query_service: CaseLogQueryService | None = None,
    ) -> None:
        self._mutation_service = mutation_service
        self._query_service = query_service

    @property
    def mutation_service(self) -> CaseLogMutationService:
        if self._mutation_service is None:
            self._mutation_service = CaseLogMutationService(query_service=self.query_service)
        return self._mutation_service

    @property
    def query_service(self) -> CaseLogQueryService:
        if self._query_service is None:
            self._query_service = CaseLogQueryService()
        return self._query_service

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def import_email_folder(
        self,
        *,
        case_id: int,
        subfolder: str,
        user: Any | None = None,
        org_access: dict[str, Any] | None = None,
        perm_open_access: bool = False,
    ) -> dict[str, Any]:
        """将指定子文件夹下每个子目录分别导入为独立案件日志 + 附件."""
        case_root, provider = self._get_bound_case_root(case_id)
        if case_root is None:
            raise NotFoundError("案件未绑定可用文件夹")

        is_cloud = provider is not None
        target = self._resolve_subfolder(case_root, subfolder, provider=provider)

        # 检查目标是否存在
        if is_cloud:
            assert provider is not None
            if not provider.exists(str(target)):
                raise ValidationException("指定文件夹不存在", errors={"subfolder": "文件夹路径无效"})
        else:
            if not target.exists() or not target.is_dir():  # type: ignore[union-attr]
                raise ValidationException("指定文件夹不存在", errors={"subfolder": "文件夹路径无效"})

        # 收集子目录
        subdirs = self._collect_subdirs(target, provider=provider)
        if not subdirs:
            files = self._collect_allowed_files(target, provider=provider)
            if not files:
                raise ValidationException("文件夹内没有可导入的文件", errors={"subfolder": "无合规文件"})
            subdirs = [(target, files)]

        existing_sources: set[str] = set(
            CaseLog.objects.filter(case_id=case_id)
            .exclude(source_subfolder="")
            .values_list("source_subfolder", flat=True)
        )

        created_logs: list[CaseLog] = []
        skipped_count = 0

        with transaction.atomic():
            for subdir, files in subdirs:
                subdir_name = subdir.name if isinstance(subdir, Path) else PurePosixPath(subdir).name
                source_key = f"{subfolder}/{subdir_name}"
                if source_key in existing_sources:
                    skipped_count += 1
                    logger.info("案件 %d 跳过已导入子目录: %s", case_id, source_key)
                    continue

                content = self._build_log_content(subdir_name)

                log = self.mutation_service.create_log(
                    case_id=case_id,
                    content=content,
                    user=user,
                    org_access=org_access,
                    perm_open_access=perm_open_access,
                )

                log.source_subfolder = source_key
                log.save(update_fields=["source_subfolder"])

                date_match = _DATE_PATTERN.match(subdir_name)
                if date_match:
                    try:
                        year, month, day = int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3))
                        log.created_at = datetime(year, month, day, 12, 0, 0)
                        log.save(update_fields=["created_at"])
                    except ValueError:
                        pass

                for file_path in files:
                    self._upload_file_as_attachment(log, file_path, provider=provider)

                created_logs.append(log)
                existing_sources.add(source_key)

        logger.info(
            "案件 %d 子文件夹导入完成: 新增=%d, 跳过=%d",
            case_id,
            len(created_logs),
            skipped_count,
        )
        return {"logs": created_logs, "skipped_count": skipped_count}

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _get_bound_case_root(self, case_id: int) -> tuple[Path | str | None, CloudStorageProvider | None]:
        """获取案件绑定的文件夹根路径和可选的云存储 provider."""
        binding = CaseFolderBinding.objects.filter(case_id=case_id).first()
        if not binding or not binding.resolved_folder_path:
            return None, None

        storage_type = getattr(binding, "storage_type", "local")
        if storage_type != "local" and getattr(binding, "storage_account", None) is not None:
            from apps.core.cloud_storage.factory import create_provider_for_binding

            provider = create_provider_for_binding(binding)
            return binding.resolved_folder_path, provider

        root = Path(binding.resolved_folder_path).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            logger.warning("案件 %d 绑定目录不可访问: %s", case_id, root)
            return None, None
        return root, None

    def _resolve_subfolder(self, case_root: Path | str, subfolder: str, provider: Any = None) -> Path | str:
        """将相对子文件夹路径解析为完整路径，并校验安全性."""
        raw = str(subfolder or "").strip().replace("\\", "/")
        if not raw:
            raise ValidationException("子文件夹路径不能为空", errors={"subfolder": raw})

        if raw.startswith("/") or raw.startswith("~"):
            raise ValidationException("子文件夹必须使用相对路径", errors={"subfolder": raw})

        parts = [p for p in raw.split("/") if p not in {"", "."}]
        if not parts:
            raise ValidationException("子文件夹路径不能为空", errors={"subfolder": raw})
        if any(p == ".." for p in parts):
            raise ValidationException("子文件夹路径非法", errors={"subfolder": raw})
        if any(p.startswith(".") for p in parts):
            raise ValidationException("子文件夹路径非法", errors={"subfolder": raw})

        joined = "/".join(parts)

        if provider is not None:
            root_str = str(case_root).rstrip("/")
            return f"{root_str}/{joined}"

        assert isinstance(case_root, Path)
        target = (case_root / joined).resolve()
        if not target.is_relative_to(case_root):
            raise ValidationException(
                "文件夹路径不在案件绑定目录内",
                errors={"subfolder": "路径不在允许范围内"},
            )
        return target

    def _collect_subdirs(self, folder_path: Path | str, provider: Any = None) -> list[tuple[Any, list[Any]]]:
        """收集文件夹下所有含合规文件的子目录."""
        if provider is not None:
            return self._collect_subdirs_cloud(str(folder_path), provider)

        assert isinstance(folder_path, Path)
        result: list[tuple[Path, list[Path]]] = []
        for child in sorted(folder_path.iterdir()):
            if not child.is_dir():
                continue
            if child.name.startswith("."):
                continue
            files = self._collect_allowed_files(child)
            if files:
                result.append((child, files))
        return result

    def _collect_subdirs_cloud(self, folder_path: str, provider: Any) -> list[tuple[str, list[str]]]:
        """云存储版本：收集子目录."""
        from apps.core.cloud_storage.exceptions import CloudStorageError

        result: list[tuple[str, list[str]]] = []
        try:
            children = provider.list_directory(folder_path)
        except CloudStorageError:
            raise
        except Exception:
            return []

        for child in sorted(children, key=lambda c: c.name.lower()):
            if not child.is_dir:
                continue
            if child.name.startswith("."):
                continue
            child_path = f"{folder_path.rstrip('/')}/{child.name}"
            files = self._collect_allowed_files(child_path, provider=provider)
            if files:
                result.append((child_path, files))
        return result

    def _collect_allowed_files(self, folder_path: Path | str, provider: Any = None) -> list[Any]:
        """递归收集文件夹内所有合规文件."""
        if provider is not None:
            return self._collect_allowed_files_cloud(str(folder_path), provider)

        assert isinstance(folder_path, Path)
        result: list[Path] = []
        for f in sorted(folder_path.rglob("*")):
            if not f.is_file():
                continue
            try:
                rel_parts = f.relative_to(folder_path).parts
            except ValueError:
                continue
            if any(part.startswith(".") for part in rel_parts):
                continue
            if f.suffix.lower() not in CASE_LOG_ALLOWED_EXTENSIONS:
                continue
            try:
                if CASE_LOG_MAX_FILE_SIZE > 0 and f.stat().st_size > CASE_LOG_MAX_FILE_SIZE:
                    logger.warning("文件超过大小限制，跳过: %s", f.name)
                    continue
            except OSError:
                logger.warning("文件无法访问，跳过: %s", f.name)
                continue
            result.append(f)
        return result

    def _collect_allowed_files_cloud(self, folder_path: str, provider: Any) -> list[str]:
        """云存储版本：递归收集合规文件."""
        from apps.core.cloud_storage.exceptions import CloudStorageError

        result: list[str] = []
        try:
            for _dirpath, _subdirs, files in provider.walk(folder_path):
                for f in files:
                    if f.is_dir:
                        continue
                    # 构建完整路径（兼容 WebDAV 和 OneDrive 的不同 path 格式）
                    file_path = f"{folder_path.rstrip('/')}/{f.name}"
                    rel = PurePosixPath(file_path)
                    if any(part.startswith(".") for part in rel.parts):
                        continue
                    if PurePosixPath(f.name).suffix.lower() not in CASE_LOG_ALLOWED_EXTENSIONS:
                        continue
                    if CASE_LOG_MAX_FILE_SIZE > 0 and f.size > CASE_LOG_MAX_FILE_SIZE:
                        logger.warning("文件超过大小限制，跳过: %s", f.name)
                        continue
                    result.append(file_path)
        except CloudStorageError:
            raise
        except Exception:
            logger.exception("云存储文件收集失败: %s", folder_path)
        return sorted(result)

    def _build_log_content(self, subdir_name: str) -> str:
        """构建日志内容，只保留文件夹名中日期之后的描述部分."""
        content = re.sub(r"^\d{4}[.\-]\d{1,2}[.\-]\d{1,2}[\-\s]*", "", subdir_name)
        return content if content else subdir_name

    def _upload_file_as_attachment(
        self, log: CaseLog, file_path: Path | str, provider: Any = None
    ) -> CaseLogAttachment | None:
        """上传文件为日志附件（本地或云存储）."""
        try:
            if provider is not None:
                file_content = provider.read_file(str(file_path))
                file_name = PurePosixPath(str(file_path)).name
            else:
                assert isinstance(file_path, Path)
                with open(file_path, "rb") as f:
                    file_content = f.read()
                file_name = file_path.name

            uploaded_file = SimpleUploadedFile(name=file_name, content=file_content)
            attachment = CaseLogAttachment.objects.create(log=log, file=uploaded_file)
            logger.info("附件上传成功: %s -> 日志 %d", file_name, log.id)
            return attachment
        except Exception:
            logger.exception("附件上传失败: %s", file_path)
            return None
