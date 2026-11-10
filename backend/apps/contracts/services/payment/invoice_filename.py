"""数电发票附件的**文件名**元数据：号码 / 购买方 / 律所项目号。

律所邮件里的发票附件几乎都由税务平台自动命名，名字里已经带齐了挂账要用的三件东西：

    dzfp_26442000012915552076_某某（个人）_2025GZM0001-开票人.pdf  # privacy-allow 虚构样例，非真实项目号
    └┬─┘ └──────────┬─────────┘ └───┬────┘ └────┬─────┘ └─┬─┘
    前缀        20 位发票号码      购买方      项目号    开票人

拿到这三项比打开 PDF 便宜得多：邮件同步时就能先把发票挂到案件上，不必等识别链路
跑完。真实版式还有不少变体（`发票_<买方>_<日期>开具.pdf`、漏写项目号、买方名含
全角括号），所以每条规则都**独立兜底**：抽不到就是空串，绝不让一个解析失败挡住
整批邮件同步——文件名解析挂了可以退回读 PDF，抛异常会把整封邮件的附件一起废掉。

本模块只做 `str -> dict` 的纯推导：无 IO、无 DB、无模型，可直接单测。

**不含税号**：数电票文件名里不会出现统一社会信用代码，本模块也不会去猜身份证/税号，
买的方若是自然人只保留名字本体（`（个人）` 标注由 `mask_personal_name` 去掉）。
"""

from __future__ import annotations

import re

__all__ = ["mask_personal_name", "parse_invoice_filename"]

#: 号码边界一律写「前后不是数字」而不能用 `\b`：附件名里号码前后紧贴下划线
#: （`dzfp_26442000012915552076_…`），而下划线是单词字符，`\b` 在那里不会命中。
_INVOICE_NUMBER_STRICT = re.compile(r"(?<!\d)(\d{20})(?!\d)")
_INVOICE_NUMBER_FALLBACK = re.compile(r"(?<!\d)(\d{8,12})(?!\d)")

#: 形如开票日期的 8 位数字（`20260623`）。发票号码只有 8 位（旧版）与 20 位（数电票）
#: 两种，而旧版版式会把日期直接写进文件名（`发票_<买方>_20260623开具.pdf`），
#: 不排除它就会把日期当成发票号——去重键随即被污染，同一张票重发一次就多一条待认领。
_DATE_LIKE = re.compile(r"^(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])$")

#: 律所项目号：2025GZM0001（年份 4 位 + GZ + 1 位字母 + 4 位序号）。  # privacy-allow 虚构样例，非真实项目号
#: 同样不能用 `\b`：项目号后紧跟 `-开票人` 前的下划线/汉字时 `\b` 会失效。
_PROJECT_CODE = re.compile(r"(?<![0-9A-Za-z])(\d{4}GZ[A-Z]\d{4})(?![0-9A-Za-z])")

#: 开票人后缀：`2025GZM0001-开票人` 里的 `-开票人`，不属于购买方。  # privacy-allow 虚构样例，非真实项目号
_ISSUER_SUFFIX = re.compile(r"-[^-]*$")

#: 自然人标注。数电票把「张三（个人）」写成带标注的形式，标注不是名字的一部分。
_PERSONAL_MARKERS: tuple[str, ...] = ("（个人）", "(个人)", "（自然人）", "(自然人)")


def parse_invoice_filename(filename: str) -> dict[str, str]:
    """从数电票附件名抽号码/购买方/项目号。纯函数，失败返空串，绝不抛异常。"""
    result = {"invoice_number": "", "buyer_name": "", "project_code": ""}
    if not filename:
        return result

    stem = _strip_extension(filename)
    if not stem:
        return result

    number_match = _INVOICE_NUMBER_STRICT.search(stem)
    if number_match:
        result["invoice_number"] = number_match.group(1)
    else:
        # 兜底 8–12 位：逐个候选跳过"长得像日期"的，取第一个真正的号码
        for fallback in _INVOICE_NUMBER_FALLBACK.finditer(stem):
            candidate = fallback.group(1)
            if not _DATE_LIKE.match(candidate):
                result["invoice_number"] = candidate
                break

    project_match = _PROJECT_CODE.search(stem)
    if project_match:
        result["project_code"] = project_match.group(1)

    result["buyer_name"] = mask_personal_name(_extract_buyer_name(stem))
    return result


def mask_personal_name(name: str) -> str:
    """`张三（个人）` -> `张三`。只去掉"（个人）"/"(个人)"/"（自然人）"标注，人名本身保留。公司名原样返回。空串返回空串。"""
    masked = name.strip()
    for marker in _PERSONAL_MARKERS:
        masked = masked.replace(marker, "")
    return masked.strip()


def _strip_extension(filename: str) -> str:
    """去掉扩展名。用 rsplit 而不是 Path.stem：附件名里可能带点（`2025GZM0001-某某律师.pdf` 之外的 `.pdf.pdf`）。"""  # privacy-allow 虚构样例，非真实项目号
    stem = filename.strip().rsplit("/", 1)[-1]
    if "." in stem:
        stem = stem.rsplit(".", 1)[0]
    return stem.strip()


def _extract_buyer_name(stem: str) -> str:
    """按 `_` 分段取购买方：`dzfp_<号码>_<买方>_<项目号>-<开票人>` 取 index 2，`发票_<买方>_…` 取 index 1。"""
    segments = [segment.strip() for segment in stem.split("_")]
    if len(segments) < 3:
        # `发票_<买方>_<日期>开具` 至少三段；不足三段时没有可靠的购买方位置，宁可留空
        return ""

    buyer_index = 2 if segments[0].lower() == "dzfp" else 1
    if buyer_index >= len(segments):
        return ""

    buyer = segments[buyer_index]
    if _PROJECT_CODE.search(buyer):
        # 买方段里已经含项目号，说明该结构的字段位置与预期不同，不硬猜
        return ""
    return _ISSUER_SUFFIX.sub("", buyer).strip()
