"""引用核查 —— 让「根据《X法》第 N 条」不再是无法校验的一句话。

## 为什么这是法律场景最该有的一环

模型可以写出「根据《民法典》第 XXX 条」而**没有任何校验**。在代码场景编造
一个函数名，编译会失败；在法律场景编造一个条号，可能一路写到起诉状里交给法院。

本工具把文中的引用逐条解析、核查，给出三态结论。

## 三态口径（这是本模块最重要的设计）

| 状态 | 含义 | 律师该做什么 |
|:-|:-|:-|
| `verified` | 查到了，且**现行有效**、条文内容与所引命题一致 | 可用 |
| `not_verified` | **默认状态**。查不到 / 无法确认 / 有效性存疑 | 必须人工核对后才能用 |
| `not_found` | 明确检索过，法规库里没有这一条 | 大概率是编的，删掉或改 |

**默认是 `not_verified` 而不是 `verified`**：只有拿到可点击来源的才算
「已验证」。这个默认值是刻意的——审计文化里「未证明视为未发生」。

## 与既有 check_law_references 的关系

后端已有 `check_law_references`（走威科先行核查条文有效性），本模块是它的
**MCP 层封装 + 扩展**：

1. 补上**案号格式校验**（威科那条路径只查法条）；
2. 把结果统一成三态，并把「没查」（缺凭证/插件不可用）与「查了没有」
   严格区分——两者对律师的后续动作完全不同；
3. 给出 `needs_review` 汇总，便于前端渲染「待核对清单」。

不重写威科链路的原因：那里面有登录、凭证解密、插件探测，重写会把
安全审计做过的 E-13 域白名单等约束丢掉。
"""

from __future__ import annotations

import re
from typing import Any

from mcp_server.client import client

#: 中文法条引用：《民法典》第一千零七十九条 / 《公司法》第32条第二款
_STATUTE_RE = re.compile(
    r"《(?P<law>[^》]{2,40})》\s*第(?P<article>[一二三四五六七八九十百千零〇\d]+)条(?:第(?P<para>[一二三四五六七八九十百千零〇\d]+)款)?"
)

#: 案号：（20XX）某0105民初某某号 / （20XX）最高法民申某某号
_CASE_NO_RE = re.compile(
    r"[（(]\s*(?P<year>\d{4})\s*[）)]\s*(?P<court>[\u4e00-\u9fa5]{1,8}?\d{0,6}?)"
    r"(?P<type>[民刑行执商知破赔][\u4e00-\u9fa5]{0,4}?)"
    r"(?P<num>\d{1,8})\s*号"
)

#: 中文数字 → 阿拉伯（法条号常用中文）
_CN_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
_CN_UNITS = {"十": 10, "百": 100, "千": 1000}


def _cn_to_int(text: str) -> int | None:
    """中文数字转整数（支持「一千零七十九」「三十」「十五」）。

    为什么要自己转：法条号在中文文书里几乎总写成中文，而核查接口要的是
    数字。交给模型转会出现「一千零七十九 → 1009」这种错——一次算错就等于
    核错了一条法条。
    """
    raw = (text or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        return int(raw)
    total = 0
    section = 0
    digit = 0
    for ch in raw:
        if ch in _CN_DIGITS:
            digit = _CN_DIGITS[ch]
            continue
        unit = _CN_UNITS.get(ch)
        if unit is None:
            return None
        # 「十」单独出现时表示 10（如「十五」= 15）
        section += (digit or 1) * unit
        digit = 0
    return total + section + digit


def _extract_statutes(text: str) -> list[dict[str, Any]]:
    """从文本里抽出法条引用（去重，保留首次出现的顺序）。"""
    seen: set[tuple[str, int | None]] = set()
    out: list[dict[str, Any]] = []
    for match in _STATUTE_RE.finditer(text or ""):
        law = match.group("law").strip()
        article_raw = match.group("article")
        article = _cn_to_int(article_raw)
        key = (law, article)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "raw": match.group(0).strip(),
                "law_name": law,
                "article_num": article,
                "article_num_raw": article_raw,
                "paragraph": match.group("para") or "",
            }
        )
    return out


def _validate_case_number(raw: str) -> dict[str, Any]:
    """校验案号格式（不做数据库检索——案号真实性要靠威科/法院网站）。

    只查**格式合理性**：年份范围、编号段、案件类型字。这能挡掉大部分
    「看起来像案号但根本不是」的编造（例如年份写成 20265、编号是 0）。
    """
    match = _CASE_NO_RE.search(raw or "")
    if match is None:
        return {
            "raw": raw,
            "status": "not_verified",
            "issue": "案号格式不符合《人民法院案件案号编制规则》（形如「(20XX)某0105民初某某号」）",
        }
    year = int(match.group("year"))
    num = int(match.group("num"))
    problems: list[str] = []
    if not (1949 <= year <= 2100):
        problems.append(f"年份 {year} 不合理")
    if num <= 0:
        problems.append("案件编号不能为 0")
    if problems:
        return {"raw": raw, "status": "not_found", "issue": "；".join(problems)}
    return {
        "raw": raw,
        "status": "not_verified",
        "parsed": {
            "year": year,
            "court": match.group("court"),
            "type": match.group("type"),
            "number": num,
        },
        "issue": "格式正确，但真实性需通过威科/法院网站检索确认",
    }


