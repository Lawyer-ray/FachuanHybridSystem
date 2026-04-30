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
        "裁定如下：",
        "裁定如下:",
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
        "如不服本裁定",
        "如不服本裁定书",
        "上诉期限",
        "本调解书生效后",
        "本裁定生效后",
        "本判决为终审判决",  # 二审终审判决截止
        "驳回上诉，维持原判",  # 二审维持原判截止
        "案件受理费",  # 诉讼费负担不属于执行依据主文
        "审判长",
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

    # 页码与页脚噪声（避免混入"执行依据主文"）
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
2. 文书名称：如 "民事判决书"、"民事调解书"、"民事裁定书"、"执行证书" 等
3. 执行依据主文：从"判决如下："、"裁定如下："或"自愿达成如下协议："开始，到"如不服本判决"、"如不服本裁定"、"本调解书生效后"、"审判员"等关键词之前的判决/调解/裁定内容

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

    # 裁判文书提取的最大字符数（判决主文通常在文书末尾，必须读取全文）
    _MAX_EXTRACTION_CHARS = 200_000

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
        logger.info("开始解析裁判文书: %s", file_path)

        text, extraction_method = self._extract_full_text(file_path)

        if not text:
            logger.error("PDF文本提取失败: %s", file_path)
            raise BusinessException(
                message="无法解析文书内容，请手动输入执行依据主文",
                code="JUDGMENT_EXTRACT_FAILED",
            )

        logger.info("PDF文本提取成功，清洗后字数: %d，提取方式: %s", len(text), extraction_method)

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

    def _extract_full_text(self, file_path: str) -> tuple[str, str]:
        """
        从PDF提取全文，不受通用服务的 MAX_TEXT_LIMIT 限制。

        裁判文书的"判决如下"通常在文书末尾（最后一两页），
        必须读取全部页面才能保证关键词可被匹配到。
        TextExtractionService 的 MAX_TEXT_LIMIT 默认仅 10000 字符，
        对49页判决书只能读取前约13页，导致末尾判决主文丢失。

        策略：先尝试 PyMuPDF 直接提取，如果文本为空则降级到 OCR。

        Args:
            file_path: PDF文件路径

        Returns:
            (清洗后文本, 提取方式) 元组
        """
        import fitz

        # 1. 先尝试 PyMuPDF 直接提取全文
        raw_parts: list[str] = []
        try:
            with fitz.open(file_path) as doc:
                for i in range(doc.page_count):
                    page = doc.load_page(i)
                    t = page.get_text()
                    if t:
                        raw_parts.append(t)
                    if sum(len(x) for x in raw_parts) >= self._MAX_EXTRACTION_CHARS:
                        break
        except Exception as e:
            logger.warning("PyMuPDF直接提取失败: %s", e)

        if raw_parts:
            text = self._sanitize_extracted_text("".join(raw_parts))
            return text, "pdf_direct"

        # 2. 直接提取为空，降级到 OCR
        logger.info("PDF直接提取为空，降级到OCR: %s", file_path)
        from apps.document_recognition.services.text_extraction_service import TextExtractionService

        ocr_service = TextExtractionService(text_limit=self._MAX_EXTRACTION_CHARS, max_pages=None)
        result = ocr_service.extract_text(file_path)
        if result.success and result.text:
            return self._sanitize_extracted_text(result.text), result.extraction_method

        return "", ""

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
        # PDF排版可能导致案号中间出现空格，如"（2026）黔01 民终1960 号"
        patterns = [
            # 标准法院案号（含二审民终/民终等）：(2025)粤0606民初38361号、(2026)黔01民终1960号
            # 带 -1 后缀如：粤0605 民初10838-1 号
            r"[（(]\s*[0-9]{1,4}\s*[）)]\s*[省市]?\s*[A-Za-z\u4e00-\u9fa5]*\s*[0-9]+\s*[民行刑执调仲]\s*[初终字确]\s*[0-9]+(?:-\s*[0-9]+)?\s*号",
            # 带地区简称的案号
            r"[（(]\s*[0-9]{1,4}\s*[）)]\s*[省市]?\s*[\u4e00-\u9fa5]+\s*[0-9]+\s*[民行刑执调仲]\s*[初终字确]\s*[0-9]+(?:-\s*[0-9]+)?\s*号",
            # 仲裁案号
            r"[（(]\s*[0-9]{1,4}\s*[）)]\s*[省市]?\s*[\u4e00-\u9fa5]+\s*仲案字第\s*[0-9]+\s*号",
            # 调解案号
            r"[（(]\s*[0-9]{1,4}\s*[）)]\s*[省市]?\s*[\u4e00-\u9fa5]+\s*调字第\s*[0-9]+\s*号",
            r"[（(]\s*[0-9]{1,4}\s*[）)]\s*[省市]?\s*[\u4e00-\u9fa5]+\s*调确字第\s*[0-9]+\s*号",
            # 执行移转案号
            r"[（(]\s*[0-9]{1,4}\s*[）)]\s*[省市]?\s*[\u4e00-\u9fa5]+\s*执移字第\s*[0-9]+\s*号",
            # 简易案号（无括号）
            r"[\u4e00-\u9fa5]+\s*[民行刑执调仲]\s*[初终确字]\s*[0-9]+(?:-\s*[0-9]+)?\s*号",
            # 纯括号开头案号（更通用）- 支持中英文括号
            r"[（(]\s*[0-9]{4}\s*[）)]\s*[^\s，。,，。（）(（）)]+号",
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                case_number = match.group()
                # 清理案号中的多余空格
                case_number = re.sub(r"\s+", "", case_number)
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
        # PDF 竖排排版可能导致"审判长"变成"审\n判\n长"，
        # 先生成一份去除换行的归一化文本用于关键词匹配
        normalized_text = re.sub(r"\s+", "", text)

        for keyword in self.JUDGMENT_KEYWORDS:
            normalized_keyword = re.sub(r"\s+", "", keyword)
            if normalized_keyword in normalized_text:
                # 在归一化文本中定位关键词位置，映射回原文进行切割
                norm_idx = normalized_text.index(normalized_keyword)
                # 计算原文中关键词起始位置（逐字符计数非空白字符）
                orig_start = self._map_normalized_to_original(text, norm_idx)
                # 关键词在原文中跨越的长度
                orig_end = orig_start + len(keyword)
                main_text = text[orig_end:]

                # 在归一化文本中查找最早出现的截止关键词
                normalized_remaining = normalized_text[norm_idx + len(normalized_keyword) :]
                earliest_end_pos: int | None = None
                earliest_end_keyword: str | None = None

                for end_keyword in self.END_KEYWORDS:
                    normalized_end = re.sub(r"\s+", "", end_keyword)
                    if normalized_end in normalized_remaining:
                        end_norm_idx = normalized_remaining.index(normalized_end)
                        if earliest_end_pos is None or end_norm_idx < earliest_end_pos:
                            earliest_end_pos = end_norm_idx
                            earliest_end_keyword = end_keyword

                if earliest_end_pos is not None:
                    # 映射截止位置回原文
                    orig_end_pos = self._map_normalized_to_original(main_text, earliest_end_pos)
                    main_text = main_text[:orig_end_pos]
                    logger.info("在'%s'处截断，提取主文长度: %d", earliest_end_keyword, len(main_text))

                cleaned = self._sanitize_extracted_text(main_text)
                logger.info("提取主文长度: %d", len(cleaned))
                return cleaned

        return None

    @staticmethod
    def _map_normalized_to_original(original: str, normalized_index: int) -> int:
        """
        将归一化文本（去除空白后）的索引映射回原文索引。

        Args:
            original: 原始文本
            normalized_index: 归一化文本中的字符位置

        Returns:
            原始文本中对应的位置
        """
        non_ws_count = 0
        for i, ch in enumerate(original):
            if ch.isspace():
                continue
            if non_ws_count == normalized_index:
                return i
            non_ws_count += 1
        return len(original)

    def _sanitize_extracted_text(self, text: str | None) -> str:
        """清洗提取文本中的常见噪声（页码、页脚等）。"""
        if not text:
            return ""

        # 统一换行符
        cleaned = text.replace("\r\n", "\n").replace("\r", "\n")

        # PDF 每页开头的纯数字页码行替换为换行（保留段落分隔）
        cleaned = re.sub(r"\n\d{1,4}\n", "\n", cleaned)

        # 其他噪声模式直接删除
        for pattern in self.PAGE_NOISE_PATTERNS:
            cleaned = pattern.sub("", cleaned)
        for literal in self.PAGE_NOISE_LITERALS:
            cleaned = cleaned.replace(literal, "")

        # OCR/PDF混排下可能引入多余空行，做轻量归一化
        cleaned = re.sub(r"\n{2,}", "\n", cleaned)

        # 合并PDF排版导致的句子内换行：句末标点后的换行保留，其余合并
        # 如 "9991\n号" → "9991号"，"诉讼请求。\n如果" → "诉讼请求。\n如果"
        cleaned = re.sub(r"(?<![。，；：！？、）)》」』」])\n", "", cleaned)

        # 去除末尾不完整的行（截断残留，如"一审"等无标点结尾的碎片）
        cleaned = re.sub(r"\n[^\n。，；：！？、）)]+$", "", cleaned)

        return cleaned.strip()
