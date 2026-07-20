#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import os
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
_project_root_str = str(_project_root)
if _project_root_str not in sys.path:
    sys.path.insert(0, _project_root_str)

# 让 Django 开发服务器监控 plugins 目录变更
_plugins_dir = _project_root / "plugins"
if _plugins_dir.is_dir():
    os.environ.setdefault("RUNPY_EXTRA_WATCH_DIRS", str(_plugins_dir))


def main() -> None:
    """Run administrative tasks."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")

    # Django 4.1+ 支持 --watch 选项
    if "--watch" not in sys.argv and _plugins_dir.is_dir():
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
