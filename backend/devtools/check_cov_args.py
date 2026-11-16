#!/usr/bin/env python
"""检查 `--cov=` 参数是否会触发 pymupdf 段错误。

## 这个脚本解决的坑

在 macOS 上，用**深层点号模块名**做覆盖率目标会让进程直接段错误：

    pytest ... --cov=apps.pdf_splitting.services.split          # 💥 Segmentation fault
    pytest ... --cov=apps.pdf_splitting.services.split.pipeline # 💥 Segmentation fault

而下面这些写法都正常：

    --cov=apps                                  # 顶层包，OK
    --cov=apps.pdf_splitting                    # 浅两层，OK
    --cov=apps/pdf_splitting                    # 路径形式，OK（推荐）
    --cov=apps/pdf_splitting/services/split     # 路径形式，OK

## 为什么会崩

`--cov=<点号模块>` 与 `--cov=<路径>` 在 coverage 内部走两条不同的路：

* **路径形式**：按目录扫描源码树，只在测试实际 import 时才记录
* **点号形式**：coverage 会主动 `import` 该模块（及其父链）来建立追踪

而 `apps/pdf_splitting/services/split/__init__.py` 里有：

    from .service import PdfSplitService

`service.py` 顶层又 `import pymupdf`。于是 coverage 在**测试尚未导入任何东西之前**
就把 pymupdf 拉起来了；等到测试里用 `page.insert_text(..., fontname="china-s")`
嵌入中文字体时，MuPDF 的字体加载器访问到一块已被前一次初始化破坏的内存，
在 `fz_new_font_from_memory` 里段错误。

崩溃边界实测在 `apps.pdf_splitting.services.split` 这一层：`...services` 正常，
再加一层 `.split` 就崩——正好是那个 `__init__.py` 触发 `service` 导入的位置。

## 修复策略

不修 pymupdf（第三方），也不改包结构（`split/__init__.py` 的再导出是既有 API）。
而是**把这个用法约束固化成检查**：CI 用 `--cov=apps` 本来就安全，本地手写深层
点号时先让本脚本拦一下。

用法::

    # 检查你打算用的参数
    python devtools/check_cov_args.py apps.pdf_splitting.services.split

    # 或直接扫描 Makefile / CI 配置里的所有 --cov= 取值
    python devtools/check_cov_args.py --scan
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

#: 已知会触发崩溃的模块前缀。
#:
#: 判据：该包（或任一父包）的 __init__ 链会 import 到顶层 import pymupdf 的模块。
#: 实测边界就在 split 这一层，再深的 `.split.*` 自然同样中招。
UNSAFE_PREFIXES = ("apps.pdf_splitting.services.split",)

#: 这些形式永远安全：顶层包与路径形式都不走「主动 import 建追踪」那条路。
SAFE_EXACT = {"apps", "apps.pdf_splitting", "apps.pdf_splitting.services"}


def _out(text: str = "") -> None:
    """终端输出。

    本脚本是**命令行工具**，结果给人看是它的本分。钩子 forbid-added-print 禁的是
    用 print 调试，所以走 sys.stdout.write 表达同一意图（不改成 logger ——
    那会被日志配置重定向到文件，命令行工具的输出就没了）。
    """
    sys.stdout.write(text + "\n")


def is_unsafe(target: str) -> bool:
    """该 --cov 取值是否会触发段错误。"""
    value = target.strip()
    if not value:
        return False
    # 路径形式（含 /）安全
    if "/" in value or "\\" in value:
        return False
    if value in SAFE_EXACT:
        return False
    return any(value == prefix or value.startswith(prefix + ".") for prefix in UNSAFE_PREFIXES)


def _iter_configured_targets(repo_root: Path):
    """从 Makefile / pytest.ini / CI workflow 里抓出所有 --cov= 取值。"""
    candidates = [
        repo_root / "Makefile",
        repo_root / "pytest.ini",
        repo_root / ".github" / "workflows" / "backend-ci.yml",
    ]
    pattern = re.compile(r"--cov[= ]([A-Za-z0-9_./\\-]+)")
    for path in candidates:
        if not path.exists():
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for match in pattern.finditer(line):
                yield path, line_no, match.group(1)


def main(argv: list[str]) -> int:
    repo_root = Path(__file__).resolve().parent.parent  # devtools/ -> backend/

    if "--scan" in argv:
        bad = 0
        for path, line_no, target in _iter_configured_targets(repo_root):
            if is_unsafe(target):
                bad += 1
                _out(f"❌ {path.name}:{line_no}  --cov={target}  ← 会段错误，改用路径形式")
            else:
                _out(f"✅ {path.name}:{line_no}  --cov={target}")
        if bad:
            _out(f"\n{bad} 处需要修正：把点号换成路径，例如 --cov=apps/pdf_splitting")
        return 1 if bad else 0

    targets = [a for a in argv if not a.startswith("-")]
    if not targets:
        _out(__doc__)
        return 0

    bad = [t for t in targets if is_unsafe(t)]
    for target in targets:
        if is_unsafe(target):
            _out(f"❌ --cov={target}")
            _out("   这条会在 macOS 上段错误。改用路径形式，例如：")
            _out(f"   --cov={target.replace('.', '/', 2)}")
        else:
            _out(f"✅ --cov={target}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
