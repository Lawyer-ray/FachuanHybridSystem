"""
裁判文书PDF解析服务

从PDF裁判文书中提取判决主文或调解协议内容。
支持正则兜底+Ollama大模型兜底。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from apps.core.exceptions import BusinessException

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    """解析结果数据类"""

    number: str | None = None  # 案号
    document_name: str | None = None  # 文书名称
    content: str | None = None  # 执行依据主文


class JudgmentPdfExtractor:
    """从PDF裁判文书中提取判决/调解主文"""

    # 判决主文关键词（按优先级排序）
    JUDGMENT_KEYWORDS = [
        "判决如下：",
        "判决如下:",
        "自愿达成如下协议：",
        "自愿达成如下协议:",
        "各方当事人自行和解达成如下协议",  # 新增：自行和解格式
        "当事人自行和解达成如下协议",
        "经本院主持调解，双方当事人自愿达成如下协议",
    ]

    # 截止关键词（执行依据主文到此为止）
    END_KEYWORDS = [
        "如不服本判决",
        "如不服本判决书",
        "如不服本调解书",
        "上诉期限",
        "本调解书生效后",
        "驳回上诉，维持原判",  # 二审终审判决截止
        "审判员",
        "书记员",
        "本件与原本核对无异",
    ]

    # 文书名称关键词
    DOCUMENT_NAME_KEYWORDS = [
        "民事判决书",
        "民事调解书",
        "行政判决书",
        "行政调解书",
        "刑事判决书",
        "刑事调解书",
        "执行证书",
        "仲裁裁决书",
        "民事裁定书",
    ]

    # 页码与页脚噪声（避免混入“执行依据主文”）
    _PAGE_NUMBER_CHARS = r"0-9零一二三四五六七八九十百千万〇○O"
    PAGE_NOISE_PATTERNS = (
        re.compile(
            rf"第\s*[{_PAGE_NUMBER_CHARS}]{{1,6}}\s*页[／/|｜丨~～\-\s]*共\s*[{_PAGE_NUMBER_CHARS}]{{1,6}}\s*页",
            re.IGNORECASE,
        ),
        re.compile(
            rf"共\s*[{_PAGE_NUMBER_CHARS}]{{1,6}}\s*页[／/|｜丨~～\-\s]*第\s*[{_PAGE_NUMBER_CHARS}]{{1,6}}\s*页",
            re.IGNORECASE,
        ),
        re.compile(r"page\s*\d+\s*(?:/|of)\s*\d+", re.IGNORECASE),
    )
    PAGE_NOISE_LITERALS = ("本页无正文", "此页无正文")

    # Ollama prompt
    OLLAMA_EXTRACTION_PROMPT = """你是一个法律文书解析助手。请从以下裁判文书文本中提取信息，并以JSON格式返回：

1. 案号：如 "(2024)粤0606民初34475号" 或 "（2025）粤0606民初38361号"
2. 文书名称：如 "民事判决书"、"民事调解书"、"执行证书" 等
3. 执行依据主文：从"判决如下："或"自愿达成如下协议："开始，到"如不服本判决"、"本调解书生效后"、"审判员"等关键词之前的判决/调解内容

请直接返回JSON，不要有其他内容：
```json
{{
    "案号": "提取到的案号，如果没有则填null",
    "文书名称": "提取到的文书名称，如民事判决书",
    "执行依据主文": "提取到的判决/调解主文内容"
}}
```

