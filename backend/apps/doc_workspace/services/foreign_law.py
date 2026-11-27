"""域外法查明：把「合同里引用的外国法到底存不存在」变成审查链里可机械判定的证据。

## 为什么必须在审查链里做，而不是让模型「记得」

模型对泰国法的训练数据极稀薄。一份中英双语泰国土地租赁合同里写
「依据《泰国商业租赁法》第 42 条，租赁期可为 50 年」，这句话有三处错：

1. 泰国**没有**《商业租赁法》这部法；
2. 不动产租赁上限是 **30 年**（Civil and Commercial Code 第 540 条）；
3. 超过 3 年必须登记（第 538 条）。

模型能挑出第 2 处（这是常识级知识），但**挑不出第 1 处**——它会顺着「有一部
商业租赁法」这个假设继续推理，甚至补充「第 42 条还规定……」。这就是编造外国法
引用的典型形态：错得越具体，看起来越可信。

所以这里的分工是：

| 谁 | 干什么 | 为什么是它 |
|---|---|---|
| 规则层（本模块） | 抽取引用 → 查存在性 → 给出条文原文 | 确定性、可测、不耗模型 token |
| 模型层（`review_pipeline`） | 读**真实条文**，判断合同表述是否与之一致 | 需要语义理解，但已有原文做锚 |

**关键设计：把查明到的条文原文喂给模型。** 以前模型只能靠记忆判断「这条写得对不对」；
现在提示词里有 `Section 540. The duration of a hire of immovable property cannot exceed
thirty years...` 的原文，模型要做的是比对，不是回忆。这是「不许编造」唯一能落地的做法。

## 与类案检索（`case_evidence`）的关系

两者是**并列的风险来源**，不是替代：

- `case_evidence` 查「这类条款在本院实际怎么判」（`risk_source=case`）；
- 本模块查「这条法在不在、写了什么」（`risk_source=statute`，但是**域外** statute）。

类案检索失败 = 这轮没有类案依据；域外法查明失败 = 这轮**不能下域外法结论**。
后者更严重，因为域外法结论是「这条合同条款有效/无效」的直接依据。

## 「不存在」什么时候才能说（本模块最谨慎的一处）

上游 `JudicialVerifier.check` 有三个档位：`exists`（取到原文）/ `不存在该引用` /
无结论。真机实测发现两种**假「不存在」**：

1. **法名对不上**：`Arbitration Act` 在 BARLC 的泰国库里没有同名词条，
   但《Arbitration Act B.E. 2545》确实存在 → 报「不存在」是错的；
2. **条款切分不完整**：Labour Protection Act 只切出 4 条（PDF 取文失败），
   于是第 118 条被判「该法律正文中不存在第 118 条（共 4 条）」→ 也是错的。

所以本模块自己先查一次**法名命中数**：零命中才是 `missing_law`；有命中但解析失败、
或切出的条文数少得不可信，一律降为 `unconfirmed`（待人工核对）。
**宁可说「查不清」，也不说「不存在」**——错杀一条真实引用的代价，律师会直接用脚投票。
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

import httpx

from ..models import Consequence, Delivery, Jurisdiction, RiskSource, RuleClass, Severity, SourceWeight, Stage, Verdict

logger = logging.getLogger(__name__)

#: 整轮查明的硬预算（秒）。超时就带着已有结果继续审查——查明是增强项，不能拖垮审查。
FOREIGN_LAW_TIMEOUT_SECONDS = 40.0

#: 单条引用核验的预算（秒）。BARLC 单次 search+detail+取 PDF 正常 1–8s。
CITATION_TIMEOUT_SECONDS = 25.0

#: 最多核验几条引用。一份合同通常 3–8 条；超过就是「法律汇编」而不是合同了。
MAX_CITATIONS = 12

#: 「切出 N 条」低于这个数，认为条款切分不可信（真机：Labour Protection Act 只切出 4 条）。
MIN_PLAUSIBLE_SECTIONS = 5


#: 可预期的失败面。刻意**不写 `except Exception`**（仓库有棘轮门禁）：
#: 网络/上游/凭据/解析/超时这几类覆盖了 BARLC 的真实故障面；真正的编程错误应该炸出来。
#:
#: 插件异常是 lazily 取的：`plugins` 是子模块，缺了也不该让本模块 import 失败
#: （`_default_verifier` 里同样按需 import）。
def _upstream_errors() -> tuple[type[BaseException], ...]:
    plugin_errors: tuple[type[BaseException], ...] = ()
    try:
        from plugins.barlc_asean_law.models import BarlcError
    except ImportError:  # pragma: no cover —— 插件缺失时只剩标准异常面
        pass
    else:
        plugin_errors = (BarlcError,)
    return (
        *plugin_errors,
        # 插件的 `_authed_post` **不吞** httpx 异常：网络中断/超时/连接被拒会直接
        # 抛到这里。漏掉它，一次断网就会让整轮审查崩在 `execute_run` 之外
        # （轮次永远停在 running），而不是退化成「本轮没有域外法依据」。
        httpx.HTTPError,
        OSError,
        ValueError,
        TypeError,
        KeyError,
        RuntimeError,
        TimeoutError,
    )


#: 法域 → BARLC 国别码。BARLC 用的**不是 ISO 缩写**，猜必错。
BARLC_COUNTRY_CODE: dict[str, str] = {
    Jurisdiction.TH: "LAWCOUNTRYTG",
    Jurisdiction.VN: "LAWCOUNTRYYN",
    Jurisdiction.MY: "LAWCOUNTRYMLXY",
    Jurisdiction.SG: "LAWCOUNTRYXJP",
    Jurisdiction.ID: "LAWCOUNTRYYDNXY",
    Jurisdiction.PH: "LAWCOUNTRYFLB",
    Jurisdiction.LA: "LAWCOUNTRYLW",
    Jurisdiction.KH: "LAWCOUNTRYJPZ",
    Jurisdiction.MM: "LAWCOUNTRYMD",
    Jurisdiction.BN: "LAWCOUNTRYWL",
}

#: 查明状态的枚举（写进 `run.summary`，也要落 Finding 的 rule_key）
STATUS_VERIFIED = "verified"
"""法存在且取到了该条原文"""
STATUS_MISSING_LAW = "missing_law"
"""法名在该国库里零命中——真编造"""
STATUS_MISSING_SECTION = "missing_section"
"""法存在、条款切分可信、但该条号不在其中——错法号"""
STATUS_UNCONFIRMED = "unconfirmed"
"""查不清（法名近似 / 切分不完整 / 名称多国同名），必须人工核对"""
STATUS_UNAVAILABLE = "unavailable"
"""查明服务不可用（无凭据 / 网络 / 上游故障）"""
STATUS_SKIPPED = "skipped"
"""本轮没查（无引用 / 无法域 / 已关闭）"""

_INVALID_STATUSES = (STATUS_MISSING_LAW, STATUS_MISSING_SECTION)


# ── 引用抽取 ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Citation:
    """合同里的一处域外法引用。"""

    law_name: str
    """法名（可能是中文简称、也可能是英文全名）"""
    section_number: str = ""
    """条号。空 = 只引了法名没有条号"""
    raw: str = ""
    """原文片段，用于在清单里给律师看「你合同里是这么写的」"""


#: 《法律名》第 X 条 / 第X条之Y / 第 X 条第 Y 款
_ZH_RE = re.compile(r"《([^》]{2,60})》\s*第\s*([0-9一二三四五六七八九十百零〇\+／/]+)\s*条")

#: Section 8 of the Foreign Business Act / section 8, Civil and Commercial Code
_EN_RE = re.compile(
    r"(?:Section|Sec\.|Article|Art\.)\s*([0-9]+(?:\s*(?:bis|ter|/[0-9]+))?)\s*(?:of\s+the\s+)?"
    r"([A-Z][A-Za-z'’\.\-\s,()]{3,80}?(?:Act|Code|Law|Decree|Regulation|Ordinance|Notification))\b",
    re.IGNORECASE,
)

#: 法名在前、条号在后：`Arbitration Act Section 99` / `Labour Protection Act, Section 118`
_EN_NAME_FIRST_RE = re.compile(
    r"([A-Z][A-Za-z'’\.\-\s,()]{3,80}?(?:Act|Code|Law|Decree|Regulation))\s*,?\s*"
    r"(?:Section|Sec\.|Article|Art\.)\s*([0-9]+(?:\s*(?:bis|ter|/[0-9]+))?)",
)

#: 提到法名但没带条号：`under the Foreign Business Act`
_EN_LAW_ONLY_RE = re.compile(
    r"(?:under|pursuant to|in accordance with|according to)\s+the\s+"
    r"([A-Z][A-Za-z'’\.\-\s,()]{3,80}?(?:Act|Code|Law|Decree|Regulation))\b",
    re.IGNORECASE,
)

#: 中国法引用（`《民法典》第470条`）不该被送去做域外法查明。
#:
#: 判据用「中国法名白名单 + 中文书名号里没出现外国国别」两道，而不是「中文一律跳过」——
#: 合同里经常把泰国法写成中文（《泰国民商法典》），跳过去就等于漏查。
_CN_LAW_HINTS = (
    "民法典",
    "合同法",
    "公司法",
    "民事诉讼法",
    "仲裁法",
    "城市房地产管理法",
    "土地管理法",
    "劳动法",
    "劳动合同法",
)
_FOREIGN_HINTS = (
    "泰国",
    "泰王",
    "越南",
    "马来",
    "新加坡",
    "印尼",
    "印度尼西亚",
    "菲律宾",
    "老挝",
    "柬埔寨",
    "缅甸",
    "文莱",
    "外国",
    "域外",
)


def _looks_chinese_domestic(law_name: str) -> bool:
    name = (law_name or "").strip()
    if any(hint in name for hint in _FOREIGN_HINTS):
        return False
    return any(hint in name for hint in _CN_LAW_HINTS)


def _clean_law_name(value: str) -> str:
    """剥掉抓尾巴带进来的连接词与标点。"""
    name = re.sub(r"\s+", " ", (value or "").strip())
    name = re.sub(r"^(?:of\s+the|the)\s+", "", name, flags=re.IGNORECASE)
    name = name.strip(" ,.;:，。；：、")
    # 英文法名首字母大写（模型/正则抓来的常是小写起头）
    if name and name[0].islower():
        name = name[0].upper() + name[1:]
    return name


def extract_citations(text: str) -> list[Citation]:
    """从合同全文抽出域外法引用（中英双语都抽）。

    **只抽「可核验」的形状**：带条号的中文书名号引用、带 Section 的英文引用，
    以及「under the XXX Act」这种只引法名的。抽不出来的自然语言表述
    （「根据泰国法律的相关规定」）不猜——猜出来的法名去查，会把「查无此法」
    误报成「合同引用了不存在的法」。
    """
    body = text or ""
    found: list[Citation] = []
    seen: set[tuple[str, str]] = set()

    def _push(law_name: str, section: str, raw: str) -> None:
        name = _clean_law_name(law_name)
        if not name or _looks_chinese_domestic(name):
            return
        key = (name.lower(), section)
        if key in seen:
            return
        seen.add(key)
        found.append(Citation(law_name=name, section_number=section, raw=raw.strip()[:200]))

    for match in _ZH_RE.finditer(body):
        _push(match.group(1), re.sub(r"\s+", "", match.group(2)), match.group(0))
    for match in _EN_RE.finditer(body):
        _push(match.group(2), re.sub(r"\s+", "", match.group(1)).lower(), match.group(0))
    for match in _EN_NAME_FIRST_RE.finditer(body):
        _push(match.group(1), re.sub(r"\s+", "", match.group(2)).lower(), match.group(0))
    for match in _EN_LAW_ONLY_RE.finditer(body):
        _push(match.group(1), "", match.group(0))

    return found[:MAX_CITATIONS]


# ── 核验 ────────────────────────────────────────────────────────────────


@dataclass
class CitationEvidence:
    """一条引用的查明结果。"""

    citation: Citation
    status: str = STATUS_UNCONFIRMED
    law_title: str = ""
    section_text: str = ""
    reason: str = ""
    matched_by: str = ""
    source_url: str = ""
    effective_date: str = ""
    version_warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == STATUS_VERIFIED

    def to_text(self) -> str:
        head = f"- 引用：{self.citation.law_name}"
        if self.citation.section_number:
            head += f" 第 {self.citation.section_number} 条"
        title = f"（库中法名：{self.law_title}）" if self.law_title else ""
        verdict = {
            STATUS_VERIFIED: "已查明到条文原文",
            STATUS_MISSING_LAW: "**查无此法**",
            STATUS_MISSING_SECTION: "**查无此条号**",
            STATUS_UNCONFIRMED: "**无法确认，需人工核对**",
            STATUS_UNAVAILABLE: "查明服务不可用",
            STATUS_SKIPPED: "未查",
        }.get(self.status, self.status)
        lines = [head + title, f"  查明结论：{verdict}"]
        if self.reason:
            lines.append(f"  依据：{self.reason}")
        if self.effective_date:
            lines.append(f"  生效日：{self.effective_date}")
        for warning in self.version_warnings:
            lines.append(f"  ⚠ 版本：{warning}")
        if self.section_text:
            lines.append(f"  条文原文：{self.section_text[:900]}")
        return "\n".join(lines)

    def to_summary(self) -> dict[str, Any]:
        return {
            "law_name": self.citation.law_name,
            "section_number": self.citation.section_number,
            "status": self.status,
            "law_title": self.law_title,
            "matched_by": self.matched_by,
            "source_url": self.source_url,
            "effective_date": self.effective_date,
            "reason": self.reason[:300],
        }


@dataclass
class ForeignLawEvidence:
    """一轮审查的域外法查明证据。"""

    items: list[CitationEvidence] = field(default_factory=list)
    jurisdiction: str = Jurisdiction.CN
    skipped: str = ""
    timeout: bool = False
    error: str = ""

    @property
    def checked(self) -> list[CitationEvidence]:
        return [i for i in self.items if i.status not in (STATUS_SKIPPED,)]

    @property
    def invalid(self) -> list[CitationEvidence]:
        return [i for i in self.items if i.status in _INVALID_STATUSES]

    @property
    def unconfirmed(self) -> list[CitationEvidence]:
        return [i for i in self.items if i.status == STATUS_UNCONFIRMED]

    def to_prompt_block(self) -> str:
        if not self.items:
            return ""
        lines = [
            "## 域外法查明结果（BARLC 数据库实时检索，**不是模型记忆**）",
            "",
            "下面是合同里出现的域外法引用及其查明结论。三条硬规则：",
            "1. **只能引用本节列出的法条**；本节没列出的外国法条文一律不许出现在 `legal_basis` 里；",
            "2. 标「查无此法 / 查无此条号」的引用，必须报一条 `rule_key=foreign_law.citation_invalid` "
            "的 mandatory 结论（`severity=high`，`delivery=list_only`）；",
            "3. 标「已查明到条文原文」的，请**逐字比对**合同对该条的表述与下面的原文："
            "把上限写成下限、把例外写成原则、引用了已修订版本，都要按 "
            "`rule_key=foreign_law.citation_verified` 报出来。",
            "",
        ]
        lines.extend(item.to_text() for item in self.items)
        return "\n".join(lines) + "\n\n"

    def to_summary(self) -> dict[str, Any]:
        return {
            "jurisdiction": self.jurisdiction,
            "country_code": BARLC_COUNTRY_CODE.get(self.jurisdiction, ""),
            "skipped": self.skipped,
            "timeout": self.timeout,
            "error": self.error,
            "counts": {
                status: len([i for i in self.items if i.status == status])
                for status in (
                    STATUS_VERIFIED,
                    STATUS_MISSING_LAW,
                    STATUS_MISSING_SECTION,
                    STATUS_UNCONFIRMED,
                    STATUS_UNAVAILABLE,
                )
            },
            "items": [item.to_summary() for item in self.items],
        }


class CitationVerifier(Protocol):
    """核验器接口：给定一条引用，返回查明结论。测试注入假实现。"""

    def __call__(self, citation: Citation, *, country_code: str) -> CitationEvidence: ...


def _default_verifier() -> CitationVerifier | None:
    """用插件（BARLC）构造核验器。进程内直调，不走 HTTP。

    **为什么在这里 `jury=False`**：合议层要 3 次模型调用、约 2 万 token、20+ 秒，
    而审查本身已经是一次模型调用。真机实测合议在长条文上 3/3 判定器全部
    `parse_failed`（输出被 `max_tokens` 截断），花了 21,512 token 换来「待判定」。
    所以审查链只用**规则层**（法是否在、条是否存在、原文是什么），语义比对交给
    已经拿着原文的审查模型 —— 一分钱不额外花。
    """
    try:
        from plugins.barlc_asean_law.adapter import get_adapter
        from plugins.barlc_asean_law.credential import resolve_credential
        from plugins.barlc_asean_law.verify import CitationRequest, JudicialVerifier
    except ImportError:  # pragma: no cover —— 插件缺失时应整体降级
        logger.warning("域外法查明未接入：barlc_asean_law 插件不可用")
        return None

    def _verify(citation: Citation, *, country_code: str) -> CitationEvidence:
        adapter = get_adapter()
        credential = resolve_credential()
        evidence = CitationEvidence(citation=citation)

        verifier = JudicialVerifier(adapter)
        try:
            check = verifier.check(
                credential,
                CitationRequest(
                    law_name=citation.law_name,
                    section_number=citation.section_number,
                    claim="",
                    country_code=country_code or None,
                ),
                jury=False,
            )
        except _upstream_errors() as exc:
            logger.warning("域外法条款核验失败 law=%s s.%s: %s", citation.law_name, citation.section_number, exc)
            evidence.status = STATUS_UNAVAILABLE
            evidence.reason = f"核验失败：{exc}"
            return evidence

        evidence.law_title = str(getattr(check, "law_title", "") or "")
        evidence.section_text = str(getattr(check, "section_text", "") or "")
        evidence.matched_by = str(getattr(check, "matched_by", "") or "")
        evidence.source_url = str(getattr(check, "source_url", "") or "")
        evidence.effective_date = str(getattr(check, "effective_date", "") or "")
        evidence.version_warnings = list(getattr(check, "version_warnings", ()) or ())
        evidence.reason = str(getattr(check, "reason", "") or "")

        if evidence.section_text:
            evidence.status = STATUS_VERIFIED
            return evidence

        # 没取到正文 + 名称没认准：可能是「编造」也可能是「中文译名与库内标题不同」
        # （《泰国民商法典》vs 库内「民商法典」）。
        #
        # 先用变体**再核一次**：这不只是「判死 vs 说不清」的区别——拿到条文原文才
        # 能把「30 年上限」这类内容比对交给模型。真机第一次跑就是因为卡在中文法名上，
        # 模型只能凭记忆判断合同对 CCC 540 的表述对不对。
        for variant in law_name_variants(citation.law_name)[1:]:
            try:
                retry = verifier.check(
                    credential,
                    CitationRequest(
                        law_name=variant,
                        section_number=citation.section_number,
                        claim="",
                        country_code=country_code or None,
                    ),
                    jury=False,
                )
            except _upstream_errors() as exc:
                logger.warning("域外法变体核验失败 law=%s variant=%s: %s", citation.law_name, variant, exc)
                break
            if getattr(retry, "section_text", ""):
                evidence.law_title = str(getattr(retry, "law_title", "") or "")
                evidence.section_text = str(retry.section_text or "")
                evidence.matched_by = str(getattr(retry, "matched_by", "") or "variant")
                evidence.source_url = str(getattr(retry, "source_url", "") or "")
                evidence.effective_date = str(getattr(retry, "effective_date", "") or "")
                evidence.version_warnings = list(getattr(retry, "version_warnings", ()) or ())
                evidence.status = STATUS_VERIFIED
                evidence.reason = f"以译名变体「{variant}」定位到条文"
                return evidence

        if not evidence.matched_by:
            if _probe_law_exists(adapter, credential, citation.law_name, country_code):
                evidence.status = STATUS_UNCONFIRMED
                evidence.reason = evidence.reason or "法名与库内标题不同，未能锁定具体法条"
                return evidence
            evidence.status = STATUS_MISSING_LAW
            evidence.reason = f"BARLC 该国库中以多种写法都检索不到该法律（关键词：{citation.law_name}）"
            return evidence

        evidence.status, evidence.reason = classify_status(
            section_text=evidence.section_text,
            matched_by=evidence.matched_by,
            reason=evidence.reason,
            needs_human=bool(getattr(check, "needs_human", False)),
            result=str(getattr(check, "result", "") or ""),
            has_section_number=bool(citation.section_number),
        )
        return evidence

    return _verify


#: 中文译名与库内标题之间最常见的两种差异：带国别前缀、带「法/法典」后缀。
_NAME_VARIANTS_RE = re.compile(
    r"^(?:泰王国|泰国|泰|越南|马来|新嘉坡|新加坡|印度尼西亚|印尼|菲律宾|老挝|柬埔寨|缅甸|文莱)"
)


def law_name_variants(law_name: str) -> list[str]:
    """生成「同一部法的不同写法」，用于存在性探测。

    为什么必须多写法：合同里写《泰国民商法典》，BARLC 库里这条法的标题是「民商法典」；
    直接拿原名去搜是零命中，而零命中如果直接当成「查无此法」，就会把一条**真实存在**的
    引用报成编造。这类假阳性的代价比漏报还高——律师试两次就会永久关掉这个功能。
    """
    base = (law_name or "").strip()
    variants: list[str] = []
    if base:
        variants.append(base)
    stripped = _NAME_VARIANTS_RE.sub("", base).strip()
    if stripped and stripped != base:
        variants.append(stripped)
    # 「XX法」→「XX法典」/「XX法典」→「XX法」：中文译名在两种写法之间摇摆是常态
    for probe in list(variants):
        if probe.endswith("法典"):
            variants.append(probe[:-2])
        elif probe.endswith("法") and len(probe) > 2:
            variants.append(probe + "典")
    return list(dict.fromkeys(v for v in variants if v.strip()))


def _probe_law_exists(adapter: Any, credential: Any, law_name: str, country_code: str) -> bool:
    """用多种写法探测「这部法在库里到底有没有」。异常时按「有」处理（宁可说查不清）。"""
    for probe in law_name_variants(law_name):
        try:
            total, _hits = adapter.search(
                credential,
                keyword=probe,
                country_code=country_code or None,
                field="Title",
                page=1,
                page_size=3,
            )
        except _upstream_errors() as exc:  # 上游故障 ≠ 不存在
            logger.warning("域外法存在性探测失败 law=%s probe=%s: %s", law_name, probe, exc)
            return True
        if total:
            return True
    return False


#: 「上游说查不到，但其实不是查不到」的原因片段。命中即降为「待人工核对」。
#:
#: 这些字符串来自 `plugins/barlc_asean_law/verify.py` 的固定文案，我是**按语义匹配**
#: 而不是按 equals 精确比：上游改一个字就漏判的护栏，等于没有护栏。
_NO_VERDICT_HINTS = (
    "未能切分",
    "无可读正文",
    "未指定条款号",
    "名称近似",
    "无法排除",
)

#: 上游「结论为空」的两种形态（`result==""`）都是「没形成结论」，不是「不存在」。
_NO_RESULT = ""


def classify_status(
    *,
    section_text: str,
    matched_by: str,
    reason: str,
    needs_human: bool = False,
    result: str = "",
    has_section_number: bool = True,
) -> tuple[str, str]:
    """把上游核验结果翻译成四档查明结论（纯函数，可单测）。

    真机实测（2026-11-27，9 个国家各抽 4–6 条）逼出这张表：**「查不到」有五种完全
    不同的真相**，混成一种就会误杀真实引用：

    | 输入 | 结论 | 真相 |
    |:--|:--|:--|
    | 取到条文原文 | `verified` | 可以直接比对内容 |
    | 只给了法名、没给条号，且法已定位 | `verified` | 「法存在」本身就是结论 |
    | `result==""`（上游明确说「没形成结论」） | `unconfirmed` | 切不出条款 / 名称近似 / 多国同名 |
    | `needs_human` 为真 | `unconfirmed` | 上游自己要求人工复核 |
    | 命中「未能切分 / 无可读正文」这类文案 | `unconfirmed` | **法在库里，只是 PDF 取不出正文**（SG / PH / MY / BN 普遍如此） |
    | 名称没认准（`matched_by` 空） | `unconfirmed` | 中文译名与库内标题不同 |
    | 切出的条文数 < 5 | `unconfirmed` | 切分不完整（真机：Labour Protection Act 只切出 4 条） |
    | 以上都不命中，且上游给了「共 N 条」的结论 | `missing_section` | 法在、切分正常、条号确实不在其中 |

    ## 为什么「法在库里但取不出正文」必须算 `unconfirmed`

    BARLC 对**判例法国家**（新加坡、菲律宾、马来西亚、文莱）的成文法大量只有中文
    标题页，英文全文文件不存在。若把这种情形判成「查无此条」，一份引用
    `Arbitration Act 2005 Section 9` 的正经马来西亚合同会被报成
    「mandatory / high / 引用了不存在的法」——律师第一次就会把整个功能关掉。
    """
    if (section_text or "").strip():
        return STATUS_VERIFIED, reason
    if not (matched_by or "").strip():
        # 名称没认准（近似/多国同名/法名与库内标题不同）→ 不能判死。
        # 这一档必须排在「只给法名」之前：一部**不存在**的法也可能只被引了法名。
        return STATUS_UNCONFIRMED, reason
    if not has_section_number:
        # 只引法名且名称已定位到具体法 → 「法存在」本身就是可用的结论
        return STATUS_VERIFIED, reason or "仅引用法名，已确认该法在库中存在"
    if result == _NO_RESULT:
        # 上游返回空结论：切不出条款 / 名称近似 / 同名多国，一律不判死
        return STATUS_UNCONFIRMED, reason
    if needs_human:
        return STATUS_UNCONFIRMED, reason
    if any(hint in (reason or "") for hint in _NO_VERDICT_HINTS):
        return STATUS_UNCONFIRMED, reason
    count = _parsed_section_count(reason)
    if count is not None and count < MIN_PLAUSIBLE_SECTIONS:
        # 切出来的条文少得不可信（PDF 取文失败/体例不同）→ 不能判死
        detail = f"条款切分仅 {count} 条，不足以判定该条号不存在"
        return STATUS_UNCONFIRMED, f"{reason}；{detail}" if reason else detail
    return STATUS_MISSING_SECTION, reason


_COUNT_RE = re.compile(r"共\s*(\d+)\s*条")


def _parsed_section_count(reason: str) -> int | None:
    """从「该法律正文中不存在第 X 条（共 N 条）」里取出 N。"""
    match = _COUNT_RE.search(reason or "")
    return int(match.group(1)) if match else None


def register_verifier(verifier: CitationVerifier | None) -> None:
    """替换全局核验器（测试用；传 None 复原）。"""
    global _VERIFIER_OVERRIDE
    _VERIFIER_OVERRIDE = verifier


_VERIFIER_OVERRIDE: CitationVerifier | None = None


def default_verifier() -> CitationVerifier | None:
    if _VERIFIER_OVERRIDE is not None:
        return _VERIFIER_OVERRIDE
    return _default_verifier()


def gather(
    *,
    text: str,
    jurisdiction: str = Jurisdiction.CN,
    verifier: CitationVerifier | None = None,
    timeout_seconds: float = FOREIGN_LAW_TIMEOUT_SECONDS,
) -> ForeignLawEvidence:
    """抽取 + 核验合同里的域外法引用。**任何失败都返回证据对象，不抛异常。**

    中国法域且合同里没有域外法引用时，`skipped` 会写明原因，成本为 0。
    """
    evidence = ForeignLawEvidence(jurisdiction=jurisdiction)
    citations = extract_citations(text)
    if not citations:
        evidence.skipped = "合同内未发现可核验的域外法引用"
        return evidence
    if jurisdiction == Jurisdiction.CN and not any(c.law_name for c in citations):
        evidence.skipped = "中国法域且无域外法引用"
        return evidence

    checker = verifier or default_verifier()
    if checker is None:
        evidence.skipped = "域外法查明未接入（插件不可用）"
        return evidence

    country_code = BARLC_COUNTRY_CODE.get(jurisdiction, "")
    if not country_code and jurisdiction != Jurisdiction.CN:
        # 没有国别码 = BARLC 不覆盖这个法域（如东帝汶）。此时**必须不查**：
        # 不传 country_code 是「跨全部东盟国家检索」，会拿越南/泰国的同名法
        # 去回答东帝汶合同的问题——那比「查不到」危险得多。
        evidence.skipped = f"BARLC 不覆盖该法域（{jurisdiction}），未做域外法查明"
        return evidence

    def _run() -> list[CitationEvidence]:
        collected: list[CitationEvidence] = []
        for citation in citations:
            try:
                collected.append(checker(citation, country_code=country_code))
            except _upstream_errors() as exc:  # 单条失败不该拖垮其它引用
                logger.warning("域外法单条核验异常 law=%s: %s", citation.law_name, exc)
                collected.append(CitationEvidence(citation=citation, status=STATUS_UNAVAILABLE, reason=str(exc)))
        return collected

    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="doc-review-foreign-law")
    try:
        evidence.items = pool.submit(_run).result(timeout=timeout_seconds)
    except FutureTimeout:
        evidence.timeout = True
        logger.warning("域外法查明超时（%.1fs），审查继续（不带域外法依据）", timeout_seconds)
    except _upstream_errors() as exc:
        evidence.error = str(exc)
        logger.warning("域外法查明失败，审查继续", exc_info=True)
    finally:
        # 不等线程：查明可能卡在外部网络上，等它就是让审查一起卡住
        pool.shutdown(wait=False, cancel_futures=True)
    return evidence


# ── 结论注入（确定性，不依赖模型是否听话）──────────────────────────────


def _base_item(*, rule_key: str, title: str, reason: str, quote: str, severity: str, rule_class: str) -> dict[str, Any]:
    return {
        "rule_key": rule_key,
        "clause_type": "法律引用",
        "rule_class": rule_class,
        "stage": Stage.GENERAL,
        "risk_source": RiskSource.STATUTE,
        "source_weight": SourceWeight.CORE,
        "consequence": Consequence.UNEFFECTIVE,
        "severity": severity,
        "verdict": Verdict.DEVIATION,
        "kind": "risk",
        "quote": quote,
        "title": title,
        "reason": reason,
        "impact": "以不存在的法律为依据的条款，在争议中不产生任何说服力；对方可据此主张起草方未尽审慎义务。",
        "legal_basis": "",
        "case_ref": "",
        "suggestion_original": "",
        "suggestion_replacement": "",
        "suggestion_note": "",
        "delivery": Delivery.LIST_ONLY,
        "direction": "mandatory" if rule_class == RuleClass.MANDATORY else "neutral",
        "in_top": False,
        "source": "foreign_law",
    }


def deterministic_findings(evidence: ForeignLawEvidence) -> list[dict[str, Any]]:
    """把「查无此法/查无此条」直接变成结论。

    ## 为什么不能只靠模型报

    提示词里写了「必须报」也没用：模型漏报时，程序这边没有任何兜底，律师看到的是
    「AI 审过了，这条没问题」。而「合同引用了一部不存在的泰国法」是**可以机械判定**
    的事实——查无此法就是查无此法，不需要模型同意。所以这一档由程序直接落结论，
    模型只管补充「条文内容对不上」那类需要语义判断的。

    `delivery=list_only` 是刻意的：替换成哪一部法、哪一条，只有律师知道
    （可能要改走 30 年 + 续期，也可能整段重写）。程序不乱改正文。
    """
    items: list[dict[str, Any]] = []
    for item in evidence.invalid:
        section = f" 第 {item.citation.section_number} 条" if item.citation.section_number else ""
        if item.status == STATUS_MISSING_LAW:
            title = f"合同引用的《{item.citation.law_name}》在泰国现行法库中查无此法"
        else:
            title = f"合同引用的《{item.citation.law_name}》{section} 查无此条号"
        items.append(
            _base_item(
                rule_key="foreign_law.citation_invalid",
                title=title[:200],
                reason=f"{item.reason or '域外法查明结论'}"
                + (f"；库中法名：{item.law_title}" if item.law_title else "")
                + "。请替换为正确的法名与条号，或删除该引用。",
                quote=item.citation.raw,
                severity=Severity.HIGH,
                rule_class=RuleClass.MANDATORY,
            )
        )
    for item in evidence.unconfirmed:
        section = f" 第 {item.citation.section_number} 条" if item.citation.section_number else ""
        items.append(
            _base_item(
                rule_key="foreign_law.citation_unconfirmed",
                title=f"《{item.citation.law_name}》{section} 的域外法引用无法确认，需人工核对原文"[:200],
                reason=(item.reason or "无法确认") + "。签约前须由执业律师核对条文原文与现行版本。",
                quote=item.citation.raw,
                severity=Severity.MEDIUM,
                rule_class=RuleClass.PROCEDURAL,
            )
        )
    return items


def escalate_model_citations(items: list[dict[str, Any]], evidence: ForeignLawEvidence) -> int:
    """模型自己写了一条「引用了查无此法」的结论时，把它升到 mandatory。

    模型可能报出 `foreign_law.citation_verified` 却把 severity 写成 medium
    （「引用不规范」）。但这里的事实是「这部法不存在」——按可谈的建议处理会让律师
    把它当措辞问题跳过。返回被升级的条数（写进 summary，可观测）。
    """
    invalid_names = {(i.citation.law_name or "").lower() for i in evidence.invalid if i.citation.law_name}
    if not invalid_names:
        return 0
    escalated = 0
    for item in items:
        if item.get("source") == "foreign_law":
            continue
        haystack = " ".join(str(item.get(key) or "") for key in ("legal_basis", "reason", "quote", "title")).lower()
        if not any(name and name in haystack for name in invalid_names):
            continue
        if item.get("rule_class") != RuleClass.MANDATORY:
            item["rule_class"] = RuleClass.MANDATORY
            item["severity"] = Severity.HIGH
            item["consequence"] = Consequence.UNEFFECTIVE
            escalated += 1
    return escalated


__all__ = [
    "BARLC_COUNTRY_CODE",
    "CITATION_TIMEOUT_SECONDS",
    "FOREIGN_LAW_TIMEOUT_SECONDS",
    "MAX_CITATIONS",
    "STATUS_MISSING_LAW",
    "STATUS_MISSING_SECTION",
    "STATUS_SKIPPED",
    "STATUS_UNCONFIRMED",
    "STATUS_UNAVAILABLE",
    "STATUS_VERIFIED",
    "Citation",
    "CitationEvidence",
    "CitationVerifier",
    "ForeignLawEvidence",
    "classify_status",
    "default_verifier",
    "deterministic_findings",
    "escalate_model_citations",
    "extract_citations",
    "gather",
    "law_name_variants",
    "register_verifier",
]
