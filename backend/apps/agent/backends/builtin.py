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
        _register_antigravity()
        _register_claude_agent()
        _register_opencode()
        _register_codex()
        _register_cline()
        _register_qoder()
        return

    # 延迟 import：pi_backend 会连带拉起 pi 的 rpc / 池依赖。
    from .pi_backend import PiBackend

    # 幂等注册：注册表可能被 ``clear()`` 清过，也可能已由 ``ready()`` 装好。
    # ``register`` 对重复 kind 会报错，所以先探测再补。
    if "pi" not in registry.available_kinds():
        registry.register(PiBackend())
    _registered = True
    _register_dsh()
    _register_antigravity()
    _register_claude_agent()
    _register_opencode()
    _register_codex()
    _register_cline()
    _register_qoder()


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


def _register_antigravity() -> None:
    """注册 antigravity 后端；SDK 没装时**静默降级**（只登记一次）。

    与 :func:`_register_dsh` / :func:`_register_openai_agents` 同构，理由也相同：
    ``antigravity_backend`` 顶层 ``import google.antigravity``，而这是一个**可选
    后端**——缺依赖不该让 pi 会话跟着起不来。缺包时这些会话在
    ``registry.get("antigravity")`` 拿到 ``LookupError``（消息里带已注册清单），
    前端 ``/backends`` 也会如实标成不可用。

    ``_attempted`` 只记「import 失败过」，**不能**当成「已注册」的凭据：注册表是
    可被 ``clear()`` 清空的全局状态，清空后若被它挡住，该后端会永远报「未知
    backend」（pi / dsh / openai-agents 都踩过这个坑）。真正「在不在」只问注册表。
    """
    kind = "antigravity"
    if kind in registry.available_kinds():
        return
    if kind in _attempted:
        return

    try:
        from .antigravity_backend import AntigravityBackend
    except ImportError:
        # 缺 google-antigravity（含平台二进制 wheel）：记录后当作「本部署没有这个后端」。
        _attempted.add(kind)
        logger.info("google-antigravity SDK 未安装，antigravity 后端不可用（其它后端不受影响）")
        return
    registry.register(AntigravityBackend())


def _register_claude_agent() -> None:
    """注册 claude-agent 后端；SDK 没装时**静默降级**（只登记一次）。

    与其它可选后端同构。注意：``claude_agent_backend`` 顶层**不** import
    ``claude_agent_sdk``（差异于 dsh / openai-agents / antigravity 的写法），
    因为它只需要在 ``stream()`` 里用到 SDK 的类型；这样即使 SDK 缺失，模块本身
    的纯函数（base_url 归一化、模型过滤、能力声明）仍可被测试直接引用。
    所以这里的 import 成功**不代表** SDK 已装——真正的可用性由 ``stream()``
    的延迟 import 决定，而 ``/backends`` 前端会据运行时报错标不可用。

    为了让「SDK 没装」也能在这里就被识别（而不是等用户点进去才失败），额外
    做一次 ``find_spec`` 探测。
    """
    kind = "claude-agent"
    if kind in registry.available_kinds():
        return
    if kind in _attempted:
        return

    from importlib.util import find_spec

    if find_spec("claude_agent_sdk") is None:
        _attempted.add(kind)
        logger.info("claude-agent-sdk 未安装，claude-agent 后端不可用（其它后端不受影响）")
        return

    from .claude_agent_backend import ClaudeAgentBackend

    registry.register(ClaudeAgentBackend())


def _register_opencode() -> None:
    """注册 opencode 后端；二进制没装时**静默降级**（只登记一次）。

    与其它可选后端同构。差异只有一处：可用性判据不是 Python 包，而是
    ``opencode`` 可执行文件（``shutil.which`` 一次，不拉进程）——它是个
    独立 CLI，装没装与 Python 环境无关。

    ``_attempted`` 只记「探测失败过」，**不能**当成「已注册」的凭据：注册表是
    可被 ``clear()`` 清空的全局状态（测试大量用到），清空后若被它挡住，该后端会
    永远报「未知 backend」（pi / dsh / openai-agents / antigravity / claude-agent
    都踩过这个坑）。真正「在不在」只问注册表。
    """
    kind = "opencode"
    if kind in registry.available_kinds():
        return
    if kind in _attempted:
        return

    from .opencode_backend import OpenCodeBackend, is_available

    if not is_available():
        _attempted.add(kind)
        logger.info("未找到 opencode 可执行文件，opencode 后端不可用（其它后端不受影响）")
        return

    registry.register(OpenCodeBackend())


def _register_codex() -> None:
    """注册 codex 后端；可执行文件缺失时静默降级（只登记一次）。

    与 opencode 同构：判据是可执行文件而不是 Python 包。``_attempted`` 只记
    「探测失败过」，不能当成「已注册」——注册表可被 ``clear()`` 清空（测试大量用到），
    清空后若被它挡住，该后端会永远报「未知 backend」。
    """
    kind = "codex"
    if kind in registry.available_kinds():
        return
    if kind in _attempted:
        return

    from .codex_backend import CodexBackend, is_available

    if not is_available():
        _attempted.add(kind)
        logger.info("未找到 codex 可执行文件，codex 后端不可用（其它后端不受影响）")
        return

    registry.register(CodexBackend())


def _register_qoder() -> None:
    """注册 qoder 后端；SDK 没装时静默降级（只登记一次）。

    与 claude-agent 同构：``qoder_backend`` 顶层**不** import ``qoder_agent_sdk``
    （它只在 ``stream()`` 与少数几个函数里延迟 import），所以模块能 import 成功
    并不代表 SDK 已装——这里额外做一次 ``find_spec`` 探测，让「没装」在
    ``/backends`` 就能问出来，而不是等用户点进去才失败。

    ``_attempted`` 只记「探测失败过」，不能当成「已注册」——注册表可被
    ``clear()`` 清空（测试大量用到），清空后被它挡住会永远报「未知 backend」。
    """
    kind = "qoder"
    if kind in registry.available_kinds():
        return
    if kind in _attempted:
        return

    from .qoder_backend import QoderBackend, is_available

    if not is_available():
        _attempted.add(kind)
        logger.info("qoder-agent-sdk 未安装，qoder 后端不可用（其它后端不受影响）")
        return

    registry.register(QoderBackend())


def _register_cline() -> None:
    """注册 cline 后端；node 或桥脚本缺失时静默降级（只登记一次）。

    判据是「node 在 + 桥脚本在」，与 opencode/codex 同构（看可执行文件而不是
    Python 包）。``@cline/core`` 本身不在这里探测：它由桥在运行期按
    ``FACHUAN_CLINE_SDK`` 解析，缺了会在第一轮报 UNAVAILABLE（文案里带路径）。

    ``_attempted`` 只记「探测失败过」，不能当成「已注册」——注册表可被
    ``clear()`` 清空（测试大量用到），清空后被它挡住会永远报「未知 backend」。
    """
    kind = "cline"
    if kind in registry.available_kinds():
        return
    if kind in _attempted:
        return

    from .cline_backend import ClineBackend, is_available

    if not is_available():
        _attempted.add(kind)
        logger.info("未找到 node 或 cline 桥脚本，cline 后端不可用（其它后端不受影响）")
        return

    registry.register(ClineBackend())