以下是文书文本：
"""

    def extract(self, file_path: str) -> ExtractionResult:
        """
        从PDF中提取案号、文书名称、执行依据主文

        先使用正则表达式提取，失败后使用Ollama兜底。

        Args:
            file_path: PDF文件路径

        Returns:
            ExtractionResult，包含案号、文书名称和主文内容

        Raises:
            BusinessException: 无法解析文书内容（正则和Ollama都失败）
        """
        from apps.document_recognition.services.text_extraction_service import TextExtractionService

        logger.info("开始解析裁判文书: %s", file_path)

        # 使用现有的 TextExtractionService 提取文本，设置较大的字数限制
        extraction_service = TextExtractionService(text_limit=50000, max_pages=None)
        result = extraction_service.extract_text(file_path)

        if not result.success or not result.text:
            logger.error("PDF文本提取失败: %s", file_path)
            raise BusinessException(
                message="无法解析文书内容，请手动输入执行依据主文",
                code="JUDGMENT_EXTRACT_FAILED",
            )

        text = self._sanitize_extracted_text(result.text)
        logger.info("PDF文本提取成功，清洗后字数: %d，提取方式: %s", len(text), result.extraction_method)

        # 提取案号（常见格式：括号年号省市代码类型序号号，如 (2024)粤0605民初3356号）
        case_number = self._extract_case_number(text)

        # 提取文书名称
        document_name = self._extract_document_name(text)

        # 提取执行依据主文
        content = self._extract_main_text(text)

        # 如果正则提取失败，尝试Ollama兜底
        if not content:
            logger.warning("正则提取执行依据主文失败，尝试使用Ollama兜底...")
            ollama_result = self._extract_with_ollama(text)
            if ollama_result:
                case_number = ollama_result.number or case_number
                document_name = ollama_result.document_name or document_name
                content = ollama_result.content

        if not content:
            logger.error("未找到判决/调解主文: %s", file_path)
            raise BusinessException(
                message="无法解析文书内容，请手动输入执行依据主文",
                code="JUDGMENT_KEYWORD_NOT_FOUND",
            )

        return ExtractionResult(
            number=case_number,
            document_name=document_name,
            content=self._sanitize_extracted_text(content),
        )

    def _extract_with_ollama(self, text: str) -> ExtractionResult | None:
        """
        使用Ollama大模型提取信息（兜底方案）

        Args:
            text: PDF提取的文本

        Returns:
            ExtractionResult 或 None（Ollama不可用或失败）
        """
        try:
            from apps.core.llm.backends.ollama import OllamaBackend

            backend = OllamaBackend()
            if not backend.is_available():
                logger.warning("Ollama后端不可用，跳过Ollama兜底")
                return None

            messages = [{"role": "user", "content": self.OLLAMA_EXTRACTION_PROMPT + text[:15000]}]

            logger.info("开始调用Ollama进行信息提取...")
            response = backend.chat(messages=messages, temperature=0.3, max_tokens=4000, timeout=60.0)

            content = response.content.strip()

            # 尝试解析JSON
            # 去掉可能的markdown代码块
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            data = json.loads(content.strip())

            result = ExtractionResult(
                number=data.get("案号") or data.get("number"),
                document_name=data.get("文书名称") or data.get("document_name"),
                content=self._sanitize_extracted_text(data.get("执行依据主文") or data.get("content")),
            )

            logger.info(
                "Ollama提取成功: 案号=%s, 文书名称=%s, 主文长度=%d",
                result.number,
                result.document_name,
                len(result.content) if result.content else 0,
            )

            return result

        except Exception as e:
            logger.warning("Ollama兜底失败: %s", str(e))
            return None

    def _extract_case_number(self, text: str) -> str | None:
        """从文本中提取案号"""
        # 常见的案号格式：(2024)粤0605民初3356号、(2024)穗仲案字第1234号、(2024)佛南海区调字第123号等
        # 注意：PDF中可能有中文括号（）（用\\uFF0F\\uFF09表示）或英文括号()
        patterns = [
            # 标准民初案号：(2025)粤0606民初38361号
            r"[（(]\s*[0-9]{1,4}\s*[）)][省市]?[A-Z]{2,6}[0-9]+[民行刑执调仲][初字][0-9]+号",
            # 带地区简称的案号
            r"[（(]\s*[0-9]{1,4}\s*[）)][省市]?[\u4e00-\u9fa5]+[0-9]+[民行刑执调仲][初字][0-9]+号",
            # 仲裁案号
            r"[（(]\s*[0-9]{1,4}\s*[）)][省市]?[\u4e00-\u9fa5]+仲案字第[0-9]+号",
            # 调解案号
            r"[（(]\s*[0-9]{1,4}\s*[）)][省市]?[\u4e00-\u9fa5]+调字第[0-9]+号",
            r"[（(]\s*[0-9]{1,4}\s*[）)][省市]?[\u4e00-\u9fa5]+调确字第[0-9]+号",
            # 执行移转案号
            r"[（(]\s*[0-9]{1,4}\s*[）)][省市]?[\u4e00-\u9fa5]+执移字第[0-9]+号",
            # 简易案号（无括号）
            r"[\u4e00-\u9fa5]+[民行刑执调仲][初确字][0-9]+号",
            # 纯括号开头案号（更通用）- 支持中英文括号
            r"[（(][0-9]{4}[）)][^\s，。,，。（）(（）)]+号",
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                case_number = match.group()
                # 过滤掉明显不是案号的匹配
                if len(case_number) > 5 and "判决" not in case_number and "调解" not in case_number:
                    logger.info("提取到案号: %s", case_number)
                    return case_number

        # 如果正则没找到，尝试在"案号"关键词附近查找
        case_number_pattern = r"案号[：:\s]*[（(]([^）)]+)[）)]|案号[：:\s]*\(([^)]+)\)"
        match = re.search(case_number_pattern, text)
        if match:
            for group in match.groups():
                if group:
                    logger.info("从'案号'关键词提取到案号: %s", group)
                    return group

        logger.warning("未提取到案号")
        return None

    def _extract_document_name(self, text: str) -> str | None:
        """从文本中提取文书名称"""
        for keyword in self.DOCUMENT_NAME_KEYWORDS:
            if keyword in text:
                logger.info("提取到文书名称: %s", keyword)
                return keyword

        logger.warning("未提取到文书名称")
        return None

    def _extract_main_text(self, text: str) -> str | None:
        """提取执行依据主文"""
        for keyword in self.JUDGMENT_KEYWORDS:
            if keyword in text:
                # 找到关键词，提取之后的内容
                main_text = text.split(keyword, 1)[1]

                # 查找截止关键词
                for end_keyword in self.END_KEYWORDS:
                    if end_keyword in main_text:
                        # 在截止关键词处截断
                        main_text = main_text.split(end_keyword)[0]
                        logger.info("在'%s'处截断，提取主文长度: %d", end_keyword, len(main_text))
                        break

                cleaned = self._sanitize_extracted_text(main_text)
                logger.info("提取主文长度: %d", len(cleaned))
                return cleaned

        return None

    def _sanitize_extracted_text(self, text: str | None) -> str:
        """清洗提取文本中的常见噪声（页码、页脚等）。"""
        if not text:
            return ""

        cleaned = text
        for pattern in self.PAGE_NOISE_PATTERNS:
            cleaned = pattern.sub("", cleaned)
        for literal in self.PAGE_NOISE_LITERALS:
            cleaned = cleaned.replace(literal, "")

        # OCR/PDF混排下可能引入多余空行，做轻量归一化
        cleaned = re.sub(r"\n{2,}", "\n", cleaned)
        return cleaned.strip()
