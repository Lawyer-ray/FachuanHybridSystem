"""自动生成的归档分类学习规则。

此文件由"学习分类规则"功能自动生成，请勿手动编辑。
如需调整规则，请在 Admin 后台修改 ArchiveClassificationRule 后重新导出。

学习规则格式与 archive_classifier.py 中 _FILENAME_KEYWORD_TO_ARCHIVE_CODE 一致，
分类时优先使用学习规则，硬编码规则作为兜底。
"""
from __future__ import annotations

# 从已归档材料中学习到的文件名关键词 → archive_item_code 映射
LEARNED_FILENAME_KEYWORD_TO_ARCHIVE_CODE: dict[str, dict[str, list[str]]] = {
    "criminal": {
        "cr_1": ["案卷封面"],
        "cr_16": ["办案服务质量监督卡", "合同正本与律师办案服务质量监督卡"],
        "cr_17": ["办案小结"],
        "cr_2": ["结案归档登记表"],
        "cr_3": ["案卷目录"],
        "cr_6": ["律师办案工作日记"],
    },
    "litigation": {
        "lt_1": ["案卷封面"],
        "lt_11": ["受理通知", "缴纳保全费通知书"],
        "lt_18": ["办案服务质量监督卡", "合同正本与律师办案服务质量监督卡"],
        "lt_19": ["办案小结"],
        "lt_2": ["结案归档登记表"],
        "lt_3": ["案卷目录"],
        "lt_6": ["律师办案工作日记"],
    },
}
