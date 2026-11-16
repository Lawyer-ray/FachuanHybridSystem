"""记忆检索 —— 语义 + 关键词混合，三层降级。

``search_memories`` 是 ``recall_memory`` 的真实实现。向量召回是核心能力：
律师问「我以前说的格式要求」时，记忆里存的是「文书先给结论」——字面无关、
语义相关，子串匹配永远找不到。
"""

from __future__ import annotations

import logging
import math
import re
from typing import TYPE_CHECKING

from django.db.models import F
from django.utils import timezone

from ...models import AgentMemory
from . import scopes

if TYPE_CHECKING:
    from apps.organization.models import Lawyer

logger = logging.getLogger(__name__)

#: 语义检索绝对下限。低于此值一律不返回（连“最相关”都不可靠）。
#:
#: ## 为什么不能只用一个绝对阈值（实测教训）
#:
#: 原本用单一阈值 0.62。实测 bge-m3 的分布：
#:   相关对（「我问过的写作格式要求」 vs 「文书先给结论再给理由」）= 0.618
#:   无关对（「文书先给结论」 vs 「劳动争议先查仲裁时效」）         = 0.604
#: 差 0.014——任何单一绝对值都会同时错杀相关项或放进无关项。
#: 语义模型的高基线（”任何两句中文都很像“）让绝对阈值在这个量级失效。
MIN_SIMILARITY = 0.52

#: 相对底线：低于本批最高分这个比例的候选不入结果。
#: 真正相关的一组通常集中在高分带，无关项被这个比例自然切掉。
MIN_RELATIVE_RATIO = 0.88

#: 注入时类型优先级（越小越优先）。纠正 > 偏好 > 惯例 > 事实：
#: 「上次那条已过期」必须压过被它推翻的事实，否则注入自相矛盾。
_KIND_PRIORITY: dict[str, int] = {
    AgentMemory.Kind.CORRECTION: 0,
    AgentMemory.Kind.PREFERENCE: 1,
    AgentMemory.Kind.PROCEDURE: 2,
    AgentMemory.Kind.FACT: 3,
    # 操作指引不进正文，不参与短规则排序；给个末位避免影响 _rank_by_usage
    AgentMemory.Kind.PLAYBOOK: 9,
}


# ── 余弦相似度（与 apps/litigation_ai 同口径）──────────────────────────


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def search_memories(
    lawyer: Lawyer,
    query: str,
    *,
    limit: int = 8,
    kinds: list[str] | None = None,
) -> list[tuple[AgentMemory, float]]:
    """语义 + 关键词混合检索（**这是 `recall_memory` 的真实实现**）。

    ## 为什么不能只靠关键词

    律师问「我以前说的格式要求」时，记忆里存的是「文书先给结论」——字面无关、
    语义相关，子串匹配永远抳不到。向量召回是这个能力的核心，不是锦上添花。

    ## 三层降级（每一层都不静默失败）

    1. **向量**：query 与 memory 都有 embedding → 余弦相似度。
    2. **关键词**：向量不可用（embed 未配/调用失败）或记忆尚未 embed 时的
       兜底，取两者较大值。**不静默丢弃**——embed 服务一挂记忆检索不能整体失效。
    3. **无查询词**：按类型优先级 + 命中次数排。

    返回 ``(memory, score)`` 降序。
    """
    qs = scopes.visible_queryset(lawyer)
    if kinds:
        qs = qs.filter(kind__in=kinds)
    candidates = list(qs)
    if not candidates:
        return []

    query = (query or "").strip()
    if not query:
        return [(m, 1.0) for m in _rank_by_usage(candidates, limit)]

    # 懒补向量：历史记忆（自动抽取早期、embed 服务后配）可能没有 embedding。
    # 只在真正要检索时才补，避免写入路径被 embed 服务拖慢。
    _backfill_embeddings([m for m in candidates if not m.embedding])

    query_vec = _embed_query(query)
    scored: list[tuple[AgentMemory, float]] = []
    for memory in candidates:
        score = 0.0
        if query_vec and memory.embedding:
            score = _cosine(query_vec, list(memory.embedding))
        # 关键词兜底：向量不可用或相似度低但字符串命中，取两者较大值
        keyword_hit = _keyword_score(query, memory.content)
        score = max(score, keyword_hit)
        scored.append((memory, score))

    if not scored:
        return []

    # 两道闸：绝对下限（连最相关都不可靠时返回空） + 相对底线（切掉同批里的
    # 长尾）。单独用任一都不行——见 MIN_SIMILARITY 的注释。
    best = max(score for _m, score in scored)
    if best < MIN_SIMILARITY:
        return []
    floor = max(MIN_SIMILARITY, best * MIN_RELATIVE_RATIO)
    scored = [(m, s) for m, s in scored if s >= floor]

    # 注意排序键：(score 降序, hit_count 降序)。不能用 tuple reverse=True——
    # 那会把低命中次数的排前面。
    scored.sort(key=lambda item: (-item[1], -item[0].hit_count))
    top = scored[:limit]
    mark_hit([m for m, _score in top])
    return top


