"""完整的默认数据配置 - 包含文件模板、文件夹模板和绑定关系"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DATA_FILE = Path(__file__).with_name("complete_defaults.json")


def get_complete_default_data() -> dict[str, Any]:
    """
    获取完整的默认数据配置

    Returns:
        包含文件模板、文件夹模板和绑定关系的字典
    """
    return json.loads(_DATA_FILE.read_text(encoding="utf-8"))
