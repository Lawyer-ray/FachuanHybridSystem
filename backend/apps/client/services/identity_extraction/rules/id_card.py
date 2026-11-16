"""身份证/法代身份证规则提取（纯函数）。"""

from __future__ import annotations

import re
from typing import Any

from ..text_cleaning import _normalize_ocr_text, _prepare_text_for_llm
from ..validators import _validate_id_number
from .confidence import _compute_id_card_field_confidence
from .narrative import _NARRATIVE_PHONE_RE, _extract_narrative_fields


def _extract_id_number_candidates(text: str) -> list[str]:
    """提取全部 18 位身份证号候选（按出现顺序），供校验位评分选优。"""
    return [m.group(1).upper() for m in re.finditer(r"(?<!\d)(\d{17}[\dXx])(?!\d)", text)]


def _select_best_id_number(text: str) -> tuple[str | None, bool]:
    """从候选中选校验位通过者；无候选返回 (None, False)。"""
    candidates = _extract_id_number_candidates(text)
    if not candidates:
        return None, False
    for candidate in candidates:
        if _validate_id_number(candidate):
            return candidate, True
    return candidates[0], False


def _extract_id_number(text: str) -> str | None:
    match = re.search(r"(?<!\d)(\d{17}[\dXx])(?!\d)", text)
    if not match:
        return None
    return match.group(1).upper()


def _extract_name(lines: list[str]) -> str | None:
    for line in lines:
        match = re.search(r"姓名[:：]?([一-龥·]{2,20})", line)
        if match:
            return match.group(1)
    return None


def _extract_gender(lines: list[str]) -> str | None:
    for line in lines:
        match = re.search(r"性别[:：]?([男女])", line)
        if match:
            return match.group(1)
    return None


def _extract_ethnicity(lines: list[str]) -> str | None:
    for line in lines:
        match = re.search(r"民族[:：]?([一-龥]{1,8})", line)
        if match:
            return match.group(1)
    return None


def _extract_birth_date(text: str, id_number: str | None) -> str | None:
    # 优先取“出生”行
    match = re.search(r"出生[:：]?\s*(\d{4})\D(\d{1,2})\D(\d{1,2})", text)
    if match:
        return _format_date_parts(match.group(1), match.group(2), match.group(3))

    # 兜底：身份证号中解析出生日期（第7-14位）
    if id_number and len(id_number) >= 14 and id_number[:17].isdigit():
        year, month, day = id_number[6:10], id_number[10:12], id_number[12:14]
        return _format_date_parts(year, month, day)

    return None