def _backfill_embeddings(memories: list[AgentMemory]) -> None:
    """批量补齐缺失向量（一次 embed 调用，不逐条往返）。

    失败只记日志不抛——检索会自然退化为关键词。
    """
    if not memories:
        return
    texts = [m.content for m in memories]
    try:
        from apps.core.interfaces import ServiceLocator

        service = ServiceLocator.get_llm_service()
        vectors = service.embed_texts(texts, caller="agent.memory.backfill")
    except Exception:
        logger.info("记忆向量批量补齐失败（退化为关键词）", exc_info=True)
        return
    if not vectors or len(vectors) != len(memories):
        return
    updates: list[AgentMemory] = []
    for memory, vector in zip(memories, vectors, strict=False):
        if not vector:
            continue
        memory.embedding = [float(v) for v in vector]
        updates.append(memory)
    if updates:
        AgentMemory.objects.bulk_update(updates, ["embedding"], batch_size=200)
        logger.info("已补齐 %s 条记忆向量", len(updates))


def _keyword_score(query: str, content: str) -> float:
    """关键词命中给出的保守等价分。

    整串命中记 0.95（几乎确定相关），否则按 query 里出现的长词比例折算，
    最高 0.7——低于向量阈值则不会被采纳，避免噪音。
    """
    if not query or not content:
        return 0.0
    if query in content:
        return 0.95
    tokens = [t for t in re.split(r"[\s，,。.、；;：:]+", query) if len(t) >= 2]
    if not tokens:
        return 0.0
    hits = sum(1 for token in tokens if token in content)
    if hits == 0:
        return 0.0
    return min(0.7, 0.35 + 0.35 * hits / len(tokens))


def _rank_by_usage(memories: list[AgentMemory], limit: int) -> list[AgentMemory]:
    """无查询词时按「类型优先级 + 命中次数」排序取前 N。"""
    ranked = sorted(
        memories,
        key=lambda m: (_KIND_PRIORITY.get(m.kind, 9), -m.hit_count, -m.confidence),
    )
    return ranked[:limit]


def _embed_query(text: str) -> list[float] | None:
    """查询向量。embed 未配置 / 调用失败一律返回 None（退化为关键词）。"""
    try:
        from apps.core.interfaces import ServiceLocator

        service = ServiceLocator.get_llm_service()
        vectors = service.embed_texts([text], caller="agent.memory.search")
        if vectors and isinstance(vectors[0], list):
            return [float(v) for v in vectors[0]]
    except Exception:
        logger.info("记忆检索 embed 不可用，退化为关键词匹配", exc_info=True)
    return None


def mark_hit(memories: list[AgentMemory]) -> None:
    """命中计数自增（用于注入排序与团队策展候选池的「共识度」）。"""
    if not memories:
        return
    now = timezone.now()
    AgentMemory.objects.filter(pk__in=[m.pk for m in memories]).update(
        hit_count=F("hit_count") + 1,
        last_hit_at=now,
        # hit 是「被后来的证据重新证实」，刷新衰减锚点但不动 updated_at。
        # 两者混用会让「仅被命中」的记忆永远不衰减，或让「改措辞」无辜续命。
        reinforced_at=now,
    )
