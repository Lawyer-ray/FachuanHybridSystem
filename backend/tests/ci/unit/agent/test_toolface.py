"""``fachuan`` 这个 MCP server 名的**单源收敛**不变量。

## 为什么要一个专门的测试文件

``fachuan`` 不是普通常量：四级审批按**工具全名** ``mcp__fachuan__<rawName>``
匹配（``apps/agent/services/approval/risk.py``、``mcp_server/tool_tiers.py``），
pi 的 ``mcp.json`` 键与 dsh 的 ``serverName`` 都决定这个名字是怎么生成的。
它曾经分散硬编码在 9 处，任何一处改名都不会报错——工具照旧可调，只是
**不再经过人工闸门**（静默失效家族）。

收敛后权威定义只有一处：``apps/agent/backends/toolface/constants.py``。
本文件守住「其它地方没有第二份真值」：

1. ``SERVER_NAME`` 钉死取值（防手滑改成 ``fachuan-mcp`` 之类）；
2. pi 的 ``mcp.json`` 生成结果里 server 键 == ``SERVER_NAME``；
3. dsh 的 patch 里 ``serverName: <SERVER_NAME>`` 且超时与 pi 同源；
4. **跨语言**：``rpc_client.py`` / ``tool-result-guard.ts`` / ``approval-gate.ts``
   里的 ``mcp__fachuan__`` 文本与 ``SERVER_NAME`` 一致（TS 无法 import
   Python 常量，只能靠文本比对）；
5. endpoint 值对象：url 拼接、默认值、环境变量解析。

刻意**不**依赖 Django（纯 stdlib 断言），这样它能在任何 DB 配置下跑。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from apps.agent.backends import dsh_mcp, toolface
from apps.agent.backends.toolface import McpEndpoint
from apps.agent.backends.toolface import constants as toolface_constants
from apps.agent.backends.toolface import endpoint as toolface_endpoint
from apps.agent.backends.toolface import shared_enabled, tool_prefix

_BACKEND = Path(__file__).resolve().parents[4]
_PI_DIR = _BACKEND / "apps" / "agent" / "pi"


class TestServerNameIsSingleSource:
    def test_server_name_is_pinned(self) -> None:
        """``SERVER_NAME`` 必须是 ``fachuan``。

        钉死值而不是「等于自己」：审批链、两条 mcp.json 键、dsh ``serverName``、
        前端解析、``--tools`` 白名单全部建立在这个字面量上，改它等于换一套接口。
        """
        assert toolface.SERVER_NAME == "fachuan"

    def test_tool_prefix_is_derived(self) -> None:
        """工具全名前缀必须由 ``SERVER_NAME`` 拼出（不是另一份手写字面量）。"""
        assert tool_prefix() == f"mcp__{toolface.SERVER_NAME}__"

    def test_pi_and_dsh_share_the_same_symbol(self) -> None:
        """pi / dsh / 审批侧引用的都是同一个对象，不是各自的一份拷贝。"""
        from apps.agent.pi import shared_mcp

        assert shared_mcp.SERVER_NAME is toolface.SERVER_NAME
        assert dsh_mcp.SERVER_NAME is toolface.SERVER_NAME

    def test_dsh_tool_timeout_is_derived_from_pi_timeout(self) -> None:
        """dsh 的 ``toolCallTimeoutMs`` 与 pi 的 ``timeout`` 同源（秒 → 毫秒）。"""
        assert dsh_mcp.TOOL_CALL_TIMEOUT_MS == toolface.TOOL_TIMEOUT_SECONDS * 1000
        assert toolface.TOOL_TIMEOUT_SECONDS == 200

    def test_pi_mcp_json_timeout_matches_toolface(self, tmp_path: Path) -> None:
        """pi ``mcp.json`` 里写的 ``timeout`` 必须 == ``TOOL_TIMEOUT_SECONDS``。

        ``pi/shared_mcp.py`` 里的 timeout 必须保持**字面量写法**
        （``"timeout": 200``）——``test_pi_timeout_alignment.py`` 用正则扫那个
        文件，换成常量名会让双端超时门禁扫不到东西而硬失败。所以这里读真实
        生成结果做一致性断言，把「字面量」和「单源常量」连起来。
        """
        from apps.agent.pi import shared_mcp

        path = shared_mcp.write_pi_mcp_config(tmp_path / "cfg-timeout")
        server = json.loads(path.read_text(encoding="utf-8"))["mcpServers"][toolface.SERVER_NAME]
        assert server["timeout"] == toolface.TOOL_TIMEOUT_SECONDS


class TestPiMcpJsonServerKey:
    def test_written_mcp_json_uses_server_name(self, tmp_path: Path) -> None:
        """``write_pi_mcp_config`` 写出的 ``mcpServers`` 键 == ``SERVER_NAME``。

        走真实写盘 + 读回 JSON：直接断言源码里的字符串抓不到
        ``json.dumps({...: {SERVER_NAME: server}})`` 这种间接写法，也抓不到
        「两处键写得不一致」这类漂移。
        """
        from apps.agent.pi.shared_mcp import write_pi_mcp_config

        path = write_pi_mcp_config(tmp_path / "cfg")
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert list(payload["mcpServers"]) == [toolface.SERVER_NAME]

    def test_full_config_uses_server_name(self, tmp_path: Path) -> None:
        """``write_pi_config``（正式链路）的键也必须一致。

        这条是「两处各写一份字段表」历史问题的回归钉：
        ``write_pi_config`` 与 ``write_pi_mcp_config`` 必须共用同一键。
        """
        from apps.agent.pi import shared_mcp

        path = shared_mcp.write_pi_config(tmp_path / "cfg2")
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert list(payload["mcpServers"]) == [toolface.SERVER_NAME]


class TestDshPatchServerName:
    def test_patch_body_carries_server_name(self) -> None:
        """dsh mcp-client 的 ``serverName`` 就是审批匹配口径的命名空间。"""
        body = dsh_mcp.patch_body(McpEndpoint(), "tok")  # pragma: allowlist secret
        assert f"serverName: {toolface.SERVER_NAME}\n" in body

    def test_patch_timeout_matches_pi(self) -> None:
        body = dsh_mcp.patch_body(McpEndpoint(), "tok")  # pragma: allowlist secret
        assert f"toolCallTimeoutMs: {toolface.TOOL_TIMEOUT_SECONDS * 1000}\n" in body

    def test_patch_declares_lite_tool_tier(self) -> None:
        """dsh 必须声明工具面档位，否则 MCP server 返回全量 434 个工具。

        实测代价（2026-11-25 重测）：全量 314KB / 约 10.2 万 token vs lite 44KB / 约 1.5 万。
        且 dsh **会话内不重新同步 tools/list**，所以「给多少」只能在连接时定，
        唯一表达位置就是这个请求头 —— 漏了它不会报错，只会默默地多花 7 万 token。
        """
        body = dsh_mcp.patch_body(McpEndpoint(), "tok")  # pragma: allowlist secret
        assert f"{toolface.TOOL_TIER_HEADER}: " in body
        assert toolface.TIER_LITE in body

    def test_tool_tier_can_be_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """一键回滚到全量（排查「模型说没这个能力」时先关它确认）。"""
        monkeypatch.setenv("FACHUAN_DSH_TOOL_TIER", "off")
        body = dsh_mcp.patch_body(McpEndpoint(), "tok")  # pragma: allowlist secret
        assert toolface.TIER_FULL in body


class TestCrossLanguagePrefix:
    """TS / 另一份 Python 字面量无法 import 本常量，只能靠文本比对守。"""

    def test_python_tool_selection_uses_prefix(self) -> None:
        """``rpc_client.TOOL_SELECTION`` 的 MCP 前缀必须与 ``SERVER_NAME`` 一致。"""
        from apps.agent.pi.rpc_client import TOOL_SELECTION

        assert f"{tool_prefix()}*,tool_search" == TOOL_SELECTION

    def test_tool_result_guard_ts_prefix(self) -> None:
        """``tool-result-guard.ts`` 的 ``TOOL_PREFIX`` 常量文本必须一致。

        这个常量是**真在跑**的代码（``name.startsWith(TOOL_PREFIX)``）：与 Python
        侧不一致时守卫扩展对法穿工具整体失效，且没有任何报错。
        """
        source = (_PI_DIR / "tool-result-guard.ts").read_text(encoding="utf-8")
        declared = re.findall(r'const TOOL_PREFIX = "([^"]+)"', source)
        assert declared, "tool-result-guard.ts 里找不到 TOOL_PREFIX 字面量（写法变了?）"
        assert declared == [tool_prefix()]

    def test_approval_gate_ts_mentions_the_same_prefix(self) -> None:
        """``approval-rules.ts`` 里的 ``mcp__*__`` 文本必须都是本 server 的前缀。

        gate 的实现按 ``"__"`` 切尾取短名，没有前缀常量；它只在前缀指的注释里
        写出那个名字——正是后来人抄写时唯一的参照，所以它也必须与
        ``SERVER_NAME`` 一致。用正则把所有形如 ``mcp__x__`` 的片段全抓出来逐个比，
        而不是只看「有没有出现正确值」（那样错误值也能混过去）。
        """
        source = (_PI_DIR / "approval-rules.ts").read_text(encoding="utf-8")
        mentioned = set(re.findall(r"mcp__[A-Za-z0-9_-]+__", source))
        assert mentioned == {tool_prefix()}, f"approval-rules.ts 提到的前缀与本 server 不一致: {sorted(mentioned)}"

    def test_only_toolface_constructs_the_prefix_from_a_literal(self) -> None:
        """``apps/`` 下除了 ``toolface`` 自己，不许再用字面量拼 ``mcp__fachuan__``。

        用 AST 找**字符串/字节串字面量**以及隐含的 f-string（``JoinedStr`` 里含该
        文本的常量段）——两种写法都是「第二份真值」：

        - ``"mcp__fachuan__"``（直接硬编码，历史写法）
        - ``f"mcp__fachuan__{name}"``（看起来像拼接，实际还是硬编码）

        注释与 docstring 不算：docstring 是 ``ast.Constant`` 的表达式语句，会被
        下面的 elif 分支排除；注释不进 AST。它们解释「为什么」，不是取值来源。
        """
        import ast

        needle = tool_prefix()
        scanned = 0
        offenders: list[str] = []
        for py in sorted((_BACKEND / "apps").rglob("*.py")):
            if "__pycache__" in str(py):
                continue
            relative = py.relative_to(_BACKEND)
            if relative.parts[:4] == ("apps", "agent", "backends", "toolface"):
                continue
            scanned += 1
            tree = ast.parse(py.read_text(encoding="utf-8"))
            docstrings = {
                id(node.value)
                for node in ast.walk(tree)
                if isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            }
            for node in ast.walk(tree):
                if id(node) in docstrings:
                    continue
                # 二进制字面量（PDF 魔数等）不可能是工具名，跳过解码。
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    if needle in node.value:
                        offenders.append(f"{relative}:{node.lineno}: 字面量 {node.value!r}")
                elif isinstance(node, ast.JoinedStr):
                    parts = [value.value for value in node.values if isinstance(value, ast.Constant)]
                    if any(needle in str(part) for part in parts):
                        offenders.append(f"{relative}:{node.lineno}: f-string 常量段含 {needle!r}")
        # 自证：扫描器真的走到了文件（rglob 写错时 offenders 恒为空 → 假绿）。
        assert scanned > 100, f"扫描器只走到 {scanned} 个文件，rglob 路径可能写错了"
        assert offenders == [], "以下位置硬编码了 MCP 前缀，应改用 toolface.tool_prefix():\n" + "\n".join(offenders)


class TestEndpointValueObject:
    def test_default_endpoint_url(self) -> None:
        """默认 127.0.0.1:8011 + ``/mcp``（部署、脚本、文档里全是这个地址）。"""
        endpoint = McpEndpoint()
        assert (endpoint.host, endpoint.port) == ("127.0.0.1", 8011)
        assert endpoint.url == "http://127.0.0.1:8011/mcp"

    def test_url_concatenation(self) -> None:
        assert McpEndpoint(host="10.0.0.5", port=9000).url == "http://10.0.0.5:9000/mcp"

    def test_endpoint_from_env_reads_host_and_port(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(toolface_endpoint.HOST_ENV, "0.0.0.0")
        monkeypatch.setenv(toolface_endpoint.PORT_ENV, "8123")
        endpoint = toolface.endpoint_from_env()
        assert (endpoint.host, endpoint.port) == ("0.0.0.0", 8123)

    def test_endpoint_from_env_falls_back_on_garbage_port(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """非法端口回退默认值而不是抛：环境变量写错不该让整个应用起不来。"""
        monkeypatch.setenv(toolface_endpoint.PORT_ENV, "not-a-port")
        monkeypatch.setenv(toolface_endpoint.HOST_ENV, "   ")
        endpoint = toolface.endpoint_from_env()
        assert (endpoint.host, endpoint.port) == ("127.0.0.1", 8011)

    @pytest.mark.parametrize("raw", ["0", "false", "FALSE", "no", "off", " Off "])
    def test_shared_disabled_values(self, monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
        monkeypatch.setenv(toolface_endpoint.SHARED_ENV, raw)
        assert shared_enabled() is False

    @pytest.mark.parametrize("raw", ["1", "true", "yes", "on", ""])
    def test_shared_enabled_values(self, monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
        monkeypatch.setenv(toolface_endpoint.SHARED_ENV, raw)
        assert shared_enabled() is True

    def test_shared_enabled_defaults_to_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """默认启用共享：关掉会让每个 pi 各起一份 ~225MB 的 MCP。"""
        monkeypatch.delenv(toolface_endpoint.SHARED_ENV, raising=False)
        assert shared_enabled() is True

    def test_log_dir_matches_agent_home(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """``toolface.mcp_log_dir()`` 必须与 ``pi.session_store.agent_home()/logs`` 同址。

        两者刻意各写一份（``toolface`` 不能 import ``pi``，否则成环），
        所以用这条断言把「两份取值不漂移」钉住——日志落错地方等于把
        「MCP 为什么起不来」的唯一线索丢掉。
        """
        from apps.agent.pi.session_store import agent_home

        monkeypatch.setenv("FACHUAN_AGENT_HOME", str(tmp_path / "ah"))
        assert toolface.mcp_log_dir() == agent_home() / "logs"
        # ``agent_home()`` 本身也钉住：qoder 后端的 work/配置目录建在它下面，
        # 两边取值漂移会把状态写到两个地方（而这是没有任何报错的静默失效）。
        assert toolface.agent_home() == agent_home()


class TestToolfaceStaysStdlibOnly:
    def test_package_imports_only_stdlib(self) -> None:
        """``toolface`` 只许依赖 stdlib：``pi`` 与 ``backends`` 都依赖它，成环即炸。

        用 AST 扫真实 import 语句而不是读 ``__all__``——环是从 import 来的。
        """
        import ast

        package = Path(toolface_constants.__file__).parent
        banned_prefixes = (
            "apps",
            "mcp_server",
            "django",
            "pi",
            "session_store",
            "models",
            "services",
        )
        offenders: list[str] = []
        for py in sorted(package.glob("*.py")):
            tree = ast.parse(py.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                modules: list[str] = []
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level:  # 包内相对导入
                        continue
                    modules = [node.module or ""]
                for module in modules:
                    root = module.split(".", 1)[0]
                    if root in banned_prefixes:
                        offenders.append(f"{py.name}: import {module}")
        assert offenders == [], "toolface 只许依赖 stdlib，违规 import:\n" + "\n".join(offenders)
