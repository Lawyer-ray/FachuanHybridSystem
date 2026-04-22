"""合同模板标签。"""

from __future__ import annotations

import json
from typing import Any

from django import template

register = template.Library()


@register.filter
def get_item(dictionary: dict[Any, Any], key: Any) -> Any:
    """从字典中按 key 取值，供模板使用。用法：{{ dict|get_item:key }}"""
    return dictionary.get(key)


@register.filter
def to_json(value: Any) -> str:
    """将 Python 对象序列化为 JSON 字符串，供 Alpine.js 使用。用法：{{ data|to_json }}"""
    return json.dumps(value, ensure_ascii=False)
