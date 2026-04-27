"""
文书重命名服务

负责提取文书标题并生成规范的文件名。
"""

import logging
import re
from datetime import date
from pathlib import Path

from apps.automation.services.document.document_processing import extract_document_content
from apps.core.config import get_config
from apps.core.exceptions import ValidationException

logger = logging.getLogger(__name__)


class DocumentRenamer:
    """文书重命名服务"""

    DEFAULT_TITLE_EXTRACTION_LIMIT = 50

    COURT_PREFIX_PATTERNS = [
        r".*?人民法院",
        r".*?法院",
        r".*?仲裁委员会",
        r".*?仲裁院",
        r"广东",
        r"佛山市",
        r"禅城区",
    ]

    # 长标题优先，防止被短词（如"通知书"）抢先命中
    # 注意：_match_title_from_text 已改为最长匹配，此列表顺序不再影响匹配结果
    KNOWN_TITLES = [
        "广东法院诉讼费用交费通知书",
        "诉讼费用交纳通知书",
        "交纳诉讼费用通知书",
        "诉讼费用缴费通知书",
        "诉讼费用交费通知书",
        "诉讼材料提交告知书",
        "诉讼权利义务告知书",
        "诉讼法律责任风险提示书",
        "诉讼风险提醒书",
        "审判执行流程信息公开告知书",
        "受理案件通知书",
        "案件受理通知书",
        "小额诉讼告知书",
        "诉讼风险告知书",
        "财产保全裁定书",
        "虚假诉讼法律责任风险提示书",
        "诚信诉讼承诺书",
        "审判执行流程信息公开告知内容",
        # 裁判文书生效证明（含"调解书"子串，必须放在"调解书"之前）
        "裁判文书生效证明",
        # 民事调解书、刑事调解书（比"调解书"更具体）
        "民事调解书",
        "刑事调解书",
        # 民事判决书、刑事判决书（比"判决书"更具体）
        "民事判决书",
        "刑事判决书",
        "行政判决书",
        # 民事裁定书、刑事裁定书（比"裁定书"更具体）
        "民事裁定书",
        "刑事裁定书",
        "行政裁定书",
        # 其他复合标题
        "民事决定书",
        "刑事决定书",
        "执行裁定书",
        "仲裁裁决书",
        "交费通知书",
        "缴费通知书",
        "执行通知书",
        "应诉通知书",
        "举证通知书",
        "开庭传票",
        "廉政监督卡",
        "受理通知书",
        "判决书",
        "裁定书",
        "调解书",
        "决定书",
        "传票",
        "通知书",
        "支付令",
        "告知书",
    ]

    TITLE_PATTERNS = [
        r"([^，。；、:：\s]{2,30}?通知书)",
        r"([^，。；、:：\s]{2,30}?告知书)",
        r"([^，。；、:：\s]{2,30}?裁定书)",
        r"([^，。；、:：\s]{2,30}?判决书)",
        r"([^，。；、:：\s]{2,30}?调解书)",
        r"([^，。；、:：\s]{2,30}?决定书)",
        r"([^，。；、:：\s]{2,30}?传票)",
        r"([^，。；、:：\s]{2,30}?支付令)",
        r"([^，。；、:：\s]{2,30}?监督卡)",
        r"([^，。；、:：\s]{2,30}?提示书)",
        r"([^，。；、:：\s]{2,30}?承诺书)",
    ]

    def __init__(self, ollama_model: str | None = None, ollama_base_url: str | None = None):
        """
        初始化文书重命名服务

        Args:
            ollama_model: 兼容旧调用方，当前规则模式下忽略
            ollama_base_url: 兼容旧调用方，当前规则模式下忽略
        """
        if ollama_model or ollama_base_url:
            logger.debug("DocumentRenamer 已切换为规则模式，忽略 ollama 参数")
        self.title_extraction_limit = self._get_title_extraction_limit()

    def _get_title_extraction_limit(self) -> int:
        """
        读取短信文书标题提取场景的专用文本限制

        仅作用于短信文书重命名，不影响全局 PDF 提取限制。
        """
        raw_limit = get_config("services.sms.document_title_extraction_limit", self.DEFAULT_TITLE_EXTRACTION_LIMIT)
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            return self.DEFAULT_TITLE_EXTRACTION_LIMIT

        return max(20, min(limit, 5000))

    def extract_document_title(self, document_path: str) -> str:
        """
        提取文书主标题

        Args:
            document_path: 文书文件路径

        Returns:
            str: 提取的主标题

        Raises:
            ValidationException: 文件不存在或无法读取
        """
        if not Path(document_path).exists():
            raise ValidationException(f"文书文件不存在: {document_path}")

        try:
            # 使用 Document_Processor 读取文书内容
            extraction = extract_document_content(document_path, limit=self.title_extraction_limit)

            if not extraction.text:
                logger.warning(f"无法从文书中提取文本内容: {document_path}")
                return self._extract_title_from_filename(document_path)

            # 规则提取标题（不再调用 Ollama）
            title = self._extract_title_from_text(extraction.text)
            if title:
                logger.info(f"规则提取文书标题成功: {title}")
                return title

            logger.warning(f"规则未能从正文提取标题，使用文件名降级: {document_path}")
            return self._extract_title_from_filename(document_path)

        except Exception as e:
            logger.error(f"提取文书标题失败: {document_path}, 错误: {e!s}")
            # 抛出异常让调用方处理降级逻辑
            raise

    def _normalize_title_candidate(self, text: str) -> str:
        """
        清理标题候选文本

        Args:
            text: 候选文本

        Returns:
            str: 清理后的标题
        """
        if not text:
            return ""

        cleaned = text.strip().strip('"\'""')
        cleaned = re.sub(r"^[^_]{1,20}_", "", cleaned)
        cleaned = re.sub(r"[（(].*?[）)]", "", cleaned)
        cleaned = re.sub(r"\.pdf$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", "", cleaned)

        for prefix_pattern in self.COURT_PREFIX_PATTERNS:
            cleaned = re.sub(prefix_pattern, "", cleaned)

        cleaned = re.sub(r"^(下载|文书|司法文书)", "", cleaned)
        cleaned = re.sub(r"(副本|复件|\d+)$", "", cleaned)
        return cleaned

    def _match_title_from_text(self, text: str) -> str | None:
        cleaned = self._normalize_title_candidate(text)
        if not cleaned:
            return None

        # 第一轮：在 KNOWN_TITLES 中查找所有匹配项，选择最长的
        # 这样 "裁判文书生效证明" 优先于 "调解书" 被选中
        best_match: str | None = None
        for known_title in self.KNOWN_TITLES:
            if known_title in cleaned:
                if best_match is None or len(known_title) > len(best_match):
                    best_match = known_title
        if best_match:
            return best_match

        # 第二轮：用 TITLE_PATTERNS 正则匹配
        for pattern in self.TITLE_PATTERNS:
            match = re.search(pattern, cleaned)
            if not match:
                continue

            candidate = self._normalize_title_candidate(match.group(1))
            if not candidate:
                continue

            # 同样选择最长的 KNOWN_TITLES 匹配
            best_known: str | None = None
            for known_title in self.KNOWN_TITLES:
                if known_title in candidate:
                    if best_known is None or len(known_title) > len(best_known):
                        best_known = known_title
            if best_known:
                return best_known

            if len(candidate) <= 30:
                return candidate

        return None

    def _extract_title_from_text(self, content: str) -> str | None:
        """
        从正文文本中提取标题（规则模式）
        """
        return self._match_title_from_text(content)

    def _extract_title_from_filename(self, document_path: str) -> str:
        """
        从文件名中提取标题（降级方案）

        当规则无法从文件名中识别出文书标题时，使用原始文件名（去除扩展名）
        作为标题，避免所有无法识别的文件都被重命名为"司法文书"。

        Args:
            document_path: 文件路径

        Returns:
            str: 从文件名提取的标题
        """
        filename = Path(document_path).stem
        title = self._match_title_from_text(filename)
        if title:
            return title

        # 降级：使用原始文件名作为标题，而非"司法文书"
        cleaned = self._sanitize_filename_part(filename)
        return cleaned if cleaned else "司法文书"

    def generate_filename(self, title: str, case_name: str, received_date: date) -> str:
        """
        生成规范文件名

        格式：{主标题}（{案件名称}）_{YYYYMMDD}收.pdf

        Args:
            title: 文书主标题
            case_name: 案件名称
            received_date: 收到日期

        Returns:
            str: 生成的文件名
        """
        if not title:
            title = "司法文书"

        if not case_name:
            case_name = "未知案件"

        # 清理标题和案件名称中的非法字符
        title = self._sanitize_filename_part(title)
        case_name = self._sanitize_filename_part(case_name)

        # 限制长度避免文件名过长
        title_max = get_config("features.document_renaming.title_max_length", 20)
        case_name_max = get_config("features.document_renaming.case_name_max_length", 60)
        case_name_hash_length = get_config("features.document_renaming.case_name_hash_length", 6)

        if len(title) > title_max:
            title = title[:title_max]

        if len(case_name) > case_name_max:
            import hashlib

            suffix = hashlib.md5(case_name.encode(), usedforsecurity=False).hexdigest()[:case_name_hash_length]
            case_name = case_name[: case_name_max - case_name_hash_length - 1] + "_" + suffix

        # 格式化日期
        date_str = received_date.strftime("%Y%m%d")

        # 生成文件名：使用中文括号
        filename = f"{title}（{case_name}）_{date_str}收.pdf"

        return filename

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

    def rename(self, document_path: str, case_name: str, received_date: date) -> str:
        """
        重命名文书，返回新路径

        Args:
            document_path: 原始文书路径
            case_name: 案件名称
            received_date: 收到日期

        Returns:
            str: 重命名后的文件路径

        Raises:
            ValidationException: 文件操作失败
        """
        if not Path(document_path).exists():
            raise ValidationException(f"文书文件不存在: {document_path}")

        try:
            # 提取文书标题
            title = self.extract_document_title(document_path)

            # 生成新文件名
            new_filename = self.generate_filename(title, case_name, received_date)

            # 构建新文件路径
            original_path = Path(document_path)
            new_path = original_path.parent / new_filename

            # 如果新文件名已存在，在"收"字后面添加数字（带括号）
            counter = 1
            while new_path.exists():
                # 格式：xxx收(1).pdf, xxx收(2).pdf
                base_filename = new_filename.replace("收.pdf", f"收({counter}).pdf")
                new_path = original_path.parent / base_filename
                counter += 1
                if counter > 100:  # 防止无限循环
                    break

            # 重命名文件
            original_path.rename(new_path)

            logger.info(f"文书重命名成功: {document_path} -> {new_path}")
            return str(new_path)

        except Exception as e:
            logger.error(f"文书重命名失败: {document_path}, 错误: {e!s}")
            # 抛出异常让调用方处理降级逻辑
            raise

    def rename_with_fallback(
        self, document_path: str, case_name: str, received_date: date, original_name: str | None = None
    ) -> str:
        """
        带降级方案的重命名

        Args:
            document_path: 原始文书路径
            case_name: 案件名称
            received_date: 收到日期
            original_name: 原始文件名（用于降级）

        Returns:
            str: 重命名后的文件路径
        """
        try:
            return self.rename(document_path, case_name, received_date)
        except Exception as e:
            logger.warning(f"重命名失败，使用降级方案: {e!s}")

            # 降级方案：使用原始文件名（去除扩展名）作为标题
            if original_name:
                fallback_title = Path(original_name).stem
                fallback_title = self._sanitize_filename_part(fallback_title)
                if not fallback_title:
                    fallback_title = "司法文书"
            else:
                fallback_title = "司法文书"

            try:
                fallback_filename = self.generate_filename(fallback_title, case_name, received_date)

                original_path = Path(document_path)
                fallback_path = original_path.parent / fallback_filename

                # 避免文件名冲突，在"收"字后面添加数字（带括号）
                counter = 1
                while fallback_path.exists():
                    base_filename = fallback_filename.replace("收.pdf", f"收({counter}).pdf")
                    fallback_path = original_path.parent / base_filename
                    counter += 1
                    if counter > 100:
                        break

                original_path.rename(fallback_path)
                logger.info(f"使用降级方案重命名成功: {document_path} -> {fallback_path}")
                return str(fallback_path)

            except Exception as fallback_error:
                logger.error(f"降级方案也失败: {fallback_error!s}")
                return document_path
