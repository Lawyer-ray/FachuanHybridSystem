"""内置后端的注册入口（幂等）。

## 为什么需要 ``ensure_registered``

``AgentConfig.ready()`` 在 app 启动时注册一次，这是主路径。但注册表是**可被
清空的进程内全局状态**（``registry.clear()`` 供测试用），而 ``stream_chat`` 取
后端是纯内存操作、没有任何东西保证「注册表此刻还是满的」。实测踩到：一个测
试文件清空注册表后，后续所有用例的 ``stream_chat`` 全部报
``未知 agent backend: 'pi'``——错误发生在业务入口，而不是注册处，排查方向会被
带偏。

所以取后端之前先调一次本函数：已注册就什么都不做（幂等），被清空过就补回去。
不把注册做成「import 模块的副作用」——那依赖「有人先 import 过它」，而
``stream_chat`` 是运行期才触发的，冷启动后的第一轮对话最容易漏。

## 为什么不做成 import 时自动注册

``apps.agent.backends`` 这个包刻意不 import 任何具体实现（见包 docstring），
否则接入第二个 agent 时 import 本包会连带拉起 pi 的子进程依赖。本模块是显式
入口，谁需要内置后端谁来调。
"""

from __future__ import annotations

import logging

from . import registry

logger = logging.getLogger(__name__)

_registered = False
#: import **失败过**的 kind。用来记「dsh SDK 没装」这类永久性缺失，避免每轮对话
#: 都重试一次 import（异常开销不小，日志也会刷）。注意它不表达「注册过」：
#: 注册表被 ``clear()`` 清空后仍要能重新注册（见 ``_register_dsh``）。
_attempted: set[str] = set()


def ensure_registered() -> None:
    """确保内置后端都在注册表里；已就位则什么都不做。

    用模块级 ``_registered`` 记「本进程已经装过」，避免每次取后端都做一遍
    ``kind in _BACKENDS`` 探测 + import 检查。但注册表被清空后 ``_registered``
    仍是 ``True``——所以真正判断「在不在」要问注册表本身。两个条件都满足才跳过。
    """
    global _registered
    if _registered and "pi" in registry.available_kinds():
        # pi 在就说明主路径可用；dsh / openai-agents 是可选后端，单独补（缺 SDK 的
        # 部署里上面这个条件会一直成立，不能因为可选后端缺席就每次都重跑一遍）。
        _register_dsh()
        _register_openai_agents()
        return

    # 延迟 import：pi_backend 会连带拉起 pi 的 rpc / 池依赖。
    from .pi_backend import PiBackend

    # 幂等注册：注册表可能被 ``clear()`` 清过，也可能已由 ``ready()`` 装好。
    # ``register`` 对重复 kind 会报错，所以先探测再补。
    if "pi" not in registry.available_kinds():
        registry.register(PiBackend())
    _registered = True
    _register_dsh()
    _register_openai_agents()


def _register_dsh() -> None:
    """注册 dsh 后端；SDK 没装时**静默降级**（只登记一次）。

    ## 为什么这里的延迟 import 是硬要求

    ``dsh_backend`` 顶层 ``import deepseek_harness``（理由见该模块注释）。如果本函数
    在模块顶层 import 它，那么**没装 SDK 的部署会在 app 启动时直接崩**——pi 明明
    可用，却因为一个可选后端缺依赖而整个服务起不来。这与「注册 dsh」这个可有可无
    的动作完全不匹配。

    ## 为什么吞 ImportError 而不是往上抛

    dsh 是会话级可选的第二个后端：只有 ``agent_kind="dsh"`` 的会话需要它。缺它就
    让 pi 会话照常跑，是把故障面限制在「选了 dsh 的那些会话」的唯一办法。那些会话
    会在 ``registry.get("dsh")`` 拿到 ``LookupError``，消息里带已注册清单，足以定位。

    ## 为什么 ``_attempted`` 只管「import 失败」而不阻止重注册

    ``ensure_registered`` 每轮对话都调，重试**失败的** import 既无意义（模块不会
    自己出现）又刷日志，所以记在 ``_attempted`` 里跳过。但它**不能**当成「已经
    注册过」的凭据：注册表是可被 ``clear()`` 清空的全局状态（测试大量用到），
    清空后若被 ``_attempted`` 挡住，dsh 会话就会永远报「未知 backend」——
    与 pi 那个踩过的坑一模一样。真正「在不在」只问注册表。
    """
    if "dsh" in registry.available_kinds():
        return
    if "dsh" in _attempted:
        # 上次 import 失败（SDK 没装）。静默跳过，不重复刷日志。
        return

    try:
        from .dsh_backend import DshBackend
    except ImportError:
        # 缺 deepseek-harness-sdk：记录后当作「本部署没有这个后端」。
        _attempted.add("dsh")
        logger.info("deepseek-harness SDK 未安装，dsh 后端不可用（pi 不受影响）")
        return
    registry.register(DshBackend())


def _register_openai_agents() -> None:
    """注册 openai-agents 后端；SDK 没装时**静默降级**（只登记一次）。

    与 :func:`_register_dsh` 同构，理由也相同：``openai_agents_backend`` 顶层
    ``import agents``（SDK 未装时 import 必炸），而这是一个**可选后端**——缺依赖
    不该让 pi 会话跟着起不来。缺包时这些会话在 ``registry.get("openai-agents")``
    拿到 ``LookupError``，消息里带已注册清单，足以定位。

    ``_attempted`` 只记「import 失败过」，**不能**当成「已注册」的凭据：注册表是
    可被 ``clear()`` 清空的全局状态，清空后若被它挡住，该后端会永远报「未知
    backend」（pi 与 dsh 都踩过这个坑）。真正「在不在」只问注册表。
    """
    kind = "openai-agents"
    if kind in registry.available_kinds():
        return
    if kind in _attempted:
        return

    try:
        from .openai_agents_backend import OpenAiAgentsBackend
    except ImportError:
        # 缺 openai-agents：记录后当作「本部署没有这个后端」。
        _attempted.add(kind)
        logger.info("openai-agents SDK 未安装，openai-agents 后端不可用（pi 不受影响）")
        return
    registry.register(OpenAiAgentsBackend())
