"""类案检索作为审查的**第四个风险来源**（`risk_source=case`）。

## 为什么审查链里必须有这一步

法务总的「四维风险勘探」里，三维是标准库/流程/标的能做到的，唯独**案例检索**做不到：
「这块地在本院辖区实际怎么判」不在合同条款里，也不在任何规则库里，只能去检索。

之前我们的审查只靠 `statute`（法条 + 标准条款），于是最容易出的一种漏判是：
**条款写得合规，但同类案子在这家法院就是判不赢**。类案检索补的正是这一块。

## 三个工程约束（决定了实现长什么样）

1. **检索是异步的、慢的**（建任务 → 轮询 → 取结果）。审查本身已经在后台跑，但也
   不能给它开无限预算 → 这里给**硬超时** `CASE_EVIDENCE_TIMEOUT_SECONDS`，
   超时只记 `timeout=True` 并继续审查，绝不因为检索慢就把整轮审查判失败。
2. **可能没有凭证/配额**（威科账号）。缺失时返回空证据 + `skipped` 原因，而不是抛错
   ——「查不到类案」和「审查失败」是两件事，不能混。
3. **证据必须可回指**。模型说「据类案」但给不出案号时，我们把 `source_weight`
   降为 `supporting`：可以留作线索，但不能当决定性依据（否则就是让模型编案号）。

## 与 MCP 的关系

检索能力是 MCP 工具面已经包装好的既有资产（`mcp_server/tools/legal_research/`），
这里只做「以审查需要的形状取用」：拼查询 → 限预算 → 归一化 → 喂提示词。
**不重写检索**，也不在本模块里直连威科。
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from apps.core.exceptions import BusinessException

logger = logging.getLogger(__name__)

#: 整轮检索的硬预算（秒）。超时就带着已有结果继续审查——审查不能等检索。
CASE_EVIDENCE_TIMEOUT_SECONDS = 15.0

#: 最多发几个查询（每个查询对应一组「标的关系 + 争议焦点」），防止把配额打光。
MAX_QUERIES = 3

#: 每个查询取几条类案进提示词。多了只会稀释注意力，也让提示词变贵。
HITS_PER_QUERY = 3

#: 检索失败的可预期异常面。刻意不写 `except Exception`（仓库有棘轮门禁）：
#: 网络/配额/解析/超时这几类覆盖了检索器的真实故障面；真正的编程错误应该炸出来。
_SEARCH_ERRORS: tuple[type[BaseException], ...] = (
    RuntimeError,
    OSError,
    ValueError,
    TypeError,
    KeyError,
    TimeoutError,
    # 业务异常必须在内：检索侧「本所未配置威科账号」「能力降级」都是 BusinessException，
    # 不接住就会把「没查成类案」升级成「整轮审查失败」。
    BusinessException,
)


@dataclass(frozen=True)
class CaseHit:
    """一条类案。字段刻意保守：只收「能在提示词里说清楚、且能源头核对」的几项。"""

    case_no: str = ""
    """案号。**没有案号的结果不应当决定性依据**（见 normalize 的 source_weight 降档）。"""

    court: str = ""
    title: str = ""
    gist: str = ""
    """裁判要点/摘要（喂模型的就是它）。"""

    relevance: float = 0.0
    url: str = ""

    def to_text(self) -> str:
        bits = [self.case_no or "（无案号）", self.court, self.title]
        head = "｜".join(b for b in bits if b)
        return f"- {head}：{self.gist}".strip()


class CaseSearcher(Protocol):
    """检索器接口。生产实现调 MCP 包装好的检索，测试注入假实现。"""

    def __call__(self, *, query: str, facts: str, limit: int) -> list[CaseHit]: ...


@dataclass
class CaseEvidence:
    """一轮审查的类案证据。"""

    hits: list[CaseHit] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    skipped: str = ""
    """非空表示没查（无凭证/未接入/参数不足），值是给律师看的原因。"""

    timeout: bool = False

    @property
    def ok(self) -> bool:
        return bool(self.hits)

    def to_prompt_block(self) -> str:
        if not self.hits:
            return ""
        lines = [
            "## 类案要点（真实检索结果，不是模型记忆）",
            "下表是围绕本标的/争议点检索到的类案裁判要点。**只有在下面确实出现时**"
            "才可以把某条结论的 `risk_source` 标为 `case`，并在 `case_ref` 里写上对应案号；"
            "**没有案号就不要标 case**——编案号比不提类案严重得多。",
        ]
        lines.extend(hit.to_text() for hit in self.hits)
        return "\n".join(lines) + "\n\n"

    def to_summary(self) -> dict[str, Any]:
        return {
            "queries": self.queries,
            "hits": [
                {
                    "case_no": h.case_no,
                    "court": h.court,
                    "title": h.title,
                    "relevance": h.relevance,
                }
                for h in self.hits
            ],
            "skipped": self.skipped,
            "timeout": self.timeout,
        }


def build_queries(
    *, subject_profile: list[str], relations: list[dict[str, str]], rules: list[dict[str, Any]]
) -> list[str]:
    """把「强制性条款类型 + 标的特殊性 + 关系方」拼成检索关键词（**轮转取用**）。

    检索系统吃的是短关键词（空格分隔），不是整段案情；而且这三类词的价值不同：

    - 强制性条款类型 —— 法律风险最集中的地方（转让资格、优先购买权…）；
    - 标的特殊性 —— 最能决定裁判走向（工业用地、历史污染…）；
    - 关系方 —— 争议常从第三人身上冒出来（抵押权人、承租人…）。

    所以**轮转**取用（每类各来一个再进下一轮），而不是先把一类取完：只按顺序填，
    前两类就会把预算吃光，第三类永远进不了检索。这个 bug 在写测试时被抓住过。
    """
    mandatory_types: list[str] = []
    for rule in rules:
        if rule.get("rule_class") == "mandatory":
            clause_type = str(rule.get("clause_type") or "").strip()
            if clause_type:
                mandatory_types.append(clause_type)

    profile_items = [str(item).strip() for item in subject_profile if str(item).strip()]

    relation_names = [
        str(relation.get("relation") or "").strip()
        for relation in relations[:3]
        if str(relation.get("relation") or "").strip()
    ]

    buckets = [mandatory_types, profile_items, relation_names]
    ordered: list[str] = []
    depth = max((len(b) for b in buckets), default=0)
    for index in range(depth):
        for bucket in buckets:
            if index < len(bucket):
                ordered.append(bucket[index])

    seen: dict[str, None] = {}
    for probe in ordered:
        seen.setdefault(probe, None)
    return list(seen)[:MAX_QUERIES]


def gather(
    *,
    queries: list[str],
    facts: str,
    searcher: CaseSearcher | None,
    limit: int = HITS_PER_QUERY,
    timeout_seconds: float = CASE_EVIDENCE_TIMEOUT_SECONDS,
) -> CaseEvidence:
    """跑检索。**任何失败路径都返回证据对象，不抛异常。**

    这是审查链里的**增强项**：它失败的正确表现是「这轮没有类案依据」，
    而不是「审查失败」。所以凭证缺失、超时、检索器抛错，全部降级为空证据。
    """
    if searcher is None:
        return CaseEvidence(queries=queries, skipped="未接入类案检索")

    if not queries:
        return CaseEvidence(queries=[], skipped="标的/关系/条款信息不足，未生成检索词")

    evidence = CaseEvidence(queries=queries)

    def _run() -> list[CaseHit]:
        collected: list[CaseHit] = []
        for query in queries:
            try:
                collected.extend(searcher(query=query, facts=facts, limit=limit))
            except _SEARCH_ERRORS:
                # 单个查询失败不该拖垮其它查询（配额/网络/解析都可能单点失败）
                logger.warning("类案检索单次查询失败: %s", query, exc_info=True)
        return collected

    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="doc-review-cases")
    try:
        future = pool.submit(_run)
        evidence.hits = future.result(timeout=timeout_seconds)
    except FutureTimeout:
        evidence.timeout = True
        logger.warning("类案检索超时（%.1fs），审查继续（不带类案依据）", timeout_seconds)
    except _SEARCH_ERRORS:
        # 检索器整体故障同样降级：类案是增强项，不能让审查跟着失败
        evidence.skipped = "检索器异常"
        logger.warning("类案检索失败，审查继续", exc_info=True)
    finally:
        # 不等线程：它可能卡在外部网络上，等它就是让审查一起卡住
        pool.shutdown(wait=False, cancel_futures=True)

    # 去重（同案可能被多个查询命中），按相似度倒序，取前 N
    deduped: dict[str, CaseHit] = {}
    for hit in evidence.hits:
        key = hit.case_no or f"{hit.court}|{hit.title}"
        if key and key not in deduped:
            deduped[key] = hit
    evidence.hits = sorted(deduped.values(), key=lambda h: -h.relevance)[: limit * 2]
    return evidence


#: 检索器工厂。生产实现由 `_build_mcp_searcher` 提供；测试/适配器可用
#: `register_searcher` 覆盖（比 monkeypatch 模块内部名字更稳，不依赖导入顺序）。
_SEARCHER_FACTORY: Callable[[], CaseSearcher | None] | None = None


def register_searcher(factory: Callable[[], CaseSearcher | None] | None) -> None:
    """替换全局检索器工厂（传 None 复原）。"""
    global _SEARCHER_FACTORY
    _SEARCHER_FACTORY = factory


def _build_mcp_searcher() -> CaseSearcher | None:
    """用 MCP 已包装好的类案检索构造检索器（**进程内调用同一个 capability service**）。

    为什么调服务而不是走 HTTP：MCP 工具本身就是这个 REST 端点的瘦代理
    （`mcp_server/tools/legal_research/legal_research.py` → `POST /legal-research/capability/search`）。
    在 Django 进程里再绕一圈 HTTP 只多一次超时与一次鉴权，没有任何收益。

    检索器自身的失败（无凭证 / 能力降级 / 超时）由 `gather` 统一降级成空证据——
    这里只负责把请求拼对、把结果翻译成 `CaseHit`。
    """
    try:
        from apps.legal_research.schemas.legal_research_schemas import AgentSearchRequestV1
        from apps.legal_research.services.capability.service import LegalResearchCapabilityService
    except ImportError:  # pragma: no cover —— legal_research 是内置 app，正常不会缺
        logger.warning("类案检索未接入：legal_research 不可用")
        return None

    service = LegalResearchCapabilityService()

    def _search(*, query: str, facts: str, limit: int) -> list[CaseHit]:
        payload = AgentSearchRequestV1(
            intent="similar_case",
            facts=(facts or query)[:8000],
            legal_issue=query[:2000],
            target_count=max(1, min(limit, 20)),
            # 整段案情与判决书全文的相似度天然偏低；0.9（短关键词口径）会把结果全筛掉。
            min_similarity_score=0.6,
        )
        response = service.search(payload=payload, user=None)
        hits: list[CaseHit] = []
        for item in response.results:
            if str(item.decision) == "reject":
                continue
            hits.append(
                CaseHit(
                    case_no=str(item.doc_id or ""),
                    court=str(item.court or ""),
                    title=str(item.title or ""),
                    gist=str(item.why_selected or item.snippets.holdings or item.snippets.findings or ""),
                    relevance=float(item.score or 0.0),
                    url=str(item.source_url or ""),
                )
            )
        return hits

    return _search


def default_searcher() -> CaseSearcher | None:
    if _SEARCHER_FACTORY is not None:
        return _SEARCHER_FACTORY()
    return _build_mcp_searcher()


__all__ = [
    "CASE_EVIDENCE_TIMEOUT_SECONDS",
    "HITS_PER_QUERY",
    "MAX_QUERIES",
    "CaseEvidence",
    "CaseHit",
    "CaseSearcher",
    "build_queries",
    "default_searcher",
    "gather",
    "register_searcher",
]
