"""法院短信案件目录归档服务."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

from django.utils import timezone

from apps.cases.models import CaseFolderBinding
from apps.core.exceptions import ValidationException
from apps.core.filesystem.filesystem_service import FolderFilesystemService
from apps.core.services.storage_service import resolve_media_path

if TYPE_CHECKING:
    from apps.automation.models import CourtSMS

logger = logging.getLogger("apps.automation")


class CaseFolderArchiveService:
    """将短信和文书归档到案件绑定文件夹."""

    MAIL_FOLDER_KEYWORDS = ("邮件往来", "邮寄", "邮件")
    DEFAULT_MAIL_FOLDER_NAME = "邮件往来"
    DEFAULT_EVENT_SUMMARY = "收到材料"
    EVENT_MARKDOWN_FILENAME = "法院短信.md"
    MAX_SCAN_DEPTH = 4

    def __init__(self, filesystem_service: FolderFilesystemService | None = None) -> None:
        """支持注入文件系统写入服务（默认即时构造）."""
        self._filesystem_service = filesystem_service

    @property
    def filesystem_service(self) -> FolderFilesystemService:
        if self._filesystem_service is None:
            self._filesystem_service = FolderFilesystemService()
        return self._filesystem_service

    def archive_sms_documents(self, sms: CourtSMS, renamed_paths: list[str]) -> bool:  # pragma: no cover
        """执行归档流程，返回是否成功归档."""
        if not sms.case_id:
            logger.info(f"短信 {sms.id} 未关联案件，跳过案件目录归档")
            return False
        if not renamed_paths:
            logger.info(f"短信 {sms.id} 无重命名文书，跳过案件目录归档")
            return False

        case_root = self._get_bound_case_root(sms.case_id)
        if case_root is None:
            logger.info(f"短信 {sms.id} 案件未绑定可用文件夹，跳过案件目录归档")
            return False

        mail_folder = self._find_mail_folder(case_root)
        if mail_folder is None:
            mail_folder = self._create_mail_folder(case_root)
            logger.info(f"短信 {sms.id} 未找到邮件目录，已自动创建: {mail_folder}")

        event_folder_name = self._build_event_folder_name(sms, renamed_paths)
        archive_folder = self._ensure_unique_directory(mail_folder, event_folder_name)
        archive_folder.mkdir(parents=True, exist_ok=False)

        markdown_path = self._write_sms_markdown(archive_folder, sms, renamed_paths)
        copied_count = self._copy_documents(archive_folder, renamed_paths)

        logger.info(
            f"短信 {sms.id} 案件目录归档完成: 目录={archive_folder}, 文书={copied_count}, md={markdown_path.name}"
        )
        return True

    def _get_bound_case_root(self, case_id: int) -> Path | None:  # pragma: no cover
        binding = CaseFolderBinding.objects.filter(case_id=case_id).first()
        if not binding or not binding.resolved_folder_path:
            return None

        # 本服务依赖本地目录扫描（邮件目录发现/事件目录创建），云存储绑定明确跳过而非静默不归档
        storage_type = str(getattr(binding, "storage_type", "") or "local")
        if storage_type != "local":
            logger.warning(f"案件 {case_id} 绑定为云存储({storage_type})，法院短信案件目录归档暂不支持，已跳过")
            return None

        root = Path(binding.resolved_folder_path).expanduser()
        if not root.exists() or not root.is_dir():
            logger.warning(f"案件 {case_id} 绑定目录不可访问: {root}")
            return None
        return root

    def _find_mail_folder(self, case_root: Path) -> Path | None:
        candidates: list[tuple[int, int, int, Path]] = []

        for current, dirnames, _ in os.walk(case_root):
            current_path = Path(current)
            depth = len(current_path.relative_to(case_root).parts)

            if depth > self.MAX_SCAN_DEPTH:
                dirnames[:] = []
                continue
            if depth == 0:
                continue

            score = self._mail_keyword_score(current_path.name)
            if score <= 0:
                continue

            prefix_number = self._extract_leading_number(current_path.name)
            candidates.append((score, depth, prefix_number, current_path))

        if not candidates:
            return None

        candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        return candidates[0][3]

    def _mail_keyword_score(self, folder_name: str) -> int:
        name = folder_name.strip()
        if name == "邮件往来":
            return 120
        if "邮件往来" in name:
            return 100
        if "邮寄" in name:
            return 80
        if "邮件" in name:
            return 60
        return 0

    def _extract_leading_number(self, folder_name: str) -> int:
        match = re.match(r"^\s*(\d+)[\s\-_.、)]*", folder_name)
        if not match:
            return 0
        return int(match.group(1))

    def _create_mail_folder(self, case_root: Path) -> Path:  # pragma: no cover
        max_prefix = 0
        for child in case_root.iterdir():
            if not child.is_dir():
                continue
            max_prefix = max(max_prefix, self._extract_leading_number(child.name))

        next_prefix = max_prefix + 1
        while True:
            candidate = case_root / f"{next_prefix}-{self.DEFAULT_MAIL_FOLDER_NAME}"
            if not candidate.exists():
                candidate.mkdir(parents=True, exist_ok=False)
                return candidate
            next_prefix += 1

    def _build_event_folder_name(self, sms: CourtSMS, renamed_paths: list[str]) -> str:
        date_text = sms.received_at.strftime("%Y.%m.%d")
        summary = self._build_event_summary(sms, renamed_paths)
        return f"{date_text}-{summary}"

    def _build_event_summary(self, sms: CourtSMS, renamed_paths: list[str]) -> str:
        best_priority = 0
        best_summary = ""

        for file_path in renamed_paths:
            title = self._extract_title_from_filename(file_path)
            if not title:
                continue
            priority, summary = self._infer_summary(title)
            if priority > best_priority and summary:
                best_priority = priority
                best_summary = summary

        sms_priority, sms_summary = self._infer_summary(sms.content)
        if sms_priority > best_priority and sms_summary:
            best_summary = sms_summary
            best_priority = sms_priority

        if best_priority > 0 and best_summary:
            return self._sanitize_folder_name(best_summary)

        return self._sanitize_folder_name(self.DEFAULT_EVENT_SUMMARY)

    def _extract_title_from_filename(self, file_path: str) -> str:
        stem = Path(file_path).stem
        if stem.endswith(".pdf"):
            stem = stem[:-4]
        if "（" in stem:
            stem = stem.split("（", 1)[0]
        if "_" in stem:
            stem = stem.split("_", 1)[0]
        return stem.strip()

    def _infer_summary(self, text: str) -> tuple[int, str]:
        normalized = text.strip()
        if not normalized:
            return 0, ""

        keyword_rules: list[tuple[int, tuple[str, ...], str]] = [
            (100, ("立案", "受理"), "收到法院立案材料"),
            (90, ("诉讼费用", "交费", "缴费"), "收到诉讼费材料"),
            (85, ("判决书",), "收到法院判决书"),
            (85, ("裁定书",), "收到法院裁定书"),
            (80, ("调解书",), "收到法院调解书"),
            (75, ("传票",), "收到开庭传票"),
            (60, ("通知书", "告知书"), "收到法院通知"),
        ]
        for priority, keywords, mapped in keyword_rules:
            if any(word in normalized for word in keywords):
                return priority, mapped

        compact = self._sanitize_folder_name(normalized)
        if not compact:
            return 0, ""
        if compact.startswith("收到"):
            return 20, compact[:24]
        return 20, f"收到{compact[:20]}"

    def _sanitize_folder_name(self, text: str) -> str:
        clean = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "", text or "")
        clean = re.sub(r"\s+", "", clean)
        clean = clean.strip(" .")
        return clean[:30] or self.DEFAULT_EVENT_SUMMARY

    def _ensure_unique_directory(self, parent: Path, folder_name: str) -> Path:
        candidate = parent / folder_name
        if not candidate.exists():
            return candidate

        index = 2
        while True:
            with_suffix = parent / f"{folder_name}_{index}"
            if not with_suffix.exists():
                return with_suffix
            index += 1

    def _write_sms_markdown(
        self, archive_folder: Path, sms: CourtSMS, renamed_paths: list[str]
    ) -> Path:  # pragma: no cover
        sms_type_display = sms.get_sms_type_display() if sms.sms_type else "未分类"
        case_name = sms.case.name if sms.case else "未关联案件"

        lines = [
            "# 法院短信记录",
            "",
            f"- 短信ID: {sms.id}",
            f"- 收到时间: {sms.received_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"- 归档时间: {timezone.localtime().strftime('%Y-%m-%d %H:%M:%S')}",
            f"- 短信类型: {sms_type_display}",
            f"- 关联案件: {case_name}",
            "",
            "## 短信原文",
            "",
            sms.content.strip() or "(空)",
            "",
            "## 文书清单",
            "",
        ]

        for file_path in renamed_paths:
            lines.append(f"- {Path(file_path).name}")

        content = ("\n".join(lines) + "\n").encode("utf-8")
        return self._save_bytes_to_archive(archive_folder, self.EVENT_MARKDOWN_FILENAME, content)

    def _copy_documents(self, archive_folder: Path, renamed_paths: list[str]) -> int:  # pragma: no cover
        copied_count = 0
        for file_path in renamed_paths:
            src = resolve_media_path(file_path)
            if not src.exists() or not src.is_file():
                logger.warning(f"归档复制时文件不存在，跳过: {file_path}")
                continue

            self._save_bytes_to_archive(archive_folder, src.name, src.read_bytes())
            copied_count += 1
        return copied_count

    def _save_bytes_to_archive(self, archive_folder: Path, file_name: str, content: bytes) -> Path:
        """通过 core filesystem 服务写入归档目录（文件名清洗 + 越界校验 + 自动唯一后缀）。"""
        try:
            saved_path = self.filesystem_service.save_bytes(
                base_path=str(archive_folder),
                relative_dir_parts=[],
                file_name=file_name,
                content=content,
            )
        except ValidationException:
            # 文件名含非法字符等场景，降级为时间戳命名，避免归档中断
            fallback_name = f"{timezone.localtime().strftime('%Y%m%d_%H%M%S')}_{len(content)}.bin"
            saved_path = self.filesystem_service.save_bytes(
                base_path=str(archive_folder),
                relative_dir_parts=[],
                file_name=fallback_name,
                content=content,
            )
        return Path(saved_path)
