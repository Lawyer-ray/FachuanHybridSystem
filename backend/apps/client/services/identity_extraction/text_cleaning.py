"""OCR 文本清洗与日志脱敏（纯函数，无 IO）。"""

from __future__ import annotations

import re

# 喂给 LLM 的 OCR 文本上限，避免噪声与超长上下文拖慢推理
_MAX_LLM_OCR_CHARS = 1800
_MAX_LLM_OCR_LINES = 80

# PII 日志脱敏：18 位身份证号（前 3 后 2 保留，中间掩码）与截断长度
_ID_NUMBER_LOG_RE = re.compile(r"\d{17}[\dXx]")
_PII_LOG_MAX_CHARS = 200

# 全角 → 半角映射（数字/字母/常见标点）
_FULLWIDTH_TRANSLATION = str.maketrans(
    "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ：，；．（）",
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz:,;.()",
)


def _sanitize_pii_for_log(text: str) -> str:
    """日志脱敏：掩码 18 位身份证号并截断（安全审计：OCR/LLM 内容含 PII 禁止明文 INFO）。"""
    masked = _ID_NUMBER_LOG_RE.sub(lambda m: f"{m.group()[:3]}{'*' * 13}{m.group()[-2:]}", text)
    return masked[:_PII_LOG_MAX_CHARS]


def _normalize_ocr_text(text: str) -> str:
    """OCR 文本归一化：全角转半角、去除中文间空格，保留换行作为字段边界信号。"""
    normalized = text.translate(_FULLWIDTH_TRANSLATION)
    # 去除行内空白（OCR 常在中英文间插入空格），保留换行
    lines = (re.sub(r"[ \t　]+", "", line) for line in normalized.splitlines())
    return "\n".join(lines)


def _looks_like_json_noise(line: str) -> bool:
    """判断是否为结构化 JSON/调试噪声行。"""
    candidate = line.strip()
    if len(candidate) < 10:
        return False

    if (candidate.startswith("{") and candidate.endswith("}")) or (
        candidate.startswith("[") and candidate.endswith("]")
    ):
        return True

    # 常见 JSON 键值模式: "key": ...
    if re.search(r'"[A-Za-z_][\w-]*"\s*:', candidate):
        return True

    json_chars = sum(1 for c in candidate if c in '{}[]":,')
    if len(candidate) >= 30 and (json_chars / len(candidate)) > 0.30:
        return True

    return False


def _is_meaningful_line(line: str) -> bool:
    """判断 OCR 行是否有信息价值。"""
    if not line:
        return False

    # 仅符号/分隔线（如 ----、====、...）直接过滤
    if re.fullmatch(r"[\W_]+", line):
        return False

    # 纯重复字符噪声（如 111111、哈哈哈哈）过滤
    if len(set(line)) == 1 and len(line) >= 4:
        return False

    # 结构化 JSON 噪声过滤
    if _looks_like_json_noise(line):
        return False

    # 过短且不含常见有效字符（数字/中文/字母）过滤
    if len(line) <= 1 and not re.search(r"[0-9A-Za-z一-鿿]", line):
        return False

    return True


def _prepare_text_for_llm(raw_text: str) -> str:
    """清洗 OCR 文本后再发送给 LLM，减少噪声与无意义上下文。"""
    # 统一换行并拆分候选行（兼容部分 OCR 用 | 作为分隔符）
    normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    candidates = re.split(r"\n+|\|", normalized)

    seen: set[str] = set()
    cleaned_lines: list[str] = []

    for part in candidates:
        # 合并中英文空白，减少 OCR 抖动导致的重复
        line = re.sub(r"\s+", "", part).strip()
        if not line:
            continue
        if not _is_meaningful_line(line):
            continue
        if line in seen:
            continue

        seen.add(line)
        cleaned_lines.append(line)

    if not cleaned_lines:
        fallback = raw_text.strip()
        return fallback[:_MAX_LLM_OCR_CHARS]

    # 行数限制
    limited_lines = cleaned_lines[:_MAX_LLM_OCR_LINES]

    # 字符总量限制
    merged: list[str] = []
    current_len = 0
    for line in limited_lines:
        add_len = len(line) + (1 if merged else 0)
        if current_len + add_len > _MAX_LLM_OCR_CHARS:
            break
        merged.append(line)
        current_len += add_len

    prepared = "\n".join(merged)
    return prepared if prepared else "\n".join(limited_lines[:10])
