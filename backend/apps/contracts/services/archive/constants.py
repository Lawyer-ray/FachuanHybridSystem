"""归档检查清单常量定义

三种归档分类对应的检查清单项：
- non_litigation: 法律顾问及非诉事务 (11项)
- litigation: 诉讼/仲裁 (19项)
- criminal: 刑事案件 (17项)
"""

from __future__ import annotations

from typing import TypedDict


class ChecklistItem(TypedDict):
    """检查清单项"""

    code: str  # 编号，如 "4.2.6"
    name: str  # 名称
    template: str | None  # 对应的 DocumentArchiveSubType 值，None 表示非模板生成
    required: bool  # 是否必需
    auto_detect: str | None  # 自动检测类型，如 "supervision_card"
    source: str  # 材料来源: "template" | "contract" | "case" | "manual"


# ============================================================
# 法律顾问及非诉事务 (4.1)
# ============================================================
NON_LITIGATION_CHECKLIST: list[ChecklistItem] = [
    {"code": "4.1.1", "name": "案卷封面", "template": "case_cover", "required": True, "auto_detect": None, "source": "template"},
    {"code": "4.1.2", "name": "结案归档登记表", "template": "closing_archive_register", "required": True, "auto_detect": None, "source": "template"},
    {"code": "4.1.3", "name": "案卷目录", "template": "inner_catalog", "required": True, "auto_detect": None, "source": "template"},
    {"code": "4.1.4", "name": "委托合同（客户授权证明材料等）", "template": None, "required": True, "auto_detect": None, "source": "contract"},
    {"code": "4.1.5", "name": "收费凭证", "template": None, "required": False, "auto_detect": None, "source": "contract"},
    {"code": "4.1.6", "name": "律师办案工作日记", "template": "lawyer_work_log", "required": True, "auto_detect": None, "source": "template"},
    {"code": "4.1.7", "name": "委托人提供的案件材料", "template": None, "required": False, "auto_detect": None, "source": "case"},
    {"code": "4.1.8", "name": "法律意见书、律师函等", "template": None, "required": False, "auto_detect": None, "source": "case"},
    {"code": "4.1.9", "name": "案件其它关联材料", "template": None, "required": False, "auto_detect": None, "source": "case"},
    {"code": "4.1.10", "name": "办案质量监督卡", "template": None, "required": True, "auto_detect": "supervision_card", "source": "manual"},
    {"code": "4.1.11", "name": "办案小结", "template": "case_summary", "required": True, "auto_detect": None, "source": "template"},
]

# ============================================================
# 诉讼/仲裁 (4.2)
# ============================================================
LITIGATION_CHECKLIST: list[ChecklistItem] = [
    {"code": "4.2.1", "name": "案卷封面", "template": "case_cover", "required": True, "auto_detect": None, "source": "template"},
    {"code": "4.2.2", "name": "结案归档登记表", "template": "closing_archive_register", "required": True, "auto_detect": None, "source": "template"},
    {"code": "4.2.3", "name": "案卷目录", "template": "inner_catalog", "required": True, "auto_detect": None, "source": "template"},
    {"code": "4.2.4", "name": "委托合同、风险告知书、授权委托证明材料等", "template": None, "required": True, "auto_detect": None, "source": "contract"},
    {"code": "4.2.5", "name": "收费凭证", "template": None, "required": False, "auto_detect": None, "source": "contract"},
    {"code": "4.2.5.1", "name": "律师办案工作日记", "template": "lawyer_work_log", "required": True, "auto_detect": None, "source": "template"},
    {"code": "4.2.6", "name": "起诉书、上诉书或答辩书", "template": None, "required": True, "auto_detect": None, "source": "case"},
    {"code": "4.2.7", "name": "阅卷笔录", "template": None, "required": False, "auto_detect": None, "source": "case"},
    {"code": "4.2.8", "name": "会见当事人谈话笔录", "template": None, "required": False, "auto_detect": None, "source": "case"},
    {"code": "4.2.9", "name": "调查材料等案件关联材料", "template": None, "required": False, "auto_detect": None, "source": "case"},
    {"code": "4.2.10", "name": "诉讼保全申请书、证据保全申请书、先行给付申请书和法院裁定书", "template": None, "required": False, "auto_detect": None, "source": "case"},
    {"code": "4.2.11", "name": "承办律师代理意见", "template": None, "required": False, "auto_detect": None, "source": "case"},
    {"code": "4.2.12", "name": "集体讨论记录", "template": None, "required": False, "auto_detect": None, "source": "case"},
    {"code": "4.2.13", "name": "出庭通知书", "template": None, "required": False, "auto_detect": None, "source": "case"},
    {"code": "4.2.14", "name": "代理词", "template": None, "required": False, "auto_detect": None, "source": "case"},
    {"code": "4.2.15", "name": "庭审笔录", "template": None, "required": False, "auto_detect": None, "source": "case"},
    {"code": "4.2.16", "name": "判决书、裁定书、调解书、上诉书", "template": None, "required": True, "auto_detect": None, "source": "case"},
    {"code": "4.2.17", "name": "办案服务质量监督卡", "template": None, "required": True, "auto_detect": "supervision_card", "source": "manual"},
    {"code": "4.2.18", "name": "办案小结", "template": "case_summary", "required": True, "auto_detect": None, "source": "template"},
]

