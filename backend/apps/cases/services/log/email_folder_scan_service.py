"""邮件往来文件夹扫描导入服务."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.cases.models import CaseFolderBinding, CaseLog, CaseLogAttachment
from apps.cases.utils import CASE_LOG_ALLOWED_EXTENSIONS, CASE_LOG_MAX_FILE_SIZE
from apps.core.exceptions import NotFoundError, ValidationException

from .case_log_mutation_service import CaseLogMutationService
from .case_log_query_service import CaseLogQueryService

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser

logger = logging.getLogger("apps.cases")

# 子文件夹名中的日期提取模式，如 "2026.04.16-收到判决书" → (2026, 4, 16)
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
        """将指定子文件夹下每个子目录分别导入为独立案件日志 + 附件.

        目录结构示例:
          4-邮件往来/
            2026.04.16-收到判决书/
              判决书.pdf
            2026.03.12-收到移送检察院通知/
              通知.jpg

        每个 "2026.04.16-收到判决书" 子目录生成一条日志，日志内容包含目录标题和文件清单，
        附件为该子目录下的合规文件。如果子目录名以日期开头，日志的 created_at 会被设为该日期。

        去重逻辑：通过 source_subfolder 字段记录来源，重复导入时跳过已存在的子目录。

        Args:
            case_id: 案件 ID
            subfolder: 子文件夹相对路径（与 folder-scan/subfolders 返回的 relative_path 一致）
            user: 当前用户
            org_access: 组织访问策略
            perm_open_access: 是否有开放访问权限

        Returns:
            {"logs": 创建的 CaseLog 列表, "skipped_count": 跳过的子目录数量}
        """
        case_root = self._get_bound_case_root(case_id)
        if case_root is None:
            raise NotFoundError(_("案件未绑定可用文件夹"))

        target = self._resolve_subfolder(case_root, subfolder)

        if not target.exists() or not target.is_dir():
            raise ValidationException(_("指定文件夹不存在"), errors={"subfolder": _("文件夹路径无效")})

        # 收集子目录（每个子目录 = 一条日志）
        subdirs = self._collect_subdirs(target)
        if not subdirs:
            # 如果没有子目录，将整个文件夹作为一条日志
            files = self._collect_allowed_files(target)
            if not files:
                raise ValidationException(_("文件夹内没有可导入的文件"), errors={"subfolder": _("无合规文件")})
            subdirs = [(target, files)]

        # 查询该案件已有的来源子文件夹，用于去重
        existing_sources: set[str] = set(
            CaseLog.objects.filter(case_id=case_id)
            .exclude(source_subfolder="")  # type: ignore[misc]
            .values_list("source_subfolder", flat=True)  # type: ignore[misc]
        )

        created_logs: list[CaseLog] = []
        skipped_count = 0

        with transaction.atomic():
            for subdir, files in subdirs:
                # 去重：来源标识 = "子文件夹路径/子目录名"
                source_key = f"{subfolder}/{subdir.name}"
                if source_key in existing_sources:
                    skipped_count += 1
                    logger.info(f"案件 {case_id} 跳过已导入子目录: {source_key}")
                    continue

                content = self._build_log_content(subdir, files, target)

                log = self.mutation_service.create_log(
                    case_id=case_id,
                    content=content,
                    user=user,
                    org_access=org_access,
                    perm_open_access=perm_open_access,
                )

                # 回写 source_subfolder 用于后续去重
                log.source_subfolder = source_key  # type: ignore[attr-defined]
                log.save(update_fields=["source_subfolder"])

                # 如果子目录名以日期开头，回写 created_at
                date_match = _DATE_PATTERN.match(subdir.name)
                if date_match:
                    try:
                        year, month, day = int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3))
                        log.created_at = datetime(year, month, day, 12, 0, 0)
                        log.save(update_fields=["created_at"])
                    except ValueError:
                        pass  # 日期无效则跳过，使用默认时间

                # 逐个上传附件
                for file_path in files:
                    self._upload_file_as_attachment(log, file_path)

                created_logs.append(log)
                existing_sources.add(source_key)

        logger.info(
            f"案件 {case_id} 子文件夹导入完成: 目录={target.name}, "
            f"新增={len(created_logs)}, 跳过={skipped_count}"
        )
        return {"logs": created_logs, "skipped_count": skipped_count}

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _get_bound_case_root(self, case_id: int) -> Path | None:
        """获取案件绑定的文件夹根路径."""
        binding = CaseFolderBinding.objects.filter(case_id=case_id).select_related("case").first()
        if not binding or not binding.folder_path:
            return None

        root = Path(binding.folder_path).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            logger.warning(f"案件 {case_id} 绑定目录不可访问: {root}")
            return None
        return root

    def _resolve_subfolder(self, case_root: Path, subfolder: str) -> Path:
        """将相对子文件夹路径解析为绝对路径，并校验安全性."""
        raw = str(subfolder or "").strip().replace("\\", "/")
        if not raw:
            raise ValidationException(_("子文件夹路径不能为空"), errors={"subfolder": raw})

        if raw.startswith("/") or raw.startswith("~"):
            raise ValidationException(_("子文件夹必须使用相对路径"), errors={"subfolder": raw})

        parts = [p for p in raw.split("/") if p not in {"", "."}]
        if not parts:
            raise ValidationException(_("子文件夹路径不能为空"), errors={"subfolder": raw})
        if any(p == ".." for p in parts):
            raise ValidationException(_("子文件夹路径非法"), errors={"subfolder": raw})
        if any(p.startswith(".") for p in parts):
            raise ValidationException(_("子文件夹路径非法"), errors={"subfolder": raw})

        target = (case_root / "/".join(parts)).resolve()
        if not target.is_relative_to(case_root):
            raise ValidationException(
                _("文件夹路径不在案件绑定目录内"),
                errors={"subfolder": _("路径不在允许范围内")},
            )
        return target

    def _collect_subdirs(self, folder_path: Path) -> list[tuple[Path, list[Path]]]:
        """收集文件夹下所有含合规文件的子目录.

        Returns:
            [(子目录路径, [合规文件列表]), ...] 按目录名排序
        """
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

    def _collect_allowed_files(self, folder_path: Path) -> list[Path]:
        """递归收集文件夹内所有合规文件（扩展名 + 大小校验），跳过隐藏文件/目录."""
        result: list[Path] = []
        for f in sorted(folder_path.rglob("*")):
            if not f.is_file():
                continue
            # 跳过隐藏文件和隐藏目录下的文件
            try:
                rel_parts = f.relative_to(folder_path).parts
            except ValueError:
                continue
            if any(part.startswith(".") for part in rel_parts):
                continue
            if f.suffix.lower() not in CASE_LOG_ALLOWED_EXTENSIONS:
                continue
            try:
                if f.stat().st_size > CASE_LOG_MAX_FILE_SIZE:
                    logger.warning(f"文件超过大小限制，跳过: {f.name}")
                    continue
            except OSError:
                logger.warning(f"文件无法访问，跳过: {f.name}")
                continue
            result.append(f)
        return result

    def _build_log_content(self, subdir: Path, files: list[Path], root: Path) -> str:
        """构建日志内容，只保留文件夹名中日期之后的描述部分.

        例如 "2026.03.02-收到鉴定意见通知书等当事人传回材料" → "收到鉴定意见通知书等当事人传回材料"
        如果文件夹名没有日期前缀，则直接使用文件夹名。
        """
        name = subdir.name
        # 尝试去掉日期前缀，如 "2026.03.02-" 或 "2026-03-02-"
        content = re.sub(r"^\d{4}[.\-]\d{1,2}[.\-]\d{1,2}[\-\s]*", "", name)
        return content if content else name

    def _upload_file_as_attachment(self, log: CaseLog, file_path: Path) -> CaseLogAttachment | None:
        """将本地文件上传为日志附件."""
        try:
            with open(file_path, "rb") as f:
                file_content = f.read()

            uploaded_file = SimpleUploadedFile(
                name=file_path.name,
                content=file_content,
            )
            attachment = CaseLogAttachment.objects.create(log=log, file=uploaded_file)
            logger.info(f"附件上传成功: {file_path.name} -> 日志 {log.id}")
            return attachment
        except Exception:
            logger.exception(f"附件上传失败: {file_path.name}")
            return None
