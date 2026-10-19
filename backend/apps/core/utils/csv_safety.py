"""CSV 单元格公式注入防护（解耦 + 安全审计 2026-10-19）。

导出到 CSV 的单元格若以 ``= + - @`` 开头，Excel / WPS 打开时会当公式执行
（DDE 等外链命令可借此触发）。数据源为 LLM 从外部文书提取的文本或用户
上传文件名时不可信，写 CSV 前应逐格过 :func:`csv_safe_cell`。

取舍：对 ``-`` 开头的**纯数字**串不加引号（金额/页码等数值列大量以负号
开头，前置单引号会破坏数值类型）；其余前缀一律前置单引号。WPS/Excel 对
带引号前缀的单元格按文本处理。
"""

from __future__ import annotations

import re

_FORMULA_PREFIXES = ("=", "+", "@")
_PURE_NUMBER_RE = re.compile(r"^-?[\d.,\s%]+$")


def csv_safe_cell(value: object) -> str:
    """把任意值转为安全的 CSV 单元格文本（公式前缀转义）。"""
    text = str(value if value is not None else "")
    if not text:
        return ""
    first = text[0]
    if first in _FORMULA_PREFIXES or (first == "-" and not _PURE_NUMBER_RE.match(text)):
        return "'" + text
    return text
