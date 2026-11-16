"""`devtools/check_cov_args.py` 的判据单测。

## 为什么这条守卫需要被测

它挡的是一个「看起来很普通、实际会段错误」的用法：

    --cov=apps.pdf_splitting.services.split

这个坑很贵——进程直接 segfault，pytest 不会告诉你哪条参数有问题，只留下一段
C 栈。修的人第一反应通常是怀疑自己的测试代码，而不是覆盖率参数。

所以判据必须精确：**既不能漏放**（漏了就白防），**也不能误伤**（误伤会让开发者
以为守卫在瞎报，然后学会绕过它——那守卫就死了）。下面两个方向都锁住。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

#: 本文件在 backend/tests/ci/unit/structure/ 下，parents[4] 正好是 backend/。
_SCRIPT = Path(__file__).resolve().parents[4] / "devtools" / "check_cov_args.py"


def _load_module():
    """按路径加载脚本（它不是包内模块，不能直接 import）。"""
    spec = importlib.util.spec_from_file_location("check_cov_args", _SCRIPT)
    assert spec and spec.loader, f"找不到脚本: {_SCRIPT}"
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_cov_args"] = module
    spec.loader.exec_module(module)
    return module


check_cov_args = _load_module()


class TestUnsafeDetection:
    """会崩的写法必须被抓住。"""

    @pytest.mark.parametrize(
        "target",
        [
            "apps.pdf_splitting.services.split",
            "apps.pdf_splitting.services.split.pipeline",
            "apps.pdf_splitting.services.split.service",
            "apps.pdf_splitting.services.split.ocr_handler",
        ],
    )
    def test_深层点号被判为不安全(self, target: str) -> None:
        assert check_cov_args.is_unsafe(target) is True

    def test_崩溃边界就在split这一层(self) -> None:
        """实测：`...services` 正常，再加一层 `.split` 就崩。

        `.split/__init__.py` 里有 `from .service import PdfSplitService`，
        而 `service.py` 顶层 import pymupdf —— 那是 coverage 主动 import 建追踪时
        被拉起来的入口。
        """
        assert check_cov_args.is_unsafe("apps.pdf_splitting.services") is False
        assert check_cov_args.is_unsafe("apps.pdf_splitting.services.split") is True


class TestSafeDetection:
    """正常的写法不能被误伤——误伤会让守卫失去可信度。"""

    @pytest.mark.parametrize(
        "target",
        [
            "apps",
            "apps.pdf_splitting",
            "apps.pdf_splitting.services",
            # 路径形式无论如何都安全（不走「主动 import 建追踪」那条路）
            "apps/pdf_splitting",
            "apps/pdf_splitting/services/split",
            "apps/pdf_splitting/services/split/pipeline.py",
        ],
    )
    def test_安全写法不被误判(self, target: str) -> None:
        assert check_cov_args.is_unsafe(target) is False

    @pytest.mark.parametrize(
        "target",
        [
            # 同为深层点号，但不碰 pymupdf —— 实测不崩，不能误报
            "apps.cases.services.case.case_admin_export_bridge",
            "apps.client.services.text_parser",
            "apps.contracts.services.contract.admin_workflows.clone_workflow",
            "apps.enterprise_data.services.clients.api_key_pool",
        ],
    )
    def test_其他深层点号不误报(self, target: str) -> None:
        """这些是 Makefile 里 CI 实际在用的参数，误报就等于制造噪音。"""
        assert check_cov_args.is_unsafe(target) is False

    def test_空值不报错(self) -> None:
        assert check_cov_args.is_unsafe("") is False
        assert check_cov_args.is_unsafe("   ") is False

    def test_前缀相近但不属于该包的模块不误报(self) -> None:
        """`split` 作为子串出现在别的包名里，不该被当成崩溃包。"""
        assert check_cov_args.is_unsafe("apps.pdf_splitting.services.splitting_helper") is False


class TestCli:
    """命令行入口的退出码——CI/开发者脚本会据此判断。"""

    def test_发现不安全参数时返回1(self) -> None:
        assert check_cov_args.main(["apps.pdf_splitting.services.split"]) == 1

    def test_全部安全时返回0(self) -> None:
        assert check_cov_args.main(["apps", "apps/pdf_splitting"]) == 0

    def test_扫描仓库配置不应发现不安全参数(self) -> None:
        """仓库自身的 Makefile / pytest.ini / CI 配置必须是干净的。

        这条相当于一道回归门:将来谁在 Makefile 里加了深层点号,CI 会红。
        """
        assert check_cov_args.main(["--scan"]) == 0
