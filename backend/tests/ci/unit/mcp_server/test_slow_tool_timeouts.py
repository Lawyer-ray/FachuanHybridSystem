"""慢工具超时门禁:Playwright/长 IO 后端的调用必须显式抬高 client 超时。

背景(2026-10-25 三十轮审计):client 默认 60s,而以下后端是**同步阻塞**
链路(Playwright 登录 10-15s 起步 + 逐条外部 IO),长输入必超 60s——
工具被 client 先掐断,而 pi 侧 mcp.json timeout=200 本可兜住
(``check_law_references`` 漏配即此案:威科登录+长文书核查,60s 必断)。

规则:对 ``_SLOW_ENDPOINTS`` 登记的路径,client.get/post/... 调用必须带
``timeout=`` 且 ≥ 120s。异步化(submit_task 入队即返)的端点不需要登记。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parents[4] / "mcp_server" / "tools"

#: 同步阻塞(Playwright/长 IO)后端路径 → 必须携带的最小 client 超时。
_SLOW_ENDPOINTS: dict[str, int] = {
    "/lpr/calculate": 180,  # LPR 过期会同步跑 Playwright 同步(服务端等待上限 120s)
    "/lpr/sync": 180,  # Playwright 抓央行网站,数十秒
    "/legal-research/capability/search/mcp": 180,  # 威科检索,同步 Playwright/HTTP
    "/legal-research/law-verification/check": 180,  # 威科 Playwright 登录 10-15s+逐条核查
}

_MIN_SLOW_TIMEOUT = 120


def _iter_tool_files() -> list[Path]:
    return sorted(p for p in _TOOLS_DIR.rglob("*.py") if p.name != "__init__.py")


def _calls_to(path: str):
    """AST 扫描:所有 client.<method>("path") 调用节点(路径全字面量精确匹配)。"""
    hits = []
    for f in _iter_tool_files():
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "client"):
                continue
            if not node.args or not isinstance(node.args[0], ast.Constant) or node.args[0].value != path:
                continue
            hits.append((f, node))
    return hits


@pytest.mark.parametrize("endpoint,minimum", sorted(_SLOW_ENDPOINTS.items()))
def test_slow_endpoint_calls_carry_raised_timeout(endpoint: str, minimum: int) -> None:
    calls = _calls_to(endpoint)
    assert calls, f"{endpoint} 在 tools/ 下没有调用点(端点改名或工具被删,请更新 _SLOW_ENDPOINTS)"
    for f, node in calls:
        timeout = next((kw.value for kw in node.keywords if kw.arg == "timeout"), None)
        assert timeout is not None, f"{f.name}:{node.lineno} 调 {endpoint} 未带 timeout(默认 60s 对同步 Playwright 链路必掐断)"
        value: object = getattr(timeout, "value", None)
        assert isinstance(value, (int, float)) and value >= min(minimum, _MIN_SLOW_TIMEOUT), (
            f"{f.name}:{node.lineno} 调 {endpoint} 的 timeout={value!r} < {minimum}"
        )


def test_registry_is_not_stale() -> None:
    """反假绿:登记表每条都必须有真实调用点,防止路径改名后表变僵尸。"""
    for endpoint in _SLOW_ENDPOINTS:
        assert _calls_to(endpoint), f"_SLOW_ENDPOINTS 条目 {endpoint} 已无调用点(僵尸条目,请删)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
