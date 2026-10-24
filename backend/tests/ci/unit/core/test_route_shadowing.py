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


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
