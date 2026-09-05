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

# 每个 profile 的 params 只含「与行方默认差异」的字段；未列出的字段走通用默认值。
# 选中档案后，构建请求体时用 profile.params 覆盖默认表单，一次成档。
BANK_PROFILES: list[dict[str, Any]] = [
    {
        "id": "generic",
        "name": "通用·自定义",
        "description": "不预设银行口径，按通用默认参数手工填写",
        "tags": ["默认"],
        "params": {},
    },
    {
        "id": "bocom",
        "name": "交通银行·房贷",
        "description": "起参考：365 天计息、复利不分段（积数×收取时罚息利率）、对罚息再计复利、算至还款日前一日、首期按实际天数、提前还款补偿金 1%",
        "tags": ["365天", "复利不分段", "含罚息复利", "提前还补偿金"],
        "params": {
            "year_days": 365,
            "compound_method": "flat",
            "compound_on_interest": True,
            "compound_on_penalty": True,
            "charge_interest_on_payment_day": False,
            "first_period_interest": "prorate",
            "prepayment_compensation_rate": 1.0,
            "allocation_stance": "interest_first",
        },
    },
    {
        "id": "icbc",
        "name": "工商银行·房贷",
        "description": "起参考：360 天计息、复利逐日分段、对欠息计复利、算至还款日前一日",
        "tags": ["360天", "复利逐日", "对欠息复利"],
        "params": {
            "year_days": 360,
            "compound_method": "daily",
            "compound_on_interest": True,
            "compound_on_penalty": False,
            "charge_interest_on_payment_day": False,
            "allocation_stance": "interest_first",
        },
    },
    {
        "id": "ccb",
        "name": "建设银行·房贷",
        "description": "起参考：360 天计息、复利逐日分段、对欠息计复利、含还款日当日（逾期天数口径）",
        "tags": ["360天", "复利逐日", "含还款日"],
        "params": {
            "year_days": 360,
            "compound_method": "daily",
            "compound_on_interest": True,
            "compound_on_penalty": False,
            "charge_interest_on_payment_day": True,
            "allocation_stance": "interest_first",
        },
    },
    {
        "id": "boc",
        "name": "中国银行·房贷",
        "description": "起参考：360 天计息、复利逐日分段、对欠息计复利、算至还款日前一日",
        "tags": ["360天", "复利逐日", "对欠息复利"],
        "params": {
            "year_days": 360,
            "compound_method": "daily",
            "compound_on_interest": True,
            "compound_on_penalty": False,
            "charge_interest_on_payment_day": False,
            "allocation_stance": "interest_first",
        },
    },
    {
        "id": "abc",
        "name": "农业银行·房贷",
        "description": "起参考：360 天计息、复利逐日分段、对欠息计复利、算至还款日前一日",
        "tags": ["360天", "复利逐日", "对欠息复利"],
        "params": {
            "year_days": 360,
            "compound_method": "daily",
            "compound_on_interest": True,
            "compound_on_penalty": False,
            "charge_interest_on_payment_day": False,
            "allocation_stance": "interest_first",
        },
    },
    {
        "id": "cmb",
        "name": "招商银行·房贷",
        "description": "起参考：360 天计息、复利逐日分段、对欠息计复利、算至还款日前一日",
        "tags": ["360天", "复利逐日", "对欠息复利"],
        "params": {
            "year_days": 360,
            "compound_method": "daily",
            "compound_on_interest": True,
            "compound_on_penalty": False,
            "charge_interest_on_payment_day": False,
            "allocation_stance": "interest_first",
        },
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
