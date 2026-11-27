"""审批拒绝文案（``_denied_text``）的三段结构。

为什么值得写：这句话是模型在「审批没通过」之后能看到的**全部**信息。上一版只说
「未执行（风险等级：…）+ 审批结论」，模型把它当成一次普通失败，于是原样重发同一个
写动作——律师刚拒绝过，弹窗又被问一遍。所以三段缺一不可：

1. **谁挡的**：工具名（模型要知道是哪个调用被拦，而不是「某个工具」）；
2. **为什么**：``reason``（律师驳回的理由 / 系统给的原因），空时要有兜底说明；
3. **下一步该干什么**：明确「不要原样重试同一动作」+ 两条可走的路（问律师 / 换只读路径）。

纯字符串函数：本文件不建库、不起事件循环，断言只在文本上。
"""

from __future__ import annotations

from apps.agent.services.approval import RiskLevel
from mcp_server.tool_approval_gate import _denied_text

LEVEL = RiskLevel.HIGH


def test_denied_text_names_tool_reason_and_next_step() -> None:
    """有审批单时：三段都在，且「批准后那一次重试」的正规路径没被抹掉。"""
    text = _denied_text("delete_case", LEVEL, "abcd" * 8, "用户拒绝或超时")

    assert "delete_case" in text, "模型要知道是哪个工具被拦"
    assert "用户拒绝或超时" in text, "拒绝理由必须原样带出来"
    assert "不要原样重试" in text, "下一步必须明确禁止原样重试"
    assert "向律师确认" in text and "只读路径" in text, "只禁止而不给出路，模型只能干等"
    assert "不要重复调用" in text and "原样重试一次" in text, "批准后那一次重试仍是正规路径"


def test_denied_text_without_approval_id_still_forbids_retry() -> None:
    """没有审批单（策略拒绝 / 无会话）时，重试没有任何正规路径，文案要说得更死。"""
    text = _denied_text("delete_case", LEVEL, "", "无人在线且不允许离线审批，按拒绝处理")

    assert "delete_case" in text
    assert "无人在线且不允许离线审批" in text
    assert "不要原样重试" in text
    assert "不要重复调用" in text
    assert "只读路径" in text


def test_denied_text_blank_reason_has_explanation() -> None:
    """``reason`` 为空也要说明「为什么」——留一个空位等于逼模型自己编原因。"""
    text = _denied_text("delete_case", LEVEL, "ef" * 16, "")

    assert "未获批准" in text, "空 reason 必须给兜底说明"
    assert "审批结论：" in text, "三段里的「为什么」段不能被整段省略"
