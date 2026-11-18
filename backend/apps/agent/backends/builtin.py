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

from . import registry

_registered = False


def ensure_registered() -> None:
    """确保内置后端都在注册表里；已就位则什么都不做。

    用模块级 ``_registered`` 记「本进程已经装过」，避免每次取后端都做一遍
    ``kind in _BACKENDS`` 探测 + import 检查。但注册表被清空后 ``_registered``
    仍是 ``True``——所以真正判断「在不在」要问注册表本身。两个条件都满足才跳过。
    """
    global _registered
    if _registered and "pi" in registry.available_kinds():
        return

    # 延迟 import：pi_backend 会连带拉起 pi 的 rpc / 池依赖。
    from .pi_backend import PiBackend

    # 幂等注册：注册表可能被 ``clear()`` 清过，也可能已由 ``ready()`` 装好。
    # ``register`` 对重复 kind 会报错，所以先探测再补。
    if "pi" not in registry.available_kinds():
        registry.register(PiBackend())
    _registered = True