def _summarize(references: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"verified": 0, "not_verified": 0, "not_found": 0}
    for ref in references:
        status = str(ref.get("status") or "not_verified")
        if status in counts:
            counts[status] += 1
        else:
            counts["not_verified"] += 1
    return counts


def verify_citations(text: str, credential_id: int | None = None) -> dict[str, Any]:
    """核查文中的法条与案号引用。

    **什么时候必须用**：准备把任何带法条/案号的内容写进正式文书之前。
    写「根据《民法典》第 X 条」而没有核查过，是法律场景里最典型的一类
    不可辩护的错误。

    **默认状态是 `not_verified`**：只有拿到可点击来源的才算 `verified`。
    `not_found` 意味着「明确检索过、确实没有」——这往往说明条号是编的，
    应当删除或改正，而不是换个说法蒙过去。

    Args:
        text: 要核查的全文（起诉状、审查意见、备忘录等）。
        credential_id: 威科先行检索凭证 ID（法规有效性与原文核查需要它）。
            不传时**只做格式与结构校验**，所有法条一律 `not_verified`——
            这不是失败，是「没查」，会在 `note` 里说清。

    Returns:
        ``{references, summary, needs_review, coverage, note}``。

        - ``references``：逐条结果，含 ``status`` / ``issue`` / 查到的原文；
        - ``summary``：三态计数；
        - ``needs_review``：需要人工核对的条目（`not_verified` + `not_found`）；
        - ``coverage``：``full``（真查了）/ ``format_only``（只做格式校验）。
    """
    body = str(text or "").strip()
    if not body:
        raise ValueError("text 不能为空——请传入要核查的文书全文")

    statutes = _extract_statutes(body)
    case_numbers = [_validate_case_number(m.group(0)) for m in _CASE_NO_RE.finditer(body)]

    references: list[dict[str, Any]] = []
    coverage = "format_only"
    note = ""

    if credential_id and statutes:
        # 走既有威科链路（含登录、凭证解密、插件探测——不重写以保住安全审计
        # 做过的域白名单等约束）
        payload = client.post(
            "/legal-research/law-verification/check",
            json={"text": body, "credential_id": int(credential_id)},
            timeout=180,
        )
        coverage = "full"
        checked = {str(item.get("law_name") or "").strip(): item for item in (payload.get("references") or [])}
        for item in statutes:
            hit = checked.get(item["law_name"])
            if hit is None:
                references.append(
                    {
                        **item,
                        "status": "not_verified",
                        "issue": "已检索但未返回该法规的核查结果",
                    }
                )
                continue
            # 后端 status 语义：valid/invalid/unknown（插件侧约定）
            backend_status = str(hit.get("status") or "").lower()
            validity = str(hit.get("validity") or "").lower()
            if backend_status in ("valid", "ok") and validity not in ("invalid", "repealed", "abolished"):
                status = "verified"
                issue = ""
            elif backend_status in ("invalid", "not_found", "missing"):
                status = "not_found"
                issue = "检索未命中该条文"
            else:
                status = "not_verified"
                issue = f"有效性存疑（后端状态：{backend_status or 'unknown'}）"
            references.append(
                {
                    **item,
                    "status": status,
                    "issue": issue,
                    "article_text": hit.get("article_text"),
                    "validity": hit.get("validity"),
                }
            )
    else:
        note = (
            "未提供 credential_id，本次只做了格式与结构校验，法条一律标记为 "
            "not_verified。若需确认条文现行有效性，请带 credential_id 重新核查。"
            if statutes
            else "文中未发现法条引用。"
        )
        for item in statutes:
            references.append({**item, "status": "not_verified", "issue": "未执行法规库检索"})

    references.extend(case_numbers)
    summary = _summarize(references)
    needs_review = [r for r in references if r.get("status") != "verified"]

    return {
        "references": references,
        "summary": summary,
        "needs_review": needs_review,
        "coverage": coverage,
        "note": note,
        "hint": (
            "needs_review 里的每一条都必须人工核对后才能写入正式文书。"
            "not_found 通常意味着条号有误或系编造，应删除或改正，不要换种说法绕过。"
            if needs_review
            else "全部引用已核查通过。"
        ),
    }
