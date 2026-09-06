"""银行房贷逾期计算器「口径档案」预设.

用途：
    把不同银行房贷逾期诉讼在 计息/复利/冲抵/违约金/首期 等方面的差异，
    沉淀为可编辑的数据档案。前端选中某行档案后，一次性填好计算器表单；
    后端算法本身不感知银行 —— 算法只接收显式参数，档案只在调用层（表单/API）
    应用，从而保证「加一家银行 = 加一段数据，不改一行算法」。

重要约定：
    以下数值为「常见口径的起始模板」，并非任何银行合同条款的精确复刻；
    实际使用必须对照具体贷款合同核对、修改后再引用结果。
    档案中的字段名与 mortgage-default-calculate 接口参数一一对应。
"""

from __future__ import annotations

from typing import Any

# 仅保留「通用」档案。曾预置的银行口径（交行/工行/建行/中行/农行/招行）为
# 未经验证的常识模板，已删除；如后续拿到真实合同条款，按同一结构增补。
BANK_PROFILES: list[dict[str, Any]] = [
    {
        "id": "generic",
        "name": "通用·自定义",
        "description": "不预设银行口径，按通用默认参数手工填写",
        "tags": ["默认"],
        "params": {},
    },
]


def list_bank_profiles() -> list[dict[str, Any]]:
    """返回档案元信息列表（含 params，供前端一键填充计算器表单）."""
    return [
        {
            "id": p["id"],
            "name": p["name"],
            "description": p["description"],
            "tags": p.get("tags", []),
            "params": dict(p.get("params") or {}),
        }
        for p in BANK_PROFILES
    ]


def get_bank_profile_params(profile_id: str) -> dict[str, Any]:
    """按 id 返回档案 params；未知 id 返回空 dict（等同通用默认）."""
    for p in BANK_PROFILES:
        if p["id"] == profile_id:
            return dict(p.get("params") or {})
    return {}
