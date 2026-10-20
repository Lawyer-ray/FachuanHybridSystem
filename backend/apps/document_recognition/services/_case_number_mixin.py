"""案号提取 Mixin

确定性提取（三层防线，不依赖 LLM）：
1. 括号全半角归一化——OCR 把「（2024）」识别成「(2024）」是高频错，
   归一化后统一按全角匹配；机关字号的 〔〕 同样归一（[ ] / ［ ］ → 〔 〕）；
2. 全量枚举文中案号而非取首个——同一文书常含引用案号；
3. 位置 + 句式加权——文书自身案号紧邻标题（文首），「案号」标签后的加分，
   「根据/依据（案号）裁定书/判决书…」中的是被引用案号，降权处理。

两种结构的案号分开匹配、分开重拼：
- 法院案号「（年份）法院代字…号」：年份在前，括号为（）；
- 机关字号「机关代字〔年份〕第N号」（仲裁委 / 行政机关）：代字在年份之前、括号为 〔〕。
  代字与前文（标题）之间常无任何分隔，只能以「案号/文号」标签、标点或标题尾字「书」
  为左界；若按法院结构重拼会得到「（2026）〕第300号」这类残缺值。

Requirements: 4.3
"""

import logging
import re
from collections.abc import Iterator

logger = logging.getLogger("apps.document_recognition")

# 法院案号（归一化后全角括号对为主，无括号兜底）；字符类排除 〔〕，机关字号的年份
# 绝不能被兜底模式按法院结构重拼
CASE_NUMBER_PATTERNS = [
    r"（(\d{4})）([^\s（）〔〕]{2,20}?)(\d+)号",
    r"(\d{4})([^\d\s（）〔〕][^\s（）〔〕]{1,19}?)(\d+)号",
]

# 机关字号：左界（文首 / 标点 / 「案号」「文号」标签 / 标题尾字「书」）+ 代字 + 〔年份〕+ 第?N号。
# 代字最长 12 字；左界不消费进代字（group 1 才是代字起点）
AGENCY_CASE_NUMBER_PATTERN = (
    r"(?:^|[\s，。；：、]|案号|文号|书)([\u4e00-\u9fa5A-Za-z0-9（）]{2,12}?)〔(\d{4})〕(第?)(\d+)号"
)

# 机关字号整体形状（归一化用）：代字 + 任一括号年份 + 第?N号
_AGENCY_FORM_RE = re.compile(r"^([^\d\s（）〔〕\[\]［］]{2,}?)[（(〔\[［](\d{4})[）)〕\]］](第?\d+号)$")

# 引用句式特征：案号前有「根据/依据/依照」且/或其后紧跟裁判文书名
_REFERENCE_PREFIX_RE = re.compile(r"根据|依据|依照")
_REFERENCE_SUFFIX_RE = re.compile(r"裁定书|判决书|调解书|决定书|通知书|支付令")
# 「案号」标签紧邻候选之前：文书自报案号的最强信号
_CASE_LABEL_PREFIX_RE = re.compile(r"案号[:：]?\s*$")
# 文号类代字（通知 / 函件 / 公告编号）：是文书自身编号而非案号
_DOC_NUMBER_CODE_RE = re.compile(r"(通知|通|函|公告)字$")


def _normalize_brackets(text: str) -> str:
    return (
        text.replace("(", "（")
        .replace(")", "）")
        .replace("[", "〔")
        .replace("]", "〕")
        .replace("［", "〔")
        .replace("］", "〕")
    )


class CaseNumberMixin:
    """案号提取 Mixin（确定性，位置与引用句式加权择优）"""

    def _extract_case_number_by_regex(self, text: str) -> str | None:
        """全量枚举文中案号并加权取最优，返回归一化案号。"""
        if not text:
            return None
        normalized = _normalize_brackets(text)
        best: tuple[int, int, str] | None = None
        seen_spans: list[tuple[int, int]] = []
        for start, end, case_number in _iter_case_number_candidates(normalized):
            # 跨模式去重：已被更严模式覆盖的区间不再计分
            if any(s <= start < e for s, e in seen_spans):
                continue
            seen_spans.append((start, end))
            score = _score_case_number_match(normalized, start, end)
            logger.debug("案号候选: %s (位置=%d, 得分=%d)", case_number, start, score)
            # 得分高者优先；同分取位置靠前（贴近标题）
            if best is None or (score, -start) > (best[0], -best[1]):
                best = (score, start, case_number)
        if best is None:
            logger.debug("正则未能提取到案号")
            return None
        score, pos, case_number = best
        logger.info("正则提取到案号: %s (位置=%d, 得分=%d)", case_number, pos, score)
        return self._normalize_case_number(case_number)

    def _normalize_case_number(self, case_number: str) -> str:
        """标准化案号格式（法院案号统一全角括号；机关字号年份括号统一 〔〕）"""
        if not case_number:
            return case_number
        case_number = case_number.strip()
        agency = _AGENCY_FORM_RE.match(case_number)
        if agency:
            return f"{agency.group(1)}〔{agency.group(2)}〕{agency.group(3)}"
        case_number = case_number.replace("（", "(").replace("）", ")")
        no_bracket_pattern = r"^(\d{4})([^\d\(\)])"
        match = re.match(no_bracket_pattern, case_number)
        if match:
            year = match.group(1)
            rest = case_number[4:]
            case_number = f"({year}){rest}"
        case_number = case_number.replace("(", "（").replace(")", "）")
        return case_number


# ↓↓ 由 CaseNumberMixin 下沉的模块级纯函数（四层架构静态方法棘轮）
def _iter_case_number_candidates(normalized: str) -> Iterator[tuple[int, int, str]]:
    """按「法院案号 → 机关字号 → 无括号兜底」顺序产出 (起点, 终点, 重拼案号)。"""
    court_pattern, fallback_pattern = CASE_NUMBER_PATTERNS
    for match in re.finditer(court_pattern, normalized):
        year, court_type, seq = match.group(1), match.group(2), match.group(3)
        yield match.start(), match.end(), f"（{year}）{court_type}{seq}号"
    for match in re.finditer(AGENCY_CASE_NUMBER_PATTERN, normalized):
        code, year, di, seq = match.group(1), match.group(2), match.group(3), match.group(4)
        yield match.start(1), match.end(), f"{code}〔{year}〕{di}{seq}号"
    for match in re.finditer(fallback_pattern, normalized):
        year, court_type, seq = match.group(1), match.group(2), match.group(3)
        yield match.start(), match.end(), f"（{year}）{court_type}{seq}号"


def _score_case_number_match(text: str, start: int, end: int) -> int:
    """案号候选打分：文首位置加分，「案号」标签加分，文号类代字与「根据…裁定书」引用句式降权。"""
    prefix = text[max(0, start - 12) : start]
    suffix = text[end : end + 12]
    score = max(0, 60 - start)
    if _CASE_LABEL_PREFIX_RE.search(prefix):
        score += 50
    if _DOC_NUMBER_CODE_RE.search(text[start:end].split("〔", 1)[0]):
        score -= 20
    if _REFERENCE_PREFIX_RE.search(prefix):
        score -= 40
        if _REFERENCE_SUFFIX_RE.search(suffix):
            score -= 60
    elif _REFERENCE_SUFFIX_RE.search(suffix):
        score -= 15
    return score
