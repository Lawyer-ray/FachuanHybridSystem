"""案号提取 Mixin

确定性提取（三层防线，不依赖 LLM）：
1. 括号全半角归一化——OCR 把「（2024）」识别成「(2024）」是高频错，
   归一化后统一按全角匹配；
2. 全量枚举文中案号而非取首个——同一文书常含引用案号；
3. 位置 + 引用句式加权——文书自身案号紧邻标题（文首），而
   「根据/依据（案号）裁定书/判决书…」中的是被引用案号，降权处理。

Requirements: 4.3
"""

import logging
import re

logger = logging.getLogger("apps.document_recognition")

# 归一化后的统一模式（全角括号对为主，无括号兜底）
CASE_NUMBER_PATTERNS = [
    r"（(\d{4})）([^\s（）]{2,20}?)(\d+)号",
    r"(\d{4})([^\d\s（][^\s（）]{1,19}?)(\d+)号",
]

# 引用句式特征：案号前有「根据/依据/依照」且/或其后紧跟裁判文书名
_REFERENCE_PREFIX_RE = re.compile(r"根据|依据|依照")
_REFERENCE_SUFFIX_RE = re.compile(r"裁定书|判决书|调解书|决定书|通知书|支付令")


class CaseNumberMixin:
    """案号提取 Mixin（确定性，位置与引用句式加权择优）"""

    def _extract_case_number_by_regex(self, text: str) -> str | None:
        """全量枚举文中案号并加权取最优，返回全角归一化案号。"""
        if not text:
            return None
        normalized = text.replace("(", "（").replace(")", "）")
        best: tuple[int, int, str] | None = None
        seen_spans: list[tuple[int, int]] = []
        for pattern in CASE_NUMBER_PATTERNS:
            for match in re.finditer(pattern, normalized):
                span = match.span()
                # 跨模式去重：已被更严模式覆盖的区间不再计分
                if any(s <= span[0] < e for s, e in seen_spans):
                    continue
                seen_spans.append(span)
                year, court_type, seq = match.group(1), match.group(2), match.group(3)
                case_number = f"（{year}）{court_type}{seq}号"
                score = self._score_case_number_match(normalized, span[0], span[1])
                logger.debug("案号候选: %s (位置=%d, 得分=%d)", case_number, span[0], score)
                # 得分高者优先；同分取位置靠前（贴近标题）
                if best is None or (score, -span[0]) > (best[0], -best[1]):
                    best = (score, span[0], case_number)
        if best is None:
            logger.debug("正则未能提取到案号")
            return None
        score, pos, case_number = best
        logger.info("正则提取到案号: %s (位置=%d, 得分=%d)", case_number, pos, score)
        return self._normalize_case_number(case_number)

    @staticmethod
    def _score_case_number_match(text: str, start: int, end: int) -> int:
        """案号候选打分：文首位置加分，「根据…裁定书」引用句式降权。"""
        prefix = text[max(0, start - 12) : start]
        suffix = text[end : end + 12]
        score = max(0, 60 - start)
        if _REFERENCE_PREFIX_RE.search(prefix):
            score -= 40
            if _REFERENCE_SUFFIX_RE.search(suffix):
                score -= 60
        elif _REFERENCE_SUFFIX_RE.search(suffix):
            score -= 15
        return score

    def _normalize_case_number(self, case_number: str) -> str:
        """标准化案号格式（统一全角括号）"""
        if not case_number:
            return case_number
        case_number = case_number.strip()
        case_number = case_number.replace("（", "(").replace("）", ")")
        no_bracket_pattern = r"^(\d{4})([^\d\(\)])"
        match = re.match(no_bracket_pattern, case_number)
        if match:
            year = match.group(1)
            rest = case_number[4:]
            case_number = f"({year}){rest}"
        case_number = case_number.replace("(", "（").replace(")", "）")
        return case_number
