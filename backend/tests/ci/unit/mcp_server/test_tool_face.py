"""工具面指纹的判定口径（纯函数级：不连 DB、不起服务、不占端口）。

指纹是「改完 ``mcp_server`` 要不要重启共享 MCP」的唯一判据（``scripts/shared_mcp.sh``
的 ``--if-stale`` 与 ``bluegreen`` 都靠它跳过或执行切换），所以这里逐条钉死「什么算
变了」——少一条就会让门禁静默失效：

- 工具增删 → 变（新工具被跳过就等于没上线）；
- 描述改字 → 变（描述是模型选工具的依据，改描述等于改行为）；
- ``inputSchema`` 改（参数名/描述/enum）→ 变（模型据此构造调用）；
- ``annotations`` 改（只动 ``readOnlyHint`` / ``destructiveHint``）→ 变（注解是**审批
  分级的输入**：插件把工具风险从 ``read`` 调到 ``high`` 时只改注解，名字/描述/schema
  一个字不改，指纹不变就会让 ``--if-stale`` 静默跳过、常驻进程继续按旧的低风险放行）；
- 注解字段写成 ``None`` 与「压根没写」→ **不变**（否则对象侧 ``model_dump`` 的 ``None``
  会与 wire 侧「没这个键」算成两个指纹）；
- 注册顺序不同 → **不变**（顺序不是语义，否则每次 import 抖动都会误判成「变了」，
  ``--if-stale`` 就退化成每次都重启）。
"""

from __future__ import annotations

from typing import Any

from mcp_server.tool_face import tool_face_entries, tool_face_fingerprint


def _tool(name: str, description: str = "工具说明", **properties: Any) -> dict[str, Any]:
    """造一条 wire 形态的工具条目（``inputSchema`` 用驼峰，与协议一致）。"""
    return {
        "name": name,
        "description": description,
        "inputSchema": {"type": "object", "properties": dict(properties)},
    }


def test_same_tool_face_yields_same_fingerprint() -> None:
    tools = [_tool("write_case"), _tool("read_case", path={"type": "string"})]

    assert tool_face_fingerprint(tools) == tool_face_fingerprint([dict(t) for t in tools])


def test_tool_order_does_not_change_fingerprint() -> None:
    first = _tool("write_case")
    second = _tool("read_case")

    assert tool_face_fingerprint([first, second]) == tool_face_fingerprint([second, first])


def test_adding_a_tool_changes_fingerprint() -> None:
    assert tool_face_fingerprint([_tool("write_case")]) != tool_face_fingerprint(
        [_tool("write_case"), _tool("read_case")]
    )


def test_description_change_changes_fingerprint() -> None:
    assert tool_face_fingerprint([_tool("write_case", "写一个案子")]) != tool_face_fingerprint(
        [_tool("write_case", "写一个案件")]
    )


def test_input_schema_change_changes_fingerprint() -> None:
    string_param = _tool("write_case", path={"type": "string"})
    integer_param = _tool("write_case", path={"type": "integer"})

    assert tool_face_fingerprint([string_param]) != tool_face_fingerprint([integer_param])


def _annotated(name: str, **hints: Any) -> dict[str, Any]:
    """造一条带注解的 wire 工具条目（注解键用协议驼峰写法）。"""
    return {**_tool(name), "annotations": dict(hints)}


def test_destructive_hint_change_changes_fingerprint() -> None:
    """只改 ``destructiveHint``（其余一字不改）也必须换指纹。

    这是真实的危险场景：插件把工具从「可回滚的写」改成「不可逆删除」时只动注解，
    指纹不变 → ``--if-stale`` 跳过重启 → 线上仍按旧的低风险放行。
    """
    additive = _annotated("write_case", readOnlyHint=False, destructiveHint=False)
    destructive = _annotated("write_case", readOnlyHint=False, destructiveHint=True)

    assert tool_face_fingerprint([additive]) != tool_face_fingerprint([destructive])


