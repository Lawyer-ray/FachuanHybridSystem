"""审批分级 ↔ 工具行为对齐门禁(2026-10-25 晨间审计十九轮)。

## 背景

分级是**纯名字推断**(``classify_risk``),工具实际行为在 REST 调用里——
两轨可以对不上:

- **LOW + 写方法** = 无审批、无留痕、readOnlyHint=True,模型可静默写库。
  实测抓到 3 例(convert_document 每次转换落 DocConvertRecord+产物文件、
  analyze_template 改模板状态+建 FieldMapping、parse_document 存上传文件
  +建 DocumentParsingTask+派后台任务)——前轮「parse_ 整族保持 LOW」的
  纯计算假设对它们不成立。已补 WRITE_PREFIXES(convert_/analyze_/
  parse_document)修复。
- **readOnlyHint 与分级不一致** = 客户端(pi 等)按 hint 做免审批策略时
  会被误导。

## 门禁

1. LOW 级工具的 REST 调用必须是 GET,除非在 ``_LOW_POST_ALLOWLIST``
   (每条带理由:纯计算/校验/内存生成/admin 专用);
2. LOW ⇔ readOnlyHint=True 双向一致;
3. 豁免表不得混入未注册工具名(防僵尸条目绕过检查)。
"""

from __future__ import annotations

import sys
from inspect import getsource
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_output_contract import _rest_call_of

#: LOW 级但用写方法的工具豁免表(每条都有「确实无持久化」的核验依据)。
_LOW_POST_ALLOWLIST: dict[str, str] = {
    # 纯计算/校验/识别,POST 只是 REST 风格,服务层无落库
    "calculate_interest": "LPR 利息计算,纯函数",
    "calculate_litigation_fee": "诉讼费计算,纯函数",
    "mortgage_amortize": "房贷摊还计算,纯函数",
    "mortgage_default_calculate": "房贷违约金计算,纯函数",
    "detect_orientation": "图片方向检测,纯识别",
    "detect_single_page_orientation": "单页方向检测,纯识别",
    "suggest_rename": "只建议文件名,不改名",
    "validate_id_card": "身份证校验,纯函数",
    "validate_folder_structure": "目录树校验,只读",
    "check_law_references": "法条核验,只读检索",
    "verify_citations": "法条/案号核查,只读检索(backing service 经 grep 确认无 .save/.create/update)",
    "chat_with_context": "LLM 对话,无持久化",
    "test_model_connection": "LLM 连通测试,无持久化",
    "capability_search": "能力检索,只读",
    "parse_client_text": "纯内存文本解析",
    "parse_reminders_from_text": "纯内存文本解析",
    "quick_recognize_invoice": "快速识别(不创建任务,端点文档明示)",
    # 内存生成 + 下载,产物不落库(litigation/authorization 服务层零持久化,已核)
    "download_authority_letter": "内存生成 docx 直返",
    "download_authorization_package": "内存生成打包直返",
    "download_delay_delivery_application": "内存生成直返",
    "download_full_preservation_package": "内存生成打包直返",
    "download_legal_rep_certificate": "内存生成直返",
    "download_litigation_document": "内存生成直返(litigation 服务零持久化,已核)",
    "download_power_of_attorney": "内存生成直返",
    "download_power_of_attorney_combined": "内存生成直返",
    "download_preservation_application": "内存生成直返",
    # admin 专用且只读分析 / 仅记一条性能指标
    "auto_namer_process_by_path": "admin 专用,只生成命名建议",
    "optimize_concurrency": "admin 专用,只出分析建议不改配置",
    "warm_up_cache": "admin 专用,仅记一条性能指标",
}


def _registered() -> dict[str, Any]:
    from mcp_server.server import mcp

    return dict(mcp._tool_manager._tools)


def _fn_source(fn: Any) -> str:
    return getsource(fn.fn if hasattr(fn, "fn") else fn)


def test_low_tools_are_read_only_http():
    from apps.agent.services.approval import RiskLevel, classify_risk

    bad: list[str] = []
    for name, fn in sorted(_registered().items()):
        if classify_risk(name) != RiskLevel.LOW:
            continue
        call = _rest_call_of(_fn_source(fn))
        if call and call[0] != "GET" and name not in _LOW_POST_ALLOWLIST:
            bad.append(f"{name}: {call[0]} {call[1]}(LOW 但写方法,且不在豁免表)")
    assert not bad, "LOW(直接执行+readOnlyHint)工具发写请求:\n  - " + "\n  - ".join(bad)


def test_read_only_hint_matches_risk_level():
    from apps.agent.services.approval import RiskLevel, classify_risk
    from mcp_server.server import _tool_annotations

    bad: list[str] = []
    for name in sorted(_registered()):
        low = classify_risk(name) == RiskLevel.LOW
        ann = _tool_annotations(name)
        hinted = bool(ann and ann.read_only_hint)
        if low != hinted:
            bad.append(f"{name}: LOW={low} readOnlyHint={hinted}")
    assert not bad, "readOnlyHint 与审批分级不一致:\n  - " + "\n  - ".join(bad)


def test_allowlist_has_no_stale_entries():
    names = set(_registered())
    stale = sorted(set(_LOW_POST_ALLOWLIST) - names)
    assert not stale, f"豁免表含未注册工具(僵尸条目绕过检查): {stale}"


def test_write_via_post_tools_classified_medium():
    """十九轮修复的三个 POST-但真写工具必须是中级(静默+留痕)。"""
    from apps.agent.services.approval import RiskLevel, classify_risk

    for name in ("parse_document", "convert_document", "analyze_template"):
        assert classify_risk(name) == RiskLevel.MEDIUM, f"{name} 应为 MEDIUM"
