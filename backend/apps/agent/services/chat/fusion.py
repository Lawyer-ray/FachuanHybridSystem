"""多路检索结果的确定性融合（Reciprocal Rank Fusion，不花 LLM）。

## 为什么是 RRF，而不是分数加权

各路检索的原始分数量纲完全不同——法条库给 BM25 分、类案给余弦相似度、卷宗
命中可能只有一个页码——用任何固定权重把 0.83 和 12.4 加成同一个数都不可解释，
换一批数据权重就得重调。RRF 只用**名次**：``score(d) = Σ 1 / (rank(d) + k)``。
名次是所有检索路径都有的、口径一致的东西，所以同一份输入在任何机器、任何
调用顺序下都给出同一个结果（这正是本模块存在的全部理由：确定性）。

## k = 61 的来源（0-based enumerate）

haystack 的 ``misc.py`` 用 ``enumerate(documents)`` 取 0-based 名次再加 61，
等价于论文里 1-based 的 ``1/(k + rank)``、``k = 60``。本模块沿用 61 + 0-based：
与既有实现同口径，迁移时不必重算任何历史排序。

## 为什么每一路要先截到 ``D = 2 × final_k``

RRF 衰减得慢：第 0 名是 ``1/61 = 0.0164``，第 100 名仍有 ``1/161 = 0.0062``。
于是「三路都排第 100」的候选（``3 × 0.0062 = 0.0186``）会**压过**「某一路的
第 1 名」（0.0164）——它只是在三路里都出现过，没有任何一路把它排在前面。
先按 ``2 × final_k`` 截断，把这种长尾参与挡在计分之外（10 条结果的场景只看
每路前 20 名）。这是本模块唯一偏离教科书 RRF 的地方，也是必须的一刀。

## 去重键必须是业务键，不是内容哈希

``RetrievalHit.key`` 由上游按业务对象构造（见 :func:`statute_key` /
:func:`case_key` / :func:`page_key`）。用内容哈希会把「两条不同法条、文字恰好
相同」并成一条——法条里重复句式极多（"当事人应当……"），等于凭空丢依据。
反过来，同一条法条在两路里各出现一次时必须并成一条，否则律师会看到三条
内容一样的依据却以为有三份材料支持。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence

from ..adjudication.contracts import FusedHit, RetrievalHit

logger = logging.getLogger(__name__)

#: RRF 平滑常数。61 = 论文的 ``k=60``（1-based）+ 本模块的 0-based 名次。
RRF_K = 61

#: 每一路的截断倍数：``D = LANE_TRUNCATION_FACTOR × final_k``。2 的来源见模块
#: docstring「为什么每一路要先截断」——1 会把所有并列候选砍成单路胜负，3 以上
#: 又让第 21~30 名重新获得决定权，长尾压强会回来。
LANE_TRUNCATION_FACTOR = 2


# ── 业务去重键 ──────────────────────────────────────────────────────────


def statute_key(law_id: int | str, article_no: int | str) -> str:
    """法条去重键 ``law:{law_id}::article:{article_no}``。

    种类前缀不是装饰：计划文档写的 ``law_id::article_no`` 与 ``file_id::page``
    **形状相同**（``3::7`` 既能是"法 3 第 7 条"也能是"文件 3 第 7 页"），同一轮
    同时融合法条与卷宗页码时会撞键，两条互不相干的依据被并成一条。
    """
    law = str(law_id).strip()
    article = str(article_no).strip()
    if not law or not article:
        raise ValueError("法条去重键缺 law_id 或 article_no")
    return f"law:{law}::article:{article}"


def case_key(case_no: str) -> str:
    """案号去重键 ``case:{case_no}``（案号本身就是业务主键，不需要再拆）。"""
    no = (case_no or "").strip()
    if not no:
        raise ValueError("案号去重键缺 case_no")
    return f"case:{no}"


def page_key(file_id: int | str, page: int | str) -> str:
    """卷宗页码去重键 ``file:{file_id}::page:{page}``（同 :func:`statute_key` 加种类前缀）。"""
    file_part = str(file_id).strip()
    page_part = str(page).strip()
    if not file_part or not page_part:
        raise ValueError("页码去重键缺 file_id 或 page")
    return f"file:{file_part}::page:{page_part}"


# ── 融合 ────────────────────────────────────────────────────────────────


def _is_usable(hit: RetrievalHit) -> bool:
    """能否参与计分。

    空业务键（没有可去重身份）和负名次（``rank + 61`` 会穿零甚至变负）都是
    上游退化数据：丢掉它，而不是让它和所有退化命中并成一条、或者抛异常把整轮
    对话打断——融合是加深理解的一层，不能反过来成为单点故障。
    """
    return bool(hit.key) and hit.rank >= 0


def rrf_fuse(lanes: Mapping[str, Sequence[RetrievalHit]], final_k: int) -> list[FusedHit]:
    """把多路检索结果按 RRF 融成一列。

    Args:
        lanes: ``{lane 名: 该路命中}``。lane 名同时是 ``FusedHit.lanes`` 里的
            标识；``RetrievalHit.lane`` 只是冗余标注，不参与计算（映射键才是权威
            ——同一个 ``RetrievalHit`` 对象被两路共用时，统计仍按两路各算一次）。
        final_k: 最终返回多少条；每一路的截断长度是 ``2 × final_k``。

    Returns:
        按完全键 ``(score 降, hit_count 降, best_rank 升, key 升)`` 排序的前
        ``final_k`` 条。写全四项是刻意的：只按 score 排时，两个同分候选的先后
        取决于 dict 插入顺序，同一输入换个调用顺序就换个答案。

    Raises:
        ValueError: ``final_k < 1``（返回 0 条没有意义，通常是调用方算错了）。
    """
    if final_k < 1:
        raise ValueError(f"final_k 必须 ≥ 1，收到 {final_k}")

    limit = LANE_TRUNCATION_FACTOR * final_k
    scores: dict[str, float] = {}
    hit_counts: dict[str, int] = {}
    best_ranks: dict[str, int] = {}
    contributing: dict[str, list[str]] = {}
    dropped = 0

    # 按 lane 名排序后累计：浮点加法不满足结合律，累加顺序必须是规范序，否则
    # 同样的 lane 换个 dict 插入顺序就可能出最后一位小数不同的分数。
    for lane_name in sorted(lanes):
        ordered = sorted(lanes[lane_name], key=lambda hit: (hit.rank, hit.key))[:limit]
        voted: set[str] = set()
        for hit in ordered:
            if not _is_usable(hit):
                dropped += 1
                continue
            if hit.key in voted:
                # 同一路对同一份材料只投一票：取该路内最好的名次（排序后先到者）。
                continue
            voted.add(hit.key)
            scores[hit.key] = scores.get(hit.key, 0.0) + 1.0 / (hit.rank + RRF_K)
            hit_counts[hit.key] = hit_counts.get(hit.key, 0) + 1
            previous = best_ranks.get(hit.key)
            best_ranks[hit.key] = hit.rank if previous is None else min(previous, hit.rank)
            contributing.setdefault(hit.key, []).append(lane_name)

    if dropped:
        logger.warning("rrf_fuse 丢弃 %s 条退化命中（空业务键或负名次）", dropped)

    fused = [
        FusedHit(
            key=key,
            score=score,
            hit_count=hit_counts[key],
            best_rank=best_ranks[key],
            lanes=tuple(contributing[key]),
        )
        for key, score in scores.items()
    ]
    fused.sort(key=lambda hit: (-hit.score, -hit.hit_count, hit.best_rank, hit.key))
    return fused[:final_k]


__all__ = [
    "LANE_TRUNCATION_FACTOR",
    "RRF_K",
    "case_key",
    "page_key",
    "rrf_fuse",
    "statute_key",
]
