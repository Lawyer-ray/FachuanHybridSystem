"""路由遮蔽门禁——后注册的字面量路由被先注册的参数路由吞掉(2026-10-25 审计)。

## 背景

ninja 的 URL 正则按**注册顺序**匹配,``{param}`` 默认 ``[^/]+``(str)——
字面量路由若注册在参数路由之后:

- 同方法:字面量路由**永不可达**(参数先匹配,字面量值被当参数;
  int 转换失败 → 404/422);
- 异方法:该方法打上来被参数路由拦截 → **405 Method Not Allowed**。

实测抓到 3 例(全部真实死路由):
- ``POST /court-sms/batch-delete`` 被 ``/court-sms/{sms_id}``(GET/DELETE)遮蔽 → 恒 405
- ``GET /placeholders/overview`` 被 ``/placeholders/{placeholder_id}``(GET)遮蔽 → 永不可达
- ``GET /animations/models`` 被 ``/animations/{animation_id}``(GET)遮蔽 → 永不可达

修复模式:字面量路由(及其依赖的 schema 类)移到参数路由之前注册。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[4]
#: 只扫 api 层文件(路由注册的权威位置)
_API_GLOB = sorted((_BACKEND / "apps").glob("*/api/*.py"))

_ROUTE_RE = re.compile(r'@router\.(get|post|put|patch|delete)\(\s*"([^"]+)"')


def _segment_regex(path: str) -> re.Pattern[str]:
    parts: list[str] = []
    for seg in path.strip("/").split("/"):
        if seg.startswith("{") and seg.endswith("}"):
            parts.append("[^/]+")
        else:
            parts.append(re.escape(seg))
    return re.compile("^" + "/".join(parts) + "$")


def _find_shadowings() -> list[str]:
    findings: list[str] = []
    for f in _API_GLOB:
        routes = _ROUTE_RE.findall(f.read_text())
        for i, (method_l, path_l) in enumerate(routes):
            if "{" in path_l:
                continue  # 只查字面量路由
            for method_e, path_e in routes[:i]:
                if "{" not in path_e:
                    continue
                if _segment_regex(path_e).match(path_l.strip("/")):
                    kind = "永不可达(同方法)" if method_e == method_l else f"405({method_l} 被 {method_e} 路由拦截)"
                    findings.append(
                        f"{f.relative_to(_BACKEND)}:{path_l} [{method_l}] "
                        f"被 {path_e} [{method_e}] 遮蔽 → {kind}"
                    )
    return findings


def test_api_files_found():
    assert len(_API_GLOB) > 20, "路由扫描文件过少,疑似 glob 失效(防假绿)"


def test_no_literal_route_shadowed_by_param_route():
    findings = _find_shadowings()
    assert not findings, (
        "字面量路由被参数路由遮蔽(把字面量路由及其 schema 移到参数路由前注册):\n  - "
        + "\n  - ".join(findings)
    )


# ============================================================
# 运行时门禁——跨文件/跨 router 的最终真值(2026-10-25 审计十八轮)
#
# 源码扫描只看单文件,而 /documents 前缀挂了 8 个 router、"" 挂了 3 个:
# 先注册 router 里的参数路由同样能吞掉后注册 router 里的字面量路由。
# 真值在 Django URL resolver:``api/v1`` 子树按**注册顺序**展开成 600+ 个
# URLPattern,每个的 callback 闭包里挂着 ninja ``PathView``(含全部方法)。
# 按全局顺序两两比对,与源码级扫描互为补充。
# ============================================================


def _v1_patterns() -> list[tuple[str, set[str]]]:
    """按注册序返回 ``(路径正则, HTTP 方法集合)``;无 PathView 的(openapi.json 等)方法为空。"""
    from django.urls import get_resolver

    v1 = next(p for p in get_resolver().url_patterns if hasattr(p, "url_patterns") and "v1" in str(getattr(p.pattern, "regex", "")))
    out: list[tuple[str, set[str]]] = []
    for sp in v1.url_patterns:
        rx = str(sp.pattern.regex)
        methods: set[str] = set()
        for cell in getattr(sp.callback, "__closure__", None) or []:
            pv = cell.cell_contents
            for op in getattr(pv, "operations", []) or []:
                methods |= set(getattr(op, "methods", None) or ())
        out.append((rx, methods))
    return out


def _literal_path(rx: str) -> str | None:
    """不含路径参数的正则返回其字面量路径,否则 None。"""
    if "(?P<" in rx:
        return None
    body = rx.removeprefix("^").removesuffix("\\Z")
    return re.sub(r"\\(.)", r"\1", body)


def _find_runtime_shadowings() -> list[str]:
    findings: list[str] = []
    pats = _v1_patterns()
    for i, (rx_i, methods_i) in enumerate(pats):
        path = _literal_path(rx_i)
        if path is None or not methods_i:
            continue  # 只查带方法的字面量路由
        probe = re.compile(rx_i.removeprefix("^").removesuffix("\\Z") + r"\Z")
        for j in range(i):
            rx_j, methods_j = pats[j]
            if not methods_j:
                continue
            # 早前的字面量路由:路径相同(重复注册)才可能遮蔽;参数路由:任何时候都可能
            if "(?P<" not in rx_j and rx_j != rx_i:
                continue
            body_j = rx_j.removeprefix("^").removesuffix("\\Z")
            if not re.compile(body_j).fullmatch(path):
                continue
            hit = methods_i & methods_j
            kind = f"方法 {sorted(hit)} 永不可达" if hit else f"方法 {sorted(methods_i)} 恒 405"
            findings.append(f"/{path} [{kind}] ← 被第 {j + 1} 条 {rx_j} [{sorted(methods_j)}] 遮蔽(本条是第 {i + 1} 条)")
    return findings


def test_runtime_no_literal_route_shadowed():
    pats = _v1_patterns()
    assert len(pats) > 500, f"api/v1 路由数异常({len(pats)}),疑似 resolver 未展开(防假绿)"
    findings = _find_runtime_shadowings()
    assert not findings, (
        "运行时路由遮蔽(按 Django 全局注册序,字面量路由被更早的参数/同径路由吞掉):\n  - "
        + "\n  - ".join(findings)
    )


def test_runtime_detector_catches_known_shadow(monkeypatch: pytest.MonkeyPatch):
    """检测器自证:喂入十六/十七轮真实故障形态,必须命中(防检测器假绿)。"""
    monkeypatch.setattr(
        sys.modules[__name__],
        "_v1_patterns",
        lambda: [
            (r"^inbox/sources/(?P<source_id>[^/]+)\Z", {"GET", "DELETE"}),  # 参数路由在前
            (r"^inbox/sources/sync\-all\Z", {"POST"}),  # 同径字面量在后 → 405
            (r"^documents/placeholders/(?P<placeholder_id>[^/]+)\Z", {"GET"}),
            (r"^documents/placeholders/overview\Z", {"GET"}),  # 同方法 → 永不可达
        ],
    )
    findings = _find_runtime_shadowings()
    assert len(findings) == 2, findings
    assert any("405" in f and "sync" in f for f in findings), findings
    assert any("永不可达" in f and "overview" in f for f in findings), findings


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
