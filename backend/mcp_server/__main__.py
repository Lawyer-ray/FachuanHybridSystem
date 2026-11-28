"""``python -m mcp_server`` 入口。

MCP stdio 协议把 **stdout 当作 JSON-RPC 通道**，因此这里必须做到两件事：

1. **先初始化 Django，再导入 server。** 工具模块会导入 Django 模型，缺 ``django.setup()``
   会在导入期抛 ``AppRegistryNotReady: Apps aren't loaded yet``；子进程随即秒退，客户端只看到
   "Connection closed"。同时要自己补 ``sys.path``——settings 实际位于
   ``backend/apiSystem/apiSystem/``，而子进程由 ``StdioTransport(cwd=BACKEND_DIR)`` 启动，
   不保证带 ``PYTHONPATH``。
2. **bootstrap 期间把 stdout 改道到 stderr。** ``apiSystem.settings`` 里的
   ``get_logging_config()`` 会把 console handler 的 stream 固定成**当时**的 ``sys.stdout``，
   而 Django 启动会打出几十行 INFO。若留在 stdout，这些行会插进 JSON-RPC 流里导致握手失败。
   在 ``django.setup()`` 之前改道，handler 便永久指向 stderr；之后再把 stdout 还给
   ``mcp.run()``（handler 持有的是对象引用，恢复 ``sys.stdout`` 不影响它）。

HTTP 模式（streamable-http）额外支持**蓝绿切换**，全由环境变量控制：

- ``FACHUAN_MCP_HTTP_PORT`` 的监听用 ``SO_REUSEPORT`` 显式建立，候选实例因此能与
  旧实例**同时**绑同一端口（消掉「杀掉旧进程再等冷启动」的停机窗口）；
- ``FACHUAN_MCP_SIDE_PORT`` 让候选额外监听一个**只有它自己**的端口，供
  ``scripts/shared_mcp.sh bluegreen`` 做确定性就绪校验（primary 上的连接会在新旧
  实例间分摊，拿它判就绪可能打到旧进程）；
- ``FACHUAN_MCP_GRACEFUL_TIMEOUT`` 决定退休实例等在飞请求的上限（默认 240 秒，
  对齐单次工具调用上限 200 秒）；
- 未配置 side 端口时，启动前先用一个**不带 SO_REUSEPORT** 的探针试绑 primary：
  已有实例在监听就拒绝启动。没有这道探针，SO_REUSEPORT 会让「第二个实例」不再
  EADDRINUSE 秒退，而是绑成功并悄悄分走一半流量。

工具面指纹与重启判据见 ``mcp_server/tool_face.py``。
"""

from __future__ import annotations

import errno
import logging
import os
import socket
import sys
from pathlib import Path

#: 日志器名必须写死成 ``mcp_server.__main__``，不能用 ``__name__``。
#:
#: 为什么：入口是以 ``python -m mcp_server`` 跑的，此时 ``__name__ == "__main__"``，
#: 于是 ``logging.getLogger("__main__")`` 落到 **root logger**（Django LOGGING 里 root
#: 是 WARNING）——启动时那句 ``tool_face=…`` 会被直接丢弃。实测：4 个实例的日志里
#: 都没有这行，而排障（“线上跑的是哪份工具面”）恰恰只能靠它。
_idiomatic_logger_name = "mcp_server.__main__"
logger = logging.getLogger(_idiomatic_logger_name)

BACKEND_DIR = Path(__file__).resolve().parents[1]
#: settings 的导入根，即 ``backend/apiSystem/apiSystem/settings.py`` 所在的上一级
API_SYSTEM_ROOT = BACKEND_DIR / "apiSystem"

#: 退休实例等在飞请求的上限（秒）。默认 240 的理由：MCP 客户端单次工具调用上限是
#: 200 秒（``apps/agent/backends/toolface/constants.py:49``），旧默认 30 秒比它还短，
#: 蓝绿切换时正在跑的长工具（威科检索/企业数据降级链等实测可到 ~120s，生成类 180s）
#: 会在部署瞬间被硬切——那不是「优雅退出」，是部署自带的失败。留 40 秒余量给收尾。
#: 延迟代价只落在「退休实例多活几分钟」上：``make mcp stop`` 不受影响（脚本等 5 秒
#: 后直接 ``kill -9``）。``0`` 表示沿用 uvicorn 默认（无限等，旧实例可能永挂）。
GRACEFUL_TIMEOUT_ENV = "FACHUAN_MCP_GRACEFUL_TIMEOUT"
DEFAULT_GRACEFUL_TIMEOUT_SECONDS = 240

#: 候选实例额外的监听端口（只给它的就绪校验用，见 :func:`_bind_listen_socket`）。
SIDE_PORT_ENV = "FACHUAN_MCP_SIDE_PORT"


def _bootstrap_django() -> None:
    """补 sys.path → 指定 settings → 初始化 Django（期间 stdout 改道 stderr）。"""
    for path in (str(API_SYSTEM_ROOT), str(BACKEND_DIR)):
        if path not in sys.path:
            sys.path.insert(0, path)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")

    import django

    real_stdout = sys.stdout
    sys.stdout = sys.stderr
    try:
        django.setup()
    finally:
        sys.stdout = real_stdout


