from __future__ import annotations

_BASE = "https://zxfw.court.gov.cn/yzw"
_OSS_BUCKET = "https://zxfy2-oss.oss-cn-north-2-gov-1.aliyuncs.com"

PROVINCE_CODES: dict[str, str] = {
    "北京市": "110000",
    "天津市": "120000",
    "河北省": "130000",
    "山西省": "140000",
    "内蒙古自治区": "150000",
    "辽宁省": "210000",
    "吉林省": "220000",
    "黑龙江省": "230000",
    "上海市": "310000",
    "江苏省": "320000",
    "浙江省": "330000",
    "安徽省": "340000",
    "福建省": "350000",
    "江西省": "360000",
    "山东省": "370000",
    "河南省": "410000",
    "湖北省": "420000",
    "湖南省": "430000",
    "广东省": "440000",
    "广西壮族自治区": "450000",
    "海南省": "460000",
    "重庆市": "500000",
    "四川省": "510000",
    "贵州省": "520000",
    "云南省": "530000",
    "西藏自治区": "540000",
    "陕西省": "610000",
    "甘肃省": "620000",
    "青海省": "630000",
    "宁夏回族自治区": "640000",
    "新疆维吾尔自治区": "650000",
}

# 反向映射：省份代码 → 省份名称
_CODE_TO_PROVINCE: dict[str, str] = {v: k for k, v in PROVINCE_CODES.items()}


def resolve_province_code(province: str) -> str:
    """将省份名称解析为行政区划代码。

    支持精确匹配和模糊匹配（如 "广西" → "广西壮族自治区"）。
    找不到时抛出 ValueError，避免静默回退到错误省份。
    """
    if province in PROVINCE_CODES:
        return PROVINCE_CODES[province]

    # 模糊匹配：短名包含在全名中（如 "广西" 在 "广西壮族自治区" 里）
    for full_name, code in PROVINCE_CODES.items():
        if province in full_name or full_name.startswith(province):
            return code

    supported = "、".join(sorted(PROVINCE_CODES.keys()))
    raise ValueError(
        f"不支持的省份「{province}」，未找到对应行政区划代码。"
        f"支持的省份：{supported}"
    )


CASE_TYPE_CODES: dict[str, str] = {
    "民事一审": "1501_000001-0301",
    "民事二审": "1501_000001-0302",
    "行政一审": "1501_000001-0401",
    "行政二审": "1501_000001-0402",
    "刑事自诉": "1501_000001-0201",
    "国家赔偿": "1501_000001-0510",
    "申请执行": "1501_000001-1002",
}

PARTY_ROLE_CODES: dict[str, str] = {
    "plaintiff": "1501_030109-1",
    "defendant": "1501_030109-2",
    "third_party": "1501_030109-3",
}

EXEC_PARTY_ROLE_CODES: dict[str, str] = {
    "plaintiff": "1501_100225-1",
    "defendant": "1501_100225-2",
}

MATERIAL_CLLX: dict[str, str] = {
    "0": "11800016-2",
    "1": "11800016-1",
    "2": "11800016-9",
    "3": "11800016-4",
    "4": "11800016-254",
    "5": "11800016-3",
}
MATERIAL_CLMC: dict[str, str] = {
    "0": "起诉状",
    "1": "当事人身份证明",
    "2": "委托代理人委托手续和身份材料",
    "3": "证据目录及证据材料",
    "4": "送达地址确认书",
    "5": "其他材料",
}

EXEC_MATERIAL_CLLX: dict[str, str] = {
    "0": "11800016-2",
    "1": "11800016-8",
    "2": "11800016-9",
    "3": "11800016-1",
    "4": "11800016-254",
}
EXEC_MATERIAL_CLMC: dict[str, str] = {
    "0": "执行申请书",
    "1": "执行依据文书",
    "2": "授权委托书及代理人身份证明",
    "3": "申请人身份材料",
    "4": "送达地址确认书",
}

EXECUTION_TARGET_CODE_MONEY = "1501_100279-1"
EXECUTION_TARGET_CODE_BEHAVIOR = "1501_100279-3"
EXECUTION_TARGET_CODE_PROPERTY_RIGHT = "1501_100279-4"
EXECUTION_TARGET_CODE_MOVABLE = "1501_100279-5"
EXECUTION_TARGET_CODE_IMMOVABLE = "1501_100279-6"
EXECUTION_TARGET_ALLOWED_CODES = {
    EXECUTION_TARGET_CODE_MONEY,
    EXECUTION_TARGET_CODE_BEHAVIOR,
    EXECUTION_TARGET_CODE_PROPERTY_RIGHT,
    EXECUTION_TARGET_CODE_MOVABLE,
    EXECUTION_TARGET_CODE_IMMOVABLE,
}
