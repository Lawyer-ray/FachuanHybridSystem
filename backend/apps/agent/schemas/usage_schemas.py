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