# ============================================================
# 刑事案件 (4.3)
# ============================================================
CRIMINAL_CHECKLIST: list[ChecklistItem] = [
    {"code": "4.3.1", "name": "案卷封面", "template": "case_cover", "required": True, "auto_detect": None, "source": "template"},
    {"code": "4.3.2", "name": "结案归档登记表", "template": "closing_archive_register", "required": True, "auto_detect": None, "source": "template"},
    {"code": "4.3.3", "name": "案卷目录", "template": "inner_catalog", "required": True, "auto_detect": None, "source": "template"},
    {"code": "4.3.4", "name": "委托代理合同、风险告知书、授权委托证明材料等", "template": None, "required": True, "auto_detect": None, "source": "contract"},
    {"code": "4.3.5", "name": "收费凭证", "template": None, "required": False, "auto_detect": None, "source": "contract"},
    {"code": "4.3.6", "name": "律师办案工作日记", "template": "lawyer_work_log", "required": True, "auto_detect": None, "source": "template"},
    {"code": "4.3.7", "name": "会见被告人、委托人、证人笔录", "template": None, "required": False, "auto_detect": None, "source": "case"},
    {"code": "4.3.8", "name": "调查材料等案件关联材料", "template": None, "required": False, "auto_detect": None, "source": "case"},
    {"code": "4.3.9", "name": "承办人提出的辩护或代理意见", "template": None, "required": False, "auto_detect": None, "source": "case"},
    {"code": "4.3.10", "name": "集体讨论记录", "template": None, "required": False, "auto_detect": None, "source": "case"},
    {"code": "4.3.11", "name": "起诉书、上诉书", "template": None, "required": True, "auto_detect": None, "source": "case"},
    {"code": "4.3.12", "name": "辩护词或代理词", "template": None, "required": False, "auto_detect": None, "source": "case"},
    {"code": "4.3.13", "name": "出庭通知书", "template": None, "required": False, "auto_detect": None, "source": "case"},
    {"code": "4.3.14", "name": "裁定书、判决书", "template": None, "required": True, "auto_detect": None, "source": "case"},
    {"code": "4.3.15", "name": "上诉书、抗诉书", "template": None, "required": False, "auto_detect": None, "source": "case"},
    {"code": "4.3.16", "name": "办案服务质量监督卡", "template": None, "required": True, "auto_detect": "supervision_card", "source": "manual"},
    {"code": "4.3.17", "name": "办案小结", "template": "case_summary", "required": True, "auto_detect": None, "source": "template"},
]

# 按归档分类组织的完整检查清单
ARCHIVE_CHECKLIST: dict[str, list[ChecklistItem]] = {
    "non_litigation": NON_LITIGATION_CHECKLIST,
    "litigation": LITIGATION_CHECKLIST,
    "criminal": CRIMINAL_CHECKLIST,
}