def _extract_expiry_date(lines: list[str]) -> str | None:
    """从 OCR 文本行中提取证件到期日。

    身份证的「有效期限」是**起止区间**（如 ``2025.11.07-2045.11.07``），到期日是区间末日。

    历史实现的 bug（2026-11-06 实测）：区间正则匹配失败时直接落到「单日期」分支，
    取到的是起始日（签发日），导致 2045 年到期的证件被判成 2025 年已过期。
    触发场景：``年月日`` 格式（``2025年11月07日至2045年11月07日``）、OCR 丢分隔符
    （``2025.11.072045.11.07``）、OCR 把区间拆成两行。

    修复要点：
    1. 先把相邻行拼成候选窗口再匹配，消除 OCR 断行影响；
    2. 区间锚点兼容 ``- ~ 至 到 — –`` 以及「年月日」「./-」混排；
    3. 同一窗口出现 **多个日期** 时一律取最后一个（到期日在后），只有在明确
       出现「有效期至/至」且只有一个日期时才当作到期日，其余单日期一律不采信，
       避免再把签发日当到期日。
    """
    # 日期：兼容 2025.11.07 / 2025-11-07 / 2025/11/07 / 2025年11月07日；
    # 末尾可选的「日」必须吃掉，否则「2025年11月07日至2045年...」里的「日」
    # 会挡住后面的分隔符，导致区间匹配失败。
    date_pat = r"(\d{4})[.\-/年]\s*(\d{1,2})[.\-/月]\s*(\d{1,2})\s*日?"
    # 区间：起始日 + 分隔符 + (结束日 | 长期)
    range_re = re.compile(date_pat + r"\s*(?:[-~至到—–]|起至)\s*(长期|" + date_pat + r")")
    marker_re = re.compile(r"有效期(?:限)?至[:：]?\s*" + date_pat)

    def _next_line(lines: list[str], idx: int) -> str:
        return lines[idx + 1] if idx + 1 < len(lines) else ""

    for i, line in enumerate(lines):
        window = line
        # 提前拼接下一行：OCR 常把「2025.11.07-」和「2045.11.07」拆成两行
        nxt = _next_line(lines, i)
        if nxt:
            window = f"{line} {nxt}"

        if "长期" in window and ("有效" in window or "期限" in window):
            return "2099-12-31"

        range_match = range_re.search(window)
        if range_match:
            end_group = range_match.group(4)
            if end_group == "长期":
                return "2099-12-31"
            return _format_date_parts(
                range_match.group(5),
                range_match.group(6),
                range_match.group(7),
            )

        # 明确「有效期至 X」且窗口内只有这一个日期时才采信
        marker_match = marker_re.search(window)
        if marker_match and not range_re.search(window):
            all_dates = re.findall(date_pat, window)
            if len(all_dates) == 1:
                return _format_date_parts(
                    marker_match.group(1),
                    marker_match.group(2),
                    marker_match.group(3),
                )

        # 侜底：OCR 把区间分隔符整个吃掉（如 2025.11.072045.11.07）。
        # 仅在「有效期」字样附近出现 **两个及以上** 完整日期时，取最后一个作到期日。
        if "有效" in window or "期限" in window:
            compact = re.findall(r"(\d{4})[.\-/年](\d{1,2})[.\-/月](\d{1,2})", window)
            if len(compact) >= 2:
                y, m, d = compact[-1]
                return _format_date_parts(y, m, d)

    return None


def _extract_address(lines: list[str]) -> str | None:
    address_parts: list[str] = []
    collecting = False
    stop_keywords = ("公民身份号码", "有效期限", "签发机关", "机关")

    for line in lines:
        if any(keyword in line for keyword in stop_keywords):
            break

        if line.startswith("住址"):
            collecting = True
            tail = line.replace("住址", "", 1).strip(" :：")
            if tail:
                address_parts.append(tail)
            continue

        if collecting:
            if re.fullmatch(r"\d{17}[\dXx]", line):
                break
            address_parts.append(line)

    if not address_parts:
        return None

    return "".join(address_parts)


def _format_date_parts(year: str, month: str, day: str) -> str | None:
    try:
        y = int(year)
        m = int(month)
        d = int(day)
    except ValueError:
        return None
    if y <= 1900 or m <= 0 or d <= 0 or m > 12 or d > 31:
        return None
    return f"{y:04d}-{m:02d}-{d:02d}"


def _extract_id_card_fields(raw_text: str) -> dict[str, Any]:
    """身份证卡路径：卡片版式优先，未命中字段回退叙述式提取。"""
    text = _prepare_text_for_llm(_normalize_ocr_text(raw_text))
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    merged = "\n".join(lines)

    id_number, _id_verified = _select_best_id_number(merged)
    name = _extract_name(lines)
    gender = _extract_gender(lines)
    ethnicity = _extract_ethnicity(lines)
    address = _extract_address(lines)
    expiry_date = _extract_expiry_date(lines)
    birth_date = _extract_birth_date(merged, id_number)
    phone = _NARRATIVE_PHONE_RE.search(text.replace("\n", ""))

    # 卡片版式未命中的字段，回退叙述式提取（判决书/起诉状文本）
    narrative_used = False
    if not any([name, gender, ethnicity, address]):
        narrative = _extract_narrative_fields(text)
        name = narrative["name"]
        gender = narrative["gender"]
        ethnicity = narrative["ethnicity"]
        address = narrative["address"]
        narrative_used = any([name, gender, ethnicity, address])

    extracted: dict[str, Any] = {
        "name": name,
        "id_number": id_number,
        "address": address or "",
        "expiry_date": expiry_date,
        "gender": gender,
        "ethnicity": ethnicity,
        "birth_date": birth_date,
        "phone": phone.group(1) if phone else "",
    }
    extracted["field_confidence"] = _compute_id_card_field_confidence(extracted, narrative_used)

    return extracted