def test_read_only_hint_change_changes_fingerprint() -> None:
    """只改 ``readOnlyHint``（read → write）也必须换指纹。"""
    reader = _annotated("query_case", readOnlyHint=True)
    writer = _annotated("query_case", readOnlyHint=False)

    assert tool_face_fingerprint([reader]) != tool_face_fingerprint([writer])


def test_annotation_none_value_equals_absent_annotation() -> None:
    """注解写成 ``None`` 与「没写」必须同指纹。

    pydantic 的 ``model_dump()`` 会把没声明的注解字段 dump 成 ``None``；不丢 None 的话，
    同一份代码从对象侧与 wire 侧读到的注解形态不同就会算出两个指纹，``--if-stale``
    于是每次都真重启——门禁失效的方式恰好是最难察觉的那种。
    """
    absent = _tool("read_case")
    explicit_none = {**_tool("read_case"), "annotations": {"readOnlyHint": None, "destructiveHint": None}}

    assert tool_face_fingerprint([absent]) == tool_face_fingerprint([explicit_none])


def test_empty_tool_face_has_stable_fingerprint() -> None:
    empty = tool_face_fingerprint([])

    assert empty == tool_face_fingerprint([])
    assert len(empty) == 12
    # 空表指纹不能等于「随便一个工具」的指纹：`verify` 用空表指纹当作「一个工具都没有」
    # 的合法值，混同就等于把「没读到工具表」伪装成「工具面为空」。
    assert empty != tool_face_fingerprint([_tool("write_case")])


def test_pydantic_tool_object_matches_wire_dict() -> None:
    """同一份工具表，pydantic ``Tool`` 与 wire dict 必须算出同一个指纹。

    注册表侧拿到的是对象（``input_schema`` 下划线）、线上握手侧拿到的是 JSON
    （``inputSchema`` 驼峰）。两侧口径不一致的话，``verify`` 会对同一份代码假红，
    ``--if-stale`` 则每次都真重启——门禁失效的方式恰好是最难察觉的那种。
    """
    from mcp.types import Tool

    wire = _tool("write_case", "写一个案子", path={"type": "string"})
    tool_object = Tool(name=wire["name"], description=wire["description"], input_schema=wire["inputSchema"])

    assert tool_face_entries([tool_object]) == tool_face_entries([wire])
    assert tool_face_fingerprint([tool_object]) == tool_face_fingerprint([wire])


def test_registered_tool_parameters_field_matches_wire_dict() -> None:
    """SDK 内部注册对象（schema 字段叫 ``parameters``）与 wire dict 必须同指纹。

    ``mcp.list_tools()`` 不可用时指纹退回 ``ToolManager`` 的同步注册表
    （``apps/agent/services/approval/annotations.py::_sync_tool_snapshot``），那里的对象是
    ``mcp.server.mcpserver.tools.base.Tool``——它的 schema 字段名是 ``parameters``，
    不是 ``mcp.types.Tool`` 的 ``input_schema``。只按 ``input_schema`` 取值会让退回
    路径下每个工具都算成 ``inputSchema={}``：指纹仍是合法字符串，却对 schema 改动失明。
    """
    from mcp.server.mcpserver.tools.base import Tool as RegisteredTool

    def read_case(path: str) -> str:
        """读一个案子。"""
        return path

    tool_object = RegisteredTool.from_function(read_case)
    # 兜底链确实生效：注册对象没有 input_schema，schema 只能从 parameters 取。
    assert getattr(tool_object, "input_schema", None) is None
    wire = {
        "name": tool_object.name,
        "description": tool_object.description,
        "inputSchema": tool_object.parameters,
    }

    assert tool_face_entries([tool_object])[0]["inputSchema"] == tool_object.parameters
    assert tool_face_fingerprint([tool_object]) == tool_face_fingerprint([wire])
