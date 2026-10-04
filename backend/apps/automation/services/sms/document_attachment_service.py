"""
文书附件服务

负责处理文书路径获取、重命名、添加附件等操作。
从 CourtSMSService 中解耦出来的文书附件处理逻辑。
"""

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from apps.core.filesystem.upload_paths import MediaEntity
from apps.core.services.filename_template_service import FilenameTemplateService
from apps.core.services.storage_service import resolve_media_path, sanitize_upload_filename

if TYPE_CHECKING:
    from apps.automation.models import CourtSMS
    from apps.core.interfaces import ICaseService

    from .document_renamer import DocumentRenamer

logger = logging.getLogger("apps.automation")


class DocumentAttachmentService:
    """文书附件服务 - 处理文书路径获取、重命名、添加附件"""

    def __init__(
        self,
        case_service: Optional["ICaseService"] = None,
        renamer: Optional["DocumentRenamer"] = None,
    ):
        """
        初始化服务，支持依赖注入

        Args:
            case_service: 案件服务（可选）
            renamer: 文书重命名服务（可选）
        """
        self._case_service = case_service
        self._renamer = renamer

    @property
    def case_service(self) -> "ICaseService":
        """延迟加载案件服务"""
        if self._case_service is None:
            from apps.core.dependencies.automation_sms_wiring import build_sms_case_service

            self._case_service = build_sms_case_service()
        return self._case_service

    @property
    def renamer(self) -> "DocumentRenamer":
        """延迟加载重命名服务"""
        if self._renamer is None:
            from .document_renamer import DocumentRenamer

            self._renamer = DocumentRenamer()
        return self._renamer

    def get_paths_for_renaming(self, sms: "CourtSMS") -> list[str]:
        """
        获取待重命名的文书路径列表
        """
        if not sms.scraper_task:
            logger.info("短信 %s 无下载任务，返回空路径列表", sms.id)
            return []

        document_paths: list[str] = []
        try:
            document_paths = self._paths_from_court_documents(sms)

            if not document_paths:
                document_paths = self._paths_from_task_result(sms)

            logger.info("获取到 %s 个待重命名的文书路径", len(document_paths))
        except Exception as e:
            logger.warning("获取文书路径失败: %s", e)

        return document_paths

    def _paths_from_sms_reference(self, sms: "CourtSMS") -> list[str]:
        """从 CourtSMS 统一引用字段获取路径"""
        paths: list[str] = []
        if not isinstance(sms.document_file_paths, list):
            return paths
        for file_path in sms.document_file_paths:
            if file_path and resolve_media_path(file_path).exists():
                paths.append(file_path)
                logger.debug("从 CourtSMS 引用字段获取路径: %s", file_path)
        return paths

    def _paths_from_court_documents(self, sms: "CourtSMS") -> list[str]:
        """从 CourtDocument 记录获取路径"""
        paths: list[str] = []
        scraper_task = getattr(sms, "scraper_task", None)
        if not scraper_task or not hasattr(scraper_task, "documents"):
            return paths
        for doc in scraper_task.documents.filter(download_status="success"):
            if doc.local_file_path and resolve_media_path(doc.local_file_path).exists():
                paths.append(doc.local_file_path)
                logger.debug("从 CourtDocument 获取路径: %s", doc.local_file_path)
        return paths

    def _paths_from_task_result(self, sms: "CourtSMS") -> list[str]:
        """从 ScraperTask.result 获取路径（降级）"""
        paths: list[str] = []
        if not sms.scraper_task:
            return paths
        result = sms.scraper_task.result
        if not result or not isinstance(result, dict):
            return paths
        files = result.get("files", [])
        for file_path in files:
            if file_path and resolve_media_path(file_path).exists():
                paths.append(file_path)
                logger.debug("从 ScraperTask.result 获取路径: %s", file_path)
        if files and not paths:
            logger.warning("任务结果中有 %s 个文件路径，但都不存在", len(files))
        return paths

    def get_paths_for_notification(self, sms: "CourtSMS") -> list[str]:
        """
        获取待发送通知的文书路径列表（已去重）
        """
        document_paths: list[str] = []
        seen_paths: set[str] = set()

        try:
            self._collect_unique_paths(self._paths_from_sms_reference(sms), seen_paths, document_paths)

            if sms.scraper_task:
                result = sms.scraper_task.result

                # 方式1：优先使用 renamed_files（合并到 document_paths，不丢失 sms_reference）
                if result and isinstance(result, dict):
                    renamed = result.get("renamed_files", [])
                    if renamed:
                        self._collect_unique_paths(renamed, seen_paths, document_paths)
                        logger.info("从 renamed_files 获取到文书路径")

                # 方式2：从 CourtDocument 记录获取（仅当 renamed_files 为空时）
                if not document_paths:
                    self._collect_from_court_documents(sms, document_paths, seen_paths)

                # 方式3：从原始 files 列表获取（仅当以上均为空时）
                if not document_paths and result and isinstance(result, dict):
                    self._collect_unique_paths(result.get("files", []), seen_paths, document_paths)

            logger.info("获取到 %s 个待发送通知的文书路径（已去重）", len(document_paths))

        except Exception as e:
            logger.warning("获取通知文书路径失败: %s", e)

        return document_paths

    def _collect_unique_paths(
        self,
        file_list: list[str],
        seen: set[str],
        target: list[str] | None = None,
    ) -> list[str]:
        """收集不重复的有效路径，返回新增路径列表"""
        added: list[str] = []
        for fp in file_list:
            if fp and resolve_media_path(fp).exists():
                abs_path = str(resolve_media_path(fp).resolve())
                if abs_path not in seen:
                    seen.add(abs_path)
                    added.append(fp)
                    if target is not None:
                        target.append(fp)
                    logger.debug("收集路径: %s", fp)
        return added

    def _collect_from_court_documents(
        self, sms: "CourtSMS", target: list[str], seen: set[str]
    ) -> None:  # pragma: no cover
        """从 CourtDocument 记录收集路径"""
        scraper_task = getattr(sms, "scraper_task", None)
        if not scraper_task or not hasattr(scraper_task, "documents"):
            return
        for doc in scraper_task.documents.filter(download_status="success"):
            if doc.local_file_path and resolve_media_path(doc.local_file_path).exists():
                abs_path = str(resolve_media_path(doc.local_file_path).resolve())
                if abs_path not in seen:
                    target.append(doc.local_file_path)
                    seen.add(abs_path)
                    logger.debug("从 CourtDocument 获取路径: %s", doc.local_file_path)

    def rename_documents(self, sms: "CourtSMS", document_paths: list[str]) -> list[str]:
        """
        重命名文书列表，返回重命名后的路径

        使用 DocumentRenamer 对每个文件进行重命名，处理重命名失败的情况；
        重命名完成后同步回写各处引用（CourtDocument.local_file_path、短信引用
        字段、任务结果），避免下载 404 / 原件成孤儿。

        Args:
            sms: CourtSMS 实例
            document_paths: 待重命名的文书路径列表

        Returns:
            重命名后的文书路径列表
        """
        if not document_paths:
            logger.info("短信 %s 无文书需要重命名", sms.id)
            return []

        case_name = sms.case.name if sms.case else "未知案件"
        received_date = sms.received_at.date()
        renamed_paths = []
        # 记录 (旧绝对路径, 新绝对路径) 与 旧路径 → CourtDocument.id 映射，重命名后回写引用
        rename_pairs: list[tuple[str, str]] = []
        court_doc_ids = self._build_court_document_id_map(sms)

        logger.info("开始重命名 %s 个文书: SMS ID=%s", len(document_paths), sms.id)

        for file_path in document_paths:
            try:
                # local_file_path / 任务结果可能保存 media 相对路径，重命名前先解析为绝对路径
                abs_file_path = resolve_media_path(file_path)
                if not abs_file_path.exists():
                    logger.warning("文书文件不存在，跳过: %s", file_path)
                    continue

                # 获取原始文件名用于降级
                original_name = abs_file_path.name
                old_abs = str(abs_file_path.resolve())

                # 使用带降级方案的重命名
                new_path = self.renamer.rename_with_fallback(
                    str(abs_file_path), case_name, received_date, original_name=original_name
                )

                renamed_paths.append(new_path)
                logger.info("文书重命名成功: %s -> %s", file_path, new_path)

                new_abs = str(resolve_media_path(new_path).resolve())
                if new_abs != old_abs:
                    rename_pairs.append((old_abs, new_abs))

            except Exception as e:
                logger.warning("文书重命名失败，保持原名: %s, 错误: %s", file_path, e)
                # 重命名失败不影响流程，继续使用原路径
                if resolve_media_path(file_path).exists():
                    renamed_paths.append(file_path)

        logger.info("文书重命名完成: SMS ID=%s, 成功重命名 %s 个文书", sms.id, len(renamed_paths))

        # 物理重命名完成后回写引用，与手动重命名（admin/API）共用同一同步逻辑
        if rename_pairs:
            self._sync_references_after_rename(sms, rename_pairs, court_doc_ids)

        return renamed_paths

    def _build_court_document_id_map(self, sms: "CourtSMS") -> dict[str, int]:
        """构建 规范化绝对路径 → CourtDocument.id 映射（用于重命名后回写引用）"""
        mapping: dict[str, int] = {}
        scraper_task = getattr(sms, "scraper_task", None)
        if not scraper_task or not hasattr(scraper_task, "documents"):
            return mapping

        try:
            documents = list(scraper_task.documents.all())
        except Exception as e:
            logger.warning("获取 CourtDocument 列表失败，跳过引用回写映射: SMS ID=%s, 错误: %s", sms.id, e)
            return mapping

        for doc in documents:
            if not doc.local_file_path:
                continue
            try:
                mapping[str(resolve_media_path(doc.local_file_path).resolve())] = int(doc.id)
            except Exception as e:
                logger.warning("解析 CourtDocument 路径失败: doc_id=%s, 错误: %s", doc.id, e)
        return mapping

    def _sync_references_after_rename(
        self,
        sms: "CourtSMS",
        rename_pairs: list[tuple[str, str]],
        court_doc_ids: dict[str, int],
    ) -> None:
        """将新旧路径映射传给引用同步服务，回写 CourtDocument 等引用字段"""
        from apps.automation.services.sms.court_sms_document_reference_service import CourtSMSDocumentReferenceService

        reference_service = CourtSMSDocumentReferenceService()
        for old_abs, new_abs in rename_pairs:
            try:
                reference_service.sync_document_references(sms, old_abs, new_abs, court_doc_ids.get(old_abs))
                logger.info("已同步重命名后的文书引用: %s -> %s", old_abs, new_abs)
            except Exception as e:
                # 引用同步失败不阻断主流程（文件已完成重命名），记录日志供人工修复
                logger.error("同步文书引用失败: SMS ID=%s, %s -> %s, 错误: %s", sms.id, old_abs, new_abs, e)

    def add_to_case_log(self, sms: "CourtSMS", file_paths: list[str]) -> bool:  # pragma: no cover
        """
        将文书附件添加到案件日志
        """
        if not sms.case_log or not file_paths:
            logger.warning("短信 %s 没有案件日志或文件路径，无法添加附件", sms.id)
            return False

        try:
            success_count = 0

            for file_path in file_paths:
                if self._add_single_attachment(sms, file_path):
                    success_count += 1

            logger.info("附件添加完成: 成功 %s/%s 个", success_count, len(file_paths))
            return success_count > 0

        except (OSError, ValueError) as e:
            logger.error("添加附件到案件日志失败: SMS ID=%s, 错误: %s", sms.id, e)
            return False

    def _add_single_attachment(self, sms: "CourtSMS", file_path: str) -> bool:  # pragma: no cover
        """添加单个附件，返回是否成功"""
        try:
            src_path = resolve_media_path(file_path)
            if not src_path.exists():
                logger.warning("文件不存在，跳过: %s", file_path)
                return False

            renamed_filename = src_path.name
            if "（" not in renamed_filename or "）" not in renamed_filename:
                logger.warning("文件名格式不正确，尝试修正: %s", renamed_filename)
                renamed_filename = self.fix_filename_format(renamed_filename, sms)

            max_name_length = 200
            if len(renamed_filename) > max_name_length:
                p = Path(renamed_filename)
                ext = p.suffix or ".pdf"
                renamed_filename = p.stem[: max_name_length - len(ext)] + ext

            safe_name = sanitize_upload_filename(renamed_filename)
            rel_target = f"{MediaEntity.CASE_LOGS}/{safe_name}"
            with src_path.open("rb") as f:
                # default_storage.save 重名时自动加后缀，返回实际保存的相对路径
                relative_path = str(default_storage.save(rel_target, ContentFile(f.read())))
            renamed_filename = Path(relative_path).name

            if not sms.case_log:
                logger.warning("短信 %s 无案件日志，无法写入附件", sms.id)
                return False

            success = self.case_service.add_case_log_attachment_internal(
                case_log_id=sms.case_log.id,
                file_path=relative_path,
                file_name=renamed_filename,
            )
            if not success:
                logger.warning("添加案件日志附件失败: %s", renamed_filename)
                return False

            logger.info("成功添加文书附件到案件日志: %s", renamed_filename)
            return True

        except (OSError, ValueError) as e:
            logger.warning("添加文书附件失败: %s, 错误: %s", file_path, e)
            return False

    def fix_filename_format(self, filename: str, sms: "CourtSMS") -> str:
        """
        修正文件名格式，确保符合预期的格式：标题（案件名称）_YYYYMMDD收.pdf

        Args:
            filename: 原始文件名
            sms: CourtSMS 实例

        Returns:
            修正后的文件名
        """
        try:
            # 移除文件扩展名
            name_without_ext = filename
            if "." in filename:
                name_without_ext = filename.rsplit(".", 1)[0]

            # 获取案件名称和日期
            case_name = sms.case.name if sms.case else "未知案件"
            received_date = sms.received_at.date()
            date_str = received_date.strftime("%Y%m%d")

            # 清理案件名称中的非法字符
            case_name = self._sanitize_filename_part(case_name)
            if len(case_name) > 30:
                case_name = case_name[:30]

            # 尝试从原文件名中提取标题
            title = ""  # 默认为空，后续降级使用原文件名

            # 常见的文书类型模式
            title_patterns = [
                r"(诉讼费用交费通知书|交费通知书)",
                r"(受理案件通知书|案件受理通知书|受理通知书)",
                r"(诉讼权利义务告知书|权利义务告知书)",
                r"(诉讼风险告知书|风险告知书)",
                r"(小额诉讼告知书|诉讼告知书)",
                r"(判决书|裁定书|调解书|决定书|传票|通知书|支付令|告知书)",
            ]

            for pattern in title_patterns:
                match = re.search(pattern, name_without_ext)
                if match:
                    title = match.group(1)
                    break

            # 降级：匹配不到时使用原文件名（去除扩展名）作为标题
            if not title:
                title = self._sanitize_filename_part(name_without_ext)
                if not title:
                    title = "司法文书"

            # 使用模板服务生成正确格式的文件名
            rendered = FilenameTemplateService.render_court_doc(title=title, case_name=case_name, date=date_str)
            fixed_filename = f"{rendered}.pdf"

            logger.info("文件名格式修正: %s -> %s", filename, fixed_filename)
            return fixed_filename

        except Exception as e:
            logger.warning("修正文件名格式失败: %s, 错误: %s", filename, e)
            # 返回一个基本的格式，使用原文件名作为标题
            name_without_ext = filename.rsplit(".", 1)[0] if "." in filename else filename
            fallback_title = self._sanitize_filename_part(name_without_ext) or "司法文书"
            case_name = sms.case.name if sms.case else "未知案件"
            date_str = sms.received_at.strftime("%Y%m%d")
            rendered = FilenameTemplateService.render_court_doc(
                title=fallback_title, case_name=case_name, date=date_str
            )
            return f"{rendered}.pdf"

    def _sanitize_filename_part(self, text: str) -> str:
        """
        清理文件名部分，移除非法字符

        Args:
            text: 原始文本

        Returns:
            str: 清理后的文本
        """
        if not text:
            return ""

        # 移除或替换文件名中的非法字符
        # Windows 文件名非法字符: < > : " | ? * \ /
        illegal_chars = r'[<>:"|?*\\/]'
        text = re.sub(illegal_chars, "", text)

        # 移除英文括号，避免与中文括号混淆
        text = re.sub(r"[()]", "", text)

        # 移除控制字符
        text = re.sub(r"[\x00-\x1f\x7f]", "", text)

        # 移除首尾空格和点号
        text = text.strip(" .")

        return text

    def _find_renamed_file(self, original_path: str, sms: "CourtSMS") -> str | None:
        """查找重命名后的文件"""
        import glob

        try:
            if not original_path:
                return None

            directory = str(resolve_media_path(original_path).parent)
            if not Path(directory).exists():
                return None

            case_name = sms.case.name if sms.case else None
            if not case_name:
                return None

            pattern = str(Path(directory) / f"*{case_name[:10]}*.pdf")
            matches = glob.glob(pattern)

            if matches:
                matches.sort(key=lambda p: Path(p).stat().st_mtime, reverse=True)
                logger.info("找到重命名后的文件: %s", matches[0])
                return matches[0]

            return None

        except Exception as e:
            logger.warning("查找重命名文件失败: %s", e)
            return None
