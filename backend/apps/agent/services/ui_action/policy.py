"""UI 动作的部署级风险策略 —— 出事故时改环境变量就能加严，不用改代码发版。

## 为什么 ``risk`` 之外还需要一层策略

清单里的 ``risk`` 是**代码即策略**：它随版本发布，改一次要评审、回归、发版。事故现场需要的
却是「立刻把这个动作全环境关掉」或「今天所有动作都必须人工确认」。所以这一层只读两个环境
变量、只做两件事：

- **floor**（``FACHUAN_UI_ACTION_RISK_FLOOR``）：把清单档位整体抬到某个下限，
  生效档 = ``max(清单档, floor)``。这就是 Claude Code「任一层 deny，任何层都不能 allow」的
  最小版：部署层**只能加严**——清单里的 ``confirm`` 不会因为 ``floor=safe`` 被降级。
  ``mcp_server/tools/ui/register.py`` 用生效档决定 ``ToolAnnotations``，所以被抬档的
  ``safe`` 动作会真的弹审批卡，而不是只在日志里说一句「今天很严」。
- **deny**（``FACHUAN_UI_ACTION_DENY``）：逗号分隔的动作名。命中的动作**不注册**成 MCP
  工具（模型调不到），也不出现在批量可用清单里（``batch.validate_batch``）。比 floor 更硬的
  一刀：出事故时先 deny 那一条，再排查。

## 为什么本模块不能 import manifest

``manifest`` 要能被 ``python -m apps.agent.services.ui_action --ts`` 在无 Django settings 的
进程里 import（见它的模块 docstring），而它又要用本模块的 :func:`effective_risk` 派生
``CONFIRM_ACTION_NAMES``。这里反过来 import manifest 就是循环 import，且会把「策略也认识
动作表」变成第二个真相。所以 :func:`effective_risk` 只吃**结构**（有 ``.name`` / ``.risk``
属性的对象），清单类型只在 ``TYPE_CHECKING`` 下用于注解。

## 为什么每次都重读环境变量，不缓存

部署语义是「改环境变量 + 重启进程」，重启后缓存与否没有区别；而同一个进程里（测试、
``caplog`` 排查）切换变量必须立刻生效——模块级缓存只会让用例互相污染，还会让「deny 了却
没生效」这种事故多一个可能原因。四个动作的规模下重读一次 ``os.environ`` 的成本可以忽略，
**别加 ``lru_cache``**。
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable
from typing import TYPE_CHECKING, Protocol, cast

if TYPE_CHECKING:
    from .manifest import UiActionRisk

logger = logging.getLogger(__name__)

#: 三档风险的偏序（数字越大越严）。``effective_risk`` 取 ``max``，所以这个顺序就是安全边界。
RISK_ORDER: dict[str, int] = {"safe": 0, "confirm": 1, "guarded": 2}
#: 反向查表（下标 = 档位）：比较完的整数要还原成档位名。
_RISK_BY_RANK: tuple[str, ...] = tuple(sorted(RISK_ORDER, key=RISK_ORDER.__getitem__))

#: 部署级下限环境变量：``safe`` | ``confirm`` | ``guarded``，默认 ``safe``。
FLOOR_ENV = "FACHUAN_UI_ACTION_RISK_FLOOR"
#: 默认下限。默认 ``safe`` 表示「部署层没有额外要求」，行为与没有本模块时一致。
DEFAULT_FLOOR = "safe"
#: 部署级禁用名单环境变量：逗号分隔的动作名，默认空（什么都不禁）。
DENY_ENV = "FACHUAN_UI_ACTION_DENY"


class RiskRated(Protocol):
    """``effective_risk`` / ``escalated`` 只需要「名字 + 清单档位」两条属性。

    用结构化协议而不是 ``UiAction``：本模块不能 import manifest（理由见模块 docstring），
    而合成动作、别的调用方传进来的对象只要形状对就该能用。
    """

    @property
    def name(self) -> str:
        """动作名（只用于告警文案，不参与判定）。"""
        ...

    @property
    def risk(self) -> str:
        """清单里声明的风险档。"""
        ...


def risk_floor() -> str:
    """当前部署级风险下限（默认 ``safe``；非法值 warn 后按 ``safe``）。

    ``ui_action_mode`` 同口径：环境变量写错一个字符不该让整条通道失效，所以兜底而不是抛。
    空串视为「没设」（``FACHUAN_UI_ACTION_RISK_FLOOR=`` 常见于模板变量展开），不告警。
    """
    raw = (os.environ.get(FLOOR_ENV, DEFAULT_FLOOR) or "").strip().lower()
    if not raw:
        return DEFAULT_FLOOR
    if raw in RISK_ORDER:
        return raw
    logger.warning("非法 %s=%r，按 %s 处理", FLOOR_ENV, raw, DEFAULT_FLOOR)
    return DEFAULT_FLOOR


def denied_action_names() -> frozenset[str]:
    """部署级禁用名单（逗号分隔、去空白、精确匹配动作名）。

    名单里拼错/已下线的名字**不在这里报错**：本模块不认识清单（不能 import manifest）。
    「名单里有没有真的动作」由 :func:`unknown_denied_names` 交给认识清单的调用方告警。
    """
    raw = os.environ.get(DENY_ENV, "")
    return frozenset(name.strip() for name in raw.split(",") if name.strip())


def is_denied(name: str) -> bool:
    """该动作是否被部署级名单禁用（禁用 = 不注册成工具、不进批量可用清单）。"""
    return name in denied_action_names()


def unknown_denied_names(known_names: Iterable[str]) -> tuple[str, ...]:
    """``deny`` 名单里不在 ``known_names`` 中的名字（拼写错误或动作已下线）。

    只返回不抛：一个拼错的名字不该让 MCP 起不来，但也不能静默——调用方（注册器）负责
    打一条 warning，否则运维会以为「已经关掉了」而实际什么都没发生。
    """
    return tuple(sorted(denied_action_names() - set(known_names)))


def effective_risk(action: RiskRated) -> UiActionRisk:
    """生效风险档 = ``max(清单档, floor)`` —— 只升不降。

    清单档位写错（``typing`` 管不到运行期，如 ``"safe "``）时按 ``guarded`` 处理并告警：
    一个拼错的档位绝不能变成「不经审批的放行」。
    """
    declared = str(action.risk)
    declared_rank = RISK_ORDER.get(declared)
    if declared_rank is None:
        logger.warning(
            "动作 %s 的风险档 %r 不在 %s 里，按 guarded 处理",
            action.name,
            declared,
            tuple(RISK_ORDER),
        )
        declared_rank = RISK_ORDER["guarded"]
    rank = max(declared_rank, RISK_ORDER[risk_floor()])
    return cast("UiActionRisk", _RISK_BY_RANK[rank])


def escalated(action: RiskRated) -> bool:
    """生效档是否高于清单档（被部署级 floor 抬过）。

    存在的意义是**可解释**：一个清单里的 ``safe`` 动作突然弹审批卡时，日志要能回答
    「为什么」，而不是让值班的人去猜是不是判级坏了。
    """
    declared_rank = RISK_ORDER.get(str(action.risk), RISK_ORDER["guarded"])
    return RISK_ORDER[effective_risk(action)] > declared_rank
