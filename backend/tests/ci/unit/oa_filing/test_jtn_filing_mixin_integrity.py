"""JTN 立案 mixin 调用完整性回归。

背景（2026-10-14 事故）：PR #544 静态方法下沉重构把 PlaywrightHelpersMixin._js_str
搬到模块级后，漏改了 playwright_filing.py 里经 self. 调用的两处，导致 10-11 之后
所有填联系人信息的 Playwright 立案在运行期 AttributeError。
本测试静态扫描 mixin 文件中的 self._xxx( 调用，断言全部能在组合类上解析。
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from apps.oa_filing.services.oa_scripts.jtn.filing.service import JtnFilingScript

_FILING_DIR = Path(__file__).resolve().parents[4] / "apps/oa_filing/services/oa_scripts/jtn/filing"


class TestJtnFilingMixinIntegrity:
    @pytest.mark.parametrize(
        "module_name",
        ["playwright_filing", "playwright_helpers", "http_filing"],
    )
    def test_self_calls_resolve_on_composed_class(self, module_name: str) -> None:
        module_path = _FILING_DIR / f"{module_name}.py"
        source = module_path.read_text(encoding="utf-8")
        called = set(re.findall(r"self\.(_[a-zA-Z_]+)\s*\(", source))
        assert called, f"{module_name}.py 未扫描到 self._x( 调用，文件可能被移动"

        missing = sorted(name for name in called if not hasattr(JtnFilingScript, name))
        assert not missing, (
            f"{module_name}.py 中以下 self.{missing} 调用在 JtnFilingScript 上无法解析——"
            "大概率是静态方法下沉模块级后漏改调用点（参照 2026-10-14 _js_str 事故）"
        )

    def test_playwright_filing_contact_fill_is_resolvable(self) -> None:
        """联系人注入事故点回归（2026-10-14）与 386 漏填回归（2026-10-20）。

        历史上 _js_str 曾因静态方法下沉未改调用点而报 AttributeError；
        2026-10-20 又发现联系人区块由 layui 异步渲染、且从未在 HTML payload 里出现，
        故改为 _fill_case_contact 统一处理。此处断言：
        1) 不再残留经 self. 调用的 _js_str；
        2) _fill_case_contact 在组合类上可解析（mixin 组合不会丢方法）。
        """
        from apps.oa_filing.services.oa_scripts.jtn.filing import playwright_filing

        source = inspect.getsource(playwright_filing)
        assert "self._js_str" not in source
        assert hasattr(JtnFilingScript, "_fill_case_contact")
        assert "_fill_case_contact(info)" in source
