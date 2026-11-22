"""综合结论在会话转录里的 ``agent_kind``（后端唯一定义处）。

单独成一个只有常量的叶子模块：转录的各条读路径（评审取候选、上下文回放、记忆抽取、
重生成）都要排除它，而 ``synthesis/store.py`` 会拉起 ``chat`` 包与 ``review/store``，
从这些模块顶层 import 它会成环。``store.SYNTHESIS_AGENT_KIND`` 是这里的再导出。

前端镜像：``frontend/src/features/copilot/domain/dual.ts`` 的 ``SYNTHESIS_AGENT_KIND``（必须同值）。
"""

from __future__ import annotations

#: 用它而不是"执行综合的那个 agent"（如 ``pi``）：写 ``pi`` 会和那一栏自己的回答
#: 混在同一条 lane 里（前端按 kind 合并同轮 assistant 消息，会把原答案与综合稿拼成
#: 一段），而"每栏一条"的统计口径也会失真。独立取值让综合既能在转录里被检索/引用/
#: 继续追问，又不会被算成某一栏的回答。
SYNTHESIS_AGENT_KIND = "synthesis"

__all__ = ["SYNTHESIS_AGENT_KIND"]
