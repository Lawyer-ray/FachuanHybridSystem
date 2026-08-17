#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import multiprocessing
import os
import sys
from pathlib import Path

# macOS 上 fork() 可能因 Objective-C 运行时冲突导致子进程 crash。
# 1. 设置 spawn 为默认 start method（影响未显式指定 context 的 multiprocessing 用法）。
# 2. django-q 内部硬编码 get_context("fork")，绕过本设置，由
#    apps/core/apps.py 的 ready() 单独 patch 为 spawn。
# 3. OBJC_DISABLE_INITIALIZE_FORK_SAFETY 由 libobjc 在进程启动早期读取，
#    Python 运行时设置无效（对当前进程），兜底在 Makefile 的 qcluster 目标前置。
try:
    multiprocessing.set_start_method("spawn")
except RuntimeError:
    pass

_project_root = Path(__file__).resolve().parent.parent
_project_root_str = str(_project_root)
if _project_root_str not in sys.path:
    sys.path.insert(0, _project_root_str)

# 让 Django 开发服务器监控 plugins 目录变更
_plugins_dir = _project_root / "plugins"
if _plugins_dir.is_dir():
    os.environ.setdefault("RUNPY_EXTRA_WATCH_DIRS", str(_plugins_dir))


def _bootstrap_django() -> None:
    """在模块顶层初始化 Django（而非仅在 main() 内）。

    multiprocessing spawn 子进程的 prepare 阶段会先 re-import 本模块、
    再 unpickle Process 对象（后者触发 import django_q.cluster）。若不在
    顶层完成 setup，django_q.cluster 会在模块级自行 setup，导致
    apps.core.ready() 里的 spawn patch 撞上半初始化的 cluster 模块
    （get_mp_context 未定义）而崩溃。
    """
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")

    import django

    django.setup()


_bootstrap_django()


def main() -> None:
    """Run administrative tasks."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")

    # Django 4.1+ 支持 --watch 选项（仅用于 runserver）
    if len(sys.argv) > 1 and sys.argv[1] == "runserver" and "--watch" not in sys.argv:
        if _plugins_dir.is_dir():
            sys.argv.extend(["--watch", str(_plugins_dir)])

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
