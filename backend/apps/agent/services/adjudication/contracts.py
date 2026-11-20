"""判定与融合的契约类型（本文件冻结，父会话独占）。

## 为什么同时有 pydantic 与 dataclass

- ``Review`` 一族要直接当 ``POST /agent/sessions/{id}/review`` 的响应体，走 pydantic
  才有字段校验与 OpenAPI 生成；
- ``RetrievalHit`` / ``FusedHit`` / ``EquivalenceCluster`` 是纯计算结果，进图也进测试
  断言，用 frozen dataclass：可哈希、可比较、改不动——融合的确定性靠"没人能改它"。

## 多 lane 并行期间的硬规则

1. 本文件只读（lane 不得修改签名）。
2. 字段增删改名必须四处同一次提交内对齐：本文件 → 前端
   ``frontend/src/features/copilot/adjudication-types.ts`` → 计划文档附录 A →
   消费方。
3. 本文件**不 import Django 模型、不 import services**：纯函数单测要能直接 import，
   否则每个 lane 都得先起 Django。
4. ``extra="forbid"`` 是故意的：多写一个字段就报错，比"悄悄多了个没人读的字段"好。

## 三种"没结论"必须是三种不同的东西

| 情况 | 表示 | 后果 |
|:--|:--|:--|
| 判了，通过 | ``criteria_met=True`` | 进分子 |
| 判了，不通过 | ``criteria_met=False`` | 进分母，不进分子 |
| 判不了（解析失败/超时/协议偏离） | ``criteria_met=None`` + ``unscored_reason`` | **不进分母**，也不当成答错 |

把第三种折算成 ``False``，等于"模型没答上来就算它答错"——这正是校准里最容易被骂的偏差。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: 判定"没结论"的封闭原因集。新增原因要同时改本常量与计划文档附录 A。
CRITERIA_UNSCORED_REASONS: frozenset[str] = frozenset(
    {
        "parse_failed",  # 解析不出判定（含"末行翻供"）
        "protocol_deviation",  # 给了未开启的选项（如没开 partial 却回 P）
        "timeout",  # 请求超时
        "judge_error",  # judge 侧 4xx/5xx、配额
        "empty_response",  # 空正文
    }
)

#: 评审阶段。``shadow`` = 只展示、不参与任何自动动作（B2.5 之前只有这一档）。
REVIEW_STAGES: frozenset[str] = frozenset({"shadow"})


class CriteriaVerdict(BaseModel):
    """一条 rubric 对一栏的一次判定（N 栏 × M 条 = N×M 条）。"""

    model_config = ConfigDict(extra="forbid")

    rubric_id: str
    lane: str
    #: ``None`` = 判不了；见模块 docstring 的三态表。
    criteria_met: bool | None = None
    explanation: str = ""
    #: 支撑该判定的原文片段（前端"点开分数看证据"的数据源）。
    evidence_quote: str = ""
    judge_model: str = ""
    #: 实际调用次数（含重试）；用于成本归因与"这家一直失败"的告警。
    attempts: int = 0
    #: 仅当 ``criteria_met is None`` 时有值，取值见 ``CRITERIA_UNSCORED_REASONS``。
    unscored_reason: str = ""


class LaneReview(BaseModel):
    """一栏的汇总。"""

    model_config = ConfigDict(extra="forbid")

    lane: str
    #: 有效票数 = True 的条数 + False 的条数（判不了与失败都不算）。
    valid: int = 0
    #: 其中通过的条数。
    yes: int = 0
    #: ``None`` = 该栏一条有效票都没有（**不是 0 分**）。
    score: float | None = None
    #: 一句理由（≤40 字），给汇总卡用；不许写"综上所述"这类空话。
    one_line: str = ""


class Review(BaseModel):
    """一轮多答的评审结果（一次 ``/review`` 的完整产物）。"""

    model_config = ConfigDict(extra="forbid")

    review_id: str
    session_id: str
    turn: int
    #: 用了哪套 rubric、哪一版。**必须记**：离线校准要按版本归因，否则改了 rubric 之后
    #: 历史评审与新一轮评测混在一起，kappa 算出来是两套标准混出来的假数。
    rubric_id: str = ""
    rubric_version: str = ""
    stage: Literal["shadow"] = "shadow"
    lanes: list[LaneReview] = Field(default_factory=list)
    verdicts: list[CriteriaVerdict] = Field(default_factory=list)
    #: 一句话导航（"A、C 结论一致；B 主张先催告"），不是法律结论。
    headline: str = ""
    #: 本轮提到但检索/核验没兜住的东西（如"引《X 办法》第 7 条，本轮无核验命中"）。
    unverified: list[str] = Field(default_factory=list)
    #: 评审自身的 token 成本（与三栏的 usage 分开记，别混进生成成本）。
    tokens: dict[str, int] = Field(default_factory=dict)


@dataclass(frozen=True)
class RetrievalHit:
    """一路检索的一条命中（融合的输入单元）。

    ``key`` 是**业务去重键**而不是内容指纹：``law_id::article_no`` / ``case_no`` /
    ``file_id::page``。用内容哈希会把"两条不同法条但文字相同"并成一条——法律场景下
    这会直接丢依据。
    """

    key: str
    lane: str
    #: 该路内的名次（0 起）。RRF 只吃名次，不吃原始分。
    rank: int
    title: str = ""
    raw_score: float | None = None


@dataclass(frozen=True)
class FusedHit:
    """融合结果。排序键必须完全确定，否则同一输入两次跑出来顺序不同。"""

    key: str
    #: sum(1 / (rank + 61))；61 而非 60 见 haystack misc.py 的 0-based 说明。
    score: float
    hit_count: int
    best_rank: int
    lanes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class EquivalenceCluster:
    """ "这几份答案其实是同一个立场"。

    ``tie=True`` 表示**没有可判定的代表**（全异或平票）。这时上层必须显示"三份各说
    各的"，绝不允许悄悄回落成第一条——那会让律师以为自己看到的是共识。
    """

    member_ids: tuple[str, ...]
    representative_id: str
    tie: bool = False


#: 各 lane 必须实现的公开入口（评审时逐条核对；改了要同步改计划文档）。
INTEGRATION_POINTS = """
A3 判定内核  backend/apps/agent/services/review/
    rubric.py        load_rubric(rubric_id: str) -> list[RubricItem]
                     settle(items, verdicts) -> LaneScore      # 正分进分母、负分只扣分子
    judge_prompt.py  build_prompt(channel, nonce, *, task, submission, criterion) -> str
                     parse_verdict(text) -> ParsedVerdict      # 三态 + 末行翻供
    judge_client.py  judge_once(...) / judge_with_retry(...)    # 上限 2 次 + 退避 + 换 judge
    jury.py          run_jury(...) -> Review
    api              POST /agent/sessions/{session_id}/review -> Review

A4 确定性融合  backend/apps/agent/services/chat/
    fusion.py        rrf_fuse(lanes: Mapping[str, Sequence[RetrievalHit]], final_k: int) -> list[FusedHit]
    equivalence.py   cluster_answers(ids, entails) -> list[EquivalenceCluster]
    citation_check.py verify_references(...) -> list[str]       # 返回 unverified 文案
"""
