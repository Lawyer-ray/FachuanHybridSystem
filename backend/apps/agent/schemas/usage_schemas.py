"""成本 / 耗时汇总的响应契约。"""

from __future__ import annotations

from ninja import Schema


class UsageOut(Schema):
    """成本 / 耗时汇总。``error_rate`` 为小数（0.05 = 5%）。"""

    runs: int
    ok_runs: int
    error_runs: int
    cancelled_runs: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    #: 缓存命中 / 写入 token。命中率见 ``cache_hit_rate``。
    #:
    #: 为什么单列：这是验证「AGENTS.md 逐轮字节稳定 → 命中 prompt cache」
    #: 是否生效的唯一仪表。低于预期就说明有东西在每轮改写系统提示词前缀。
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    #: 输入侧缓存命中率（0.0–1.0）。法穿前端用它判断“这轮是不是冷缓存”。
    cache_hit_rate: float = 0.0
    tool_calls: int
    avg_duration_ms: int
    error_rate: float
    #: 本月累计 token（预算口径）
    month_tokens: int = 0
    #: 月度预算（FACHUAN_AGENT_MONTHLY_TOKEN_BUDGET，0=未配置）
    budget_tokens: int = 0
    #: 已用超预算 80% 时为真（前端黄条提醒）
    budget_warn: bool = False


class UsageByAgentOut(Schema):
    """按 agent 后端的成本归因行（``GET /usage/by-agent``）。

    与 :class:`UsageOut` 的 ``/usage`` 是汇总／拆解关系：``total_tokens`` 同口径
    （``input + output + cacheWrite``，**不含** cacheRead）。

    多 agent 上线后同一个模型可能被两个后端同时使用，``by_model`` 分不清钱是谁
    花的——这里按 ``AgentRun.agent_kind`` 拆开（历史空串在 SQL 侧归 ``pi``）。
    """

    #: agent 后端（``pi`` / ``dsh`` / ...）；空串已在 SQL 侧归一为 ``pi``。
    agent_kind: str
    runs: int
    input_tokens: int
    output_tokens: int
    #: 缓存读 / 写 token。命中率见 ``cache_hit_rate``（口径同 ``UsageOut``）。
    cache_read_tokens: int
    cache_write_tokens: int
    total_tokens: int
    cache_hit_rate: float
    #: 后端报错的轮次（失败）。
    failed_runs: int
    #: 用户主动中止的轮次。与 ``failed_runs`` 分开：一个是后端不稳，一个是人喊停。
    cancelled_runs: int
