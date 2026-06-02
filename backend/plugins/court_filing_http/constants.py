from __future__ import annotations

_BASE = "https://zxfw.court.gov.cn/yzw"
_OSS_BUCKET = "https://zxfy2-oss.oss-cn-north-2-gov-1.aliyuncs.com"

PROVINCE_CODES: dict[str, str] = {
    "广东省": "440000",
    "北京市": "110000",
    "上海市": "310000",
    "浙江省": "330000",
    "江苏省": "320000",
    "湖南省": "430000",
    "湖北省": "420000",
    "四川省": "510000",
    "福建省": "350000",
    "山东省": "370000",
    "河南省": "410000",
    "河北省": "130000",
    "陕西省": "610000",
    "重庆市": "500000",
    "天津市": "120000",
}

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
