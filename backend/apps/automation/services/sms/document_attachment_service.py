"""
文书附件服务

负责处理文书路径获取、重命名、添加附件等操作。
从 CourtSMSService 中解耦出来的文书附件处理逻辑。
"""

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from apps.automation.models import CourtSMS
    from apps.core.interfaces import ICaseService

    from .document_renamer import DocumentRenamer

logger = logging.getLogger("apps.automation")


class DocumentAttachmentService:
    RESULT_RECOMMENDATION_NAMES_KEY = "recommendation_names_by_path"
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
            logger.info(f"短信 {sms.id} 无下载任务，返回空路径列表")
            return []

        document_paths: list[str] = []
        try:
            document_paths = self._paths_from_court_documents(sms)

            if not document_paths:
                document_paths = self._paths_from_task_result(sms)

            logger.info(f"获取到 {len(document_paths)} 个待重命名的文书路径")
        except Exception as e:
            logger.warning(f"获取文书路径失败: {e!s}")

        return document_paths

    def _paths_from_sms_reference(self, sms: "CourtSMS") -> list[str]:
        """从 CourtSMS 统一引用字段获取路径"""
        paths: list[str] = []
        if not isinstance(sms.document_file_paths, list):
            return paths
        for file_path in sms.document_file_paths:
            if file_path and Path(file_path).exists():
                paths.append(file_path)
                logger.debug(f"从 CourtSMS 引用字段获取路径: {file_path}")
        return paths

    def _paths_from_court_documents(self, sms: "CourtSMS") -> list[str]:
        """从 CourtDocument 记录获取路径"""
        paths: list[str] = []
        scraper_task = getattr(sms, "scraper_task", None)
        if not scraper_task or not hasattr(scraper_task, "documents"):
            return paths
        for doc in scraper_task.documents.filter(download_status="success"):
            if doc.local_file_path and Path(doc.local_file_path).exists():
                paths.append(doc.local_file_path)
                logger.debug(f"从 CourtDocument 获取路径: {doc.local_file_path}")
        return paths

    def build_recommendation_names_by_path(self, sms: "CourtSMS") -> dict[str, str]:
        """为自动归档推荐构建“文件路径 -> 原始文书名”映射。"""
        names_by_path: dict[str, str] = {}

        scraper_task = getattr(sms, "scraper_task", None)
        if scraper_task and hasattr(scraper_task, "documents"):
            for doc in scraper_task.documents.filter(download_status="success"):
                raw_path = str(getattr(doc, "local_file_path", "") or "").strip()
                raw_name = str(getattr(doc, "c_wsmc", "") or "").strip()
                file_ext = str(getattr(doc, "c_wjgs", "") or "").strip().lstrip(".")
                if not raw_path or not raw_name:
                    continue
                normalized_path = self._normalize_existing_path(raw_path)
                if not normalized_path:
                    continue
                recommendation_name = raw_name if not file_ext else f"{raw_name}.{file_ext}"
                names_by_path[normalized_path] = recommendation_name

        return names_by_path

    def build_recommendation_names_for_paths(
        self,
        sms: "CourtSMS",
        file_paths: list[str],
        *,
        original_paths: list[str] | None = None,
    ) -> dict[str, str]:
        """为目标文件路径构建推荐名称映射，确保重命名后路径也能命中原始文书名。"""
        if not file_paths:
            return {}

        names_by_target_path = self.get_saved_recommendation_names_for_paths(sms, file_paths)
        missing_file_paths = [
            path for path in file_paths if self._normalize_existing_path(path) not in names_by_target_path
        ]
        if not missing_file_paths:
            return names_by_target_path

        names_by_original_path = self.build_recommendation_names_by_path(sms)
        if not names_by_original_path:
            return names_by_target_path

        candidate_original_paths = list(original_paths or self._get_original_paths_for_recommendation(sms))

        for target_path, source_path in zip(missing_file_paths, candidate_original_paths, strict=False):
            normalized_target = self._normalize_existing_path(target_path)
            normalized_source = self._normalize_existing_path(source_path)
            recommendation_name = names_by_original_path.get(normalized_source, "")
            if normalized_target and recommendation_name:
                names_by_target_path[normalized_target] = recommendation_name

        if all(self._normalize_existing_path(path) in names_by_target_path for path in file_paths):
            return names_by_target_path

        for path in missing_file_paths:
            normalized_path = self._normalize_existing_path(path)
            recommendation_name = names_by_original_path.get(normalized_path, "")
            if normalized_path and recommendation_name:
                names_by_target_path[normalized_path] = recommendation_name

        return names_by_target_path

    def get_saved_recommendation_names_by_path(self, sms: "CourtSMS") -> dict[str, str]:
        scraper_task = getattr(sms, "scraper_task", None)
        result = getattr(scraper_task, "result", None)
        if not isinstance(result, dict):
            return {}

        raw_mapping = result.get(self.RESULT_RECOMMENDATION_NAMES_KEY)
        if not isinstance(raw_mapping, dict):
            return {}

        normalized_mapping: dict[str, str] = {}
        for raw_path, raw_name in raw_mapping.items():
            normalized_path = self._normalize_existing_path(str(raw_path or ""))
            recommendation_name = str(raw_name or "").strip()
            if normalized_path and recommendation_name:
                normalized_mapping[normalized_path] = recommendation_name
        return normalized_mapping

    def get_saved_recommendation_names_for_paths(self, sms: "CourtSMS", file_paths: list[str]) -> dict[str, str]:
        saved_mapping = self.get_saved_recommendation_names_by_path(sms)
        if not saved_mapping:
            return {}

        names_by_target_path: dict[str, str] = {}
        for raw_path in file_paths:
            normalized_path = self._normalize_existing_path(raw_path)
            recommendation_name = saved_mapping.get(normalized_path, "")
            if normalized_path and recommendation_name:
                names_by_target_path[normalized_path] = recommendation_name
        return names_by_target_path

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
            if file_path and Path(file_path).exists():
                paths.append(file_path)
                logger.debug(f"从 ScraperTask.result 获取路径: {file_path}")
        if files and not paths:
            logger.warning(f"任务结果中有 {len(files)} 个文件路径，但都不存在")
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

            logger.info(f"获取到 {len(document_paths)} 个待发送通知的文书路径（已去重）")

        except Exception as e:
            logger.warning(f"获取通知文书路径失败: {e!s}")

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
            if fp and Path(fp).exists():
                abs_path = str(Path(fp).resolve())
                if abs_path not in seen:
                    seen.add(abs_path)
                    added.append(fp)
                    if target is not None:
                        target.append(fp)
                    logger.debug(f"收集路径: {fp}")
        return added

    def _collect_from_court_documents(self, sms: "CourtSMS", target: list[str], seen: set[str]) -> None:
        """从 CourtDocument 记录收集路径"""
        scraper_task = getattr(sms, "scraper_task", None)
        if not scraper_task or not hasattr(scraper_task, "documents"):
            return
        for doc in scraper_task.documents.filter(download_status="success"):
            if doc.local_file_path and Path(doc.local_file_path).exists():
                abs_path = str(Path(doc.local_file_path).resolve())
                if abs_path not in seen:
                    target.append(doc.local_file_path)
                    seen.add(abs_path)
                    logger.debug(f"从 CourtDocument 获取路径: {doc.local_file_path}")

    def _get_original_paths_for_recommendation(self, sms: "CourtSMS") -> list[str]:
        """获取自动归档推荐所需的原始下载路径，优先使用任务结果中的原始 files 列表。"""
        scraper_task = getattr(sms, "scraper_task", None)
        if scraper_task and isinstance(getattr(scraper_task, "result", None), dict):
            raw_files = [
                str(path or "").strip()
                for path in scraper_task.result.get("files", [])
                if str(path or "").strip()
            ]
            if raw_files:
                return raw_files

        raw_paths: list[str] = []
        if scraper_task and hasattr(scraper_task, "documents"):
            for doc in scraper_task.documents.filter(download_status="success"):
                raw_path = str(getattr(doc, "local_file_path", "") or "").strip()
                if raw_path:
                    raw_paths.append(raw_path)
        return raw_paths

    def _normalize_existing_path(self, raw_path: str | None) -> str:
        normalized = str(raw_path or "").strip()
        if not normalized:
            return ""
        return str(Path(normalized).expanduser().resolve())

    def rename_documents(self, sms: "CourtSMS", document_paths: list[str]) -> list[str]:
        """
        重命名文书列表，返回重命名后的路径

        使用 DocumentRenamer 对每个文件进行重命名，处理重命名失败的情况

        Args:
            sms: CourtSMS 实例
            document_paths: 待重命名的文书路径列表

        Returns:
            重命名后的文书路径列表
        """
        if not document_paths:
            logger.info(f"短信 {sms.id} 无文书需要重命名")
            return []

        case_name = sms.case.name if sms.case else "未知案件"
        received_date = sms.received_at.date()
        renamed_paths = []

        logger.info(f"开始重命名 {len(document_paths)} 个文书: SMS ID={sms.id}")

        for file_path in document_paths:
            try:
                if not Path(file_path).exists():
                    logger.warning(f"文书文件不存在，跳过: {file_path}")
                    continue

                # 获取原始文件名用于降级
                original_name = Path(file_path).name

                # 使用带降级方案的重命名
                new_path = self.renamer.rename_with_fallback(
                    file_path, case_name, received_date, original_name=original_name
                )

                renamed_paths.append(new_path)
                logger.info(f"文书重命名成功: {file_path} -> {new_path}")

            except Exception as e:
                logger.warning(f"文书重命名失败，保持原名: {file_path}, 错误: {e!s}")
                # 重命名失败不影响流程，继续使用原路径
                if Path(file_path).exists():
                    renamed_paths.append(file_path)

        logger.info(f"文书重命名完成: SMS ID={sms.id}, 成功重命名 {len(renamed_paths)} 个文书")
        return renamed_paths

    def add_to_case_log(
        self,
        sms: "CourtSMS",
        file_paths: list[str],
        recommendation_names_by_path: dict[str, str] | None = None,
    ) -> bool:
        """
        将文书附件添加到案件日志
        """
        if not sms.case_log or not file_paths:
            logger.warning(f"短信 {sms.id} 没有案件日志或文件路径，无法添加附件")
            return False

        try:
            success_count = 0

            recommendation_names = recommendation_names_by_path or self.build_recommendation_names_for_paths(
                sms, file_paths
            )

            for file_path in file_paths:
                normalized_file_path = self._normalize_existing_path(file_path)
                if self._add_single_attachment(
                    sms,
                    file_path,
                    recommendation_file_name=recommendation_names.get(str(file_path), "")
                    or recommendation_names.get(normalized_file_path, ""),
                ):
                    success_count += 1

            logger.info(f"附件添加完成: 成功 {success_count}/{len(file_paths)} 个")
            return success_count > 0

        except Exception as e:
            logger.error(f"添加附件到案件日志失败: SMS ID={sms.id}, 错误: {e!s}")
            return False

    def _add_single_attachment(
        self,
        sms: "CourtSMS",
        file_path: str,
        recommendation_file_name: str = "",
    ) -> bool:
        """添加单个附件，返回是否成功"""
        try:
            if not Path(file_path).exists():
                logger.warning(f"文件不存在，跳过: {file_path}")
                return False

            renamed_filename = Path(file_path).name
            preferred_recommendation_name = str(recommendation_file_name or "").strip() or renamed_filename
            if "（" not in renamed_filename or "）" not in renamed_filename:
                logger.warning(f"文件名格式不正确，尝试修正: {renamed_filename}")
                renamed_filename = self.fix_filename_format(renamed_filename, sms)

            max_name_length = 200
            if len(renamed_filename) > max_name_length:
                p = Path(renamed_filename)
                ext = p.suffix or ".pdf"
                renamed_filename = p.stem[: max_name_length - len(ext)] + ext

            if not sms.case_log:
                logger.warning(f"短信 {sms.id} 无案件日志，无法写入附件")
                return False

            success = self.case_service.add_case_log_attachment_internal(
                case_log_id=sms.case_log.id,
                file_path=file_path,
                file_name=renamed_filename,
                source_scene="court_sms_attachment",
                recommendation_file_name=preferred_recommendation_name,
            )
            if not success:
                logger.warning(f"添加案件日志附件失败: {renamed_filename}")
                return False

            logger.info(f"成功添加文书附件到案件日志: {renamed_filename}")
            return True

        except Exception as e:
            logger.warning(f"添加文书附件失败: {file_path}, 错误: {e!s}")
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

            # 生成正确格式的文件名
            fixed_filename = f"{title}（{case_name}）_{date_str}收.pdf"

            logger.info(f"文件名格式修正: {filename} -> {fixed_filename}")
            return fixed_filename

        except Exception as e:
            logger.warning(f"修正文件名格式失败: {filename}, 错误: {e!s}")
            # 返回一个基本的格式，使用原文件名作为标题
            name_without_ext = filename.rsplit(".", 1)[0] if "." in filename else filename
            fallback_title = self._sanitize_filename_part(name_without_ext) or "司法文书"
            case_name = sms.case.name if sms.case else "未知案件"
            date_str = sms.received_at.strftime("%Y%m%d")
            return f"{fallback_title}（{case_name}）_{date_str}收.pdf"

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

            directory = str(Path(original_path).parent)
            if not Path(directory).exists():
                return None

            case_name = sms.case.name if sms.case else None
            if not case_name:
                return None

            pattern = str(Path(directory) / f"*{case_name[:10]}*.pdf")
            matches = glob.glob(pattern)

            if matches:
                matches.sort(key=lambda p: Path(p).stat().st_mtime, reverse=True)
                logger.info(f"找到重命名后的文件: {matches[0]}")
                return matches[0]

            return None

        except Exception as e:
            logger.warning(f"查找重命名文件失败: {e!s}")
            return None