def _graceful_timeout() -> int | None:
    """``FACHUAN_MCP_GRACEFUL_TIMEOUT`` → uvicorn 的 ``timeout_graceful_shutdown``。

    未设（或设成空）用默认 240 秒；``0``/负数返回 ``None`` = 沿用 uvicorn 默认（无限等）。
    非法值回默认并 warning：配置写错时「略久一点」比「立刻失效」安全得多。
    """
    raw = os.environ.get(GRACEFUL_TIMEOUT_ENV, "").strip()
    if not raw:
        return DEFAULT_GRACEFUL_TIMEOUT_SECONDS
    try:
        seconds = int(raw)
    except ValueError:
        logger.warning("%s=%r 不是整数秒，回退默认 %ss", GRACEFUL_TIMEOUT_ENV, raw, DEFAULT_GRACEFUL_TIMEOUT_SECONDS)
        return DEFAULT_GRACEFUL_TIMEOUT_SECONDS
    return seconds if seconds > 0 else None


def _side_port() -> int | None:
    """``FACHUAN_MCP_SIDE_PORT``（未设/非法则不加 side 监听）。"""
    raw = os.environ.get(SIDE_PORT_ENV, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        logger.warning("%s=%r 不是端口号，本次不监听 side 端口", SIDE_PORT_ENV, raw)
        return None


def _probe_conflict(host: str, port: int) -> bool:
    """``host:port`` 上是不是**已经有实例在监听**（只探测，不占用）。

    为什么需要它：本入口给 primary 开了 SO_REUSEPORT（蓝绿并绑的前提），代价是
    「第二个实例」不再像改造前那样 ``EADDRINUSE`` 秒退，而是**绑成功并分走一半流量**
    （请求随机落到两份进程，一份跑旧代码）。三条真实入口：蓝绿脚本在候选就绪与切换
    之间被杀（候选有 nohup 会活下来）、两个终端同时跑、systemd 与手工启动撞车。
    所以非蓝绿启动前先做一次**不带 SO_REUSEPORT** 的试绑：能绑上（随即 close）=
    没有别的实例；``EADDRINUSE`` = 有，由调用方拒绝启动。

    ``SO_REUSEADDR`` 要设而 ``SO_REUSEPORT`` 绝不能设：前者只放宽「上一个实例留下的
    TIME_WAIT 连接」，不设会让正常的 stop→start 重启被误判成冲突；后者正是被探测的
    共享开关——带它试绑必然成功，探针就永远失效。
    """
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    probe = socket.socket(family, socket.SOCK_STREAM)
    try:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind((host, port))
    except OSError as exc:
        return exc.errno == errno.EADDRINUSE
    finally:
        # 探针是「借端口问一句」：成功与否都必须立刻释放，否则它自己就成了占位者。
        probe.close()
    return False


def _bind_listen_socket(host: str, port: int) -> socket.socket:
    """建一个已 bind + listen 的监听 socket，带 SO_REUSEPORT。

    **为什么必须 SO_REUSEPORT**：它让候选实例与旧实例**同时**绑定同一个 primary 端口，
    两边都能服务，于是「改完代码上车」不再有「先杀旧、再等冷启动」的停机窗口。
    没有它，第二次 bind 直接 EADDRINUSE。

    **为什么先 listen**：从 bind 到 uvicorn 事件循环接管之间若只 bind 不 listen，内核
    不会把新连接分给这个 socket（表现为瞬时连接被重置）；asyncio 接管时会再 listen
    一次（只更新 backlog），幂等。
    """
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        sock.bind((host, port))
        sock.listen(2048)
    except OSError:
        sock.close()
        raise
    return sock


def main() -> None:
    _bootstrap_django()

    # 传输方式由环境变量决定（默认 stdio，保持既有行为完全不变）：
    # - stdio：每个 pi 进程各起一份（实测 ~225MB/份、冷启动 ~6s）
    # - streamable-http：一份常驻，多个 pi 共享（apps/agent 高并发模式）。
    #   HTTP 模式必须包上 RequestAuthMiddleware：把请求头里的律师身份透传给
    #   上游 REST API，否则所有 agent 工具调用都退化为超管服务账号
    #   （confused deputy，见 mcp_server/identity.py）。
    transport = os.environ.get("FACHUAN_MCP_TRANSPORT", "stdio").strip().lower()
    if transport in {"streamable-http", "http"}:
        import uvicorn

        from mcp_server.identity import RequestAuthMiddleware
        from mcp_server.server import mcp  # http 模式 stdout 不是协议通道,无需改道窗口
        from mcp_server.tool_approval_gate import install_tool_approval_gate
        from mcp_server.tool_face import tool_face_fingerprint, tool_face_from_mcp
        from mcp_server.tool_tier_gate import install_tool_tier_gate

        # 按 X-Fachuan-Tool-Tier 裁剪 tools/list（stdlib 请求头 → 客户端自选工具面）。
        # install 幂等：共享进程里重复调用不会把中间件挂两遍。
        install_tool_tier_gate(mcp)
        # 服务端审批闸门（入口 B）：dsh / openai-agents 没有工具调用钩子，
        # 高危工具只能在 MCP 这一层拦；同样幂等。
        install_tool_approval_gate(mcp)

        host = os.environ.get("FACHUAN_MCP_HTTP_HOST", "127.0.0.1").strip() or "127.0.0.1"
        try:
            port = int(os.environ.get("FACHUAN_MCP_HTTP_PORT", "8011"))
        except ValueError:
            port = 8011
        app = RequestAuthMiddleware(mcp.streamable_http_app())
        graceful_timeout = _graceful_timeout()
        side_port = _side_port()

        if not hasattr(socket, "SO_REUSEPORT"):
            # 平台没有 SO_REUSEPORT（极老内核 / 非 POSIX）：退回单实例绑端口。
            # 蓝绿切换在本机因此不可用，但启动行为与改造前完全一致。
            logger.warning("本平台 socket 无 SO_REUSEPORT：单实例启动，共享 MCP 蓝绿切换不可用")
            uvicorn.run(app, host=host, port=port, timeout_graceful_shutdown=graceful_timeout)
            return

        # 恢复「第二个实例立刻失败」：SO_REUSEPORT 让重复启动不再报错而是分摊流量，
        # 探针把它拉回 fail-fast。配了 side 端口 = 蓝绿候选，它本来就要与旧实例并绑
        # primary（就绪后由脚本把旧实例退休），必须跳过探针。
        if side_port is None and _probe_conflict(host, port):
            logger.error(
                "已有实例在监听 %s:%s；拒绝重复启动（会分摊流量）。要零停机切换请用 make mcp-bluegreen",
                host,
                port,
            )
            sys.exit(1)

        try:
            sockets = [_bind_listen_socket(host, port)]
            if side_port is not None:
                sockets.append(_bind_listen_socket(host, side_port))
        except OSError as exc:
            # 端口被占是最常见的启动失败：把 primary/side 和具体错因一起打出来，
            # 免得运维只看到一行 EADDRINUSE 去猜是哪个端口。
            logger.error("监听失败 primary=%s:%s side=%s: %s", host, port, side_port, exc)
            raise

        # 工具面指纹进启动日志：线上排障时一眼看出「这个进程跑的是哪份工具面」，
        # 不用再去猜它的启动时间早于还是晚于最后一次改 mcp_server。
        # 指纹只是排障信息，**算不出来也绝不能拦住启动**（否则一个奇怪的工具 schema
        # 就能把共享 MCP 变成起不来的东西）。
        try:
            tool_face = tool_face_fingerprint(tool_face_from_mcp(mcp))
        except (RuntimeError, TimeoutError, ValueError, TypeError, AttributeError, OSError) as exc:
            # 排障信息不得影响服务可用性。类型清单与 ``tool_face.tool_face_from_mcp``
            # 同口径（那里有完整理由）；不用 ``except Exception`` 是仓规棘轮的要求。
            logger.warning("工具面指纹计算失败（进程照常启动）: %s", exc)
            tool_face = f"unavailable({type(exc).__name__})"
        logger.info("tool_face=%s primary=%s:%s side=%s", tool_face, host, port, side_port)
        # primary 与 side 两个监听一起交给 uvicorn：side 端口只有一个监听者，
        # 是「候选实例真的起来了」的确定性判据（SO_REUSEPORT 下 primary 的连接会
        # 在新旧实例间分摊，拿它判就绪可能打到旧进程，给出假通过）。
        uvicorn.Server(uvicorn.Config(app, host=host, port=port, timeout_graceful_shutdown=graceful_timeout)).run(
            sockets=sockets
        )
        return

    # 必须在 django.setup() 之后导入：工具模块在导入期就会访问 Django 模型。
    # 工具导入同样包在 stdout 改道窗口内——433 个模块任何一个在 import 期
    # print/写 stdout 都会插进 JSON-RPC 流毁掉握手（setup 期的改道只护住
    # Django 自身日志;2026-10-25 实测当时干净,这是结构性防御,纯度由
    # test_entrypoint 的真 stdio 会话门禁逐行钉死）。
    real_stdout = sys.stdout
    sys.stdout = sys.stderr
    try:
        from mcp_server.server import mcp
        from mcp_server.tool_approval_gate import install_tool_approval_gate
        from mcp_server.tool_tier_gate import install_tool_tier_gate
    finally:
        sys.stdout = real_stdout
    # stdio 下没有请求头，一律全量；挂上只是为了让两条传输共用同一个装配点
    # （手工 ``pi`` / 脚本用 stdio 时不带任何头，行为与改造前完全一致）。
    install_tool_tier_gate(mcp)
    # 审批闸门同理共用装配点：stdio 无 X-Fachuan-Session，高危工具一律等不到
    # 审批（fail-closed），不会因为「问不到人」就放行。
    install_tool_approval_gate(mcp)
    mcp.run()


if __name__ == "__main__":
    main()
