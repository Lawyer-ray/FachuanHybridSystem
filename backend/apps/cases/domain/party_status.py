"""当事人诉讼地位的唯一权威常量。

为什么需要这个模块
------------------
生产库 ``cases_caseparty.legal_status`` 是**中英文混存**的（英文枚举 + 早期录入的中文）。
只认英文时，中文那批当事人会被判成「哪一方都不是」，直接导致：

- 一张网立案信息里 ``plaintiff_name`` / ``defendant_name`` 为 null；
- ``our_party_is_plaintiff_side`` 变 false，前端按钮被禁用，律师看到
  「我方不是原告方，本页只处理起诉立案」——完全误导；
- 担保报价接口取不到申请人，走到 ``_build_party_payload_from_case_party(party=None)``
  后因客户姓名为空直接抛 ``ValueError``。

历史教训：这套判定曾在三处各写一份并**已经漂移**（``filing`` 含中文、``guarantee`` 仅英文、
``case_readiness_service`` 少了「原审原告」），只修了一处，于是担保接口对中文案件仍然失败。
因此这里收敛为**唯一权威**，任何地方都不得再自建副本。

新增地位值时只改本文件，并跑 ``tests/ci/structure/test_party_status_single_source.py``。
"""

from __future__ import annotations

__all__: list[str] = [
    "DEFENDANT_SIDE_STATUSES",
    "EXECUTION_HINT_STATUSES",
    "PLAINTIFF_SIDE_STATUSES",
    "THIRD_SIDE_STATUSES",
    "is_defendant_side",
    "is_plaintiff_side",
]

#: 原告/申请人一侧。中文与英文并列，不可只留英文（见模块 docstring）。
PLAINTIFF_SIDE_STATUSES: frozenset[str] = frozenset(
    {
        # 英文枚举
        "plaintiff",
        "applicant",
        "appellant",
        "orig_plaintiff",
        # 早期录入的中文
        "原告",
        "申请人",
        "上诉人",
        "原审原告",
    }
)

#: 被告/被申请人一侧。
DEFENDANT_SIDE_STATUSES: frozenset[str] = frozenset(
    {
        # 英文枚举
        "defendant",
        "respondent",
        "appellee",
        "orig_defendant",
        "criminal_defendant",
        # 早期录入的中文
        "被告",
        "被申请人",
        "被上诉人",
        "原审被告",
        "刑事被告人",
    }
)

#: 第三人/被害人一侧。
THIRD_SIDE_STATUSES: frozenset[str] = frozenset(
    {
        # 英文枚举
        "third",
        "third_party",
        "orig_third",
        "victim",
        # 早期录入的中文
        "第三人",
        "原审第三人",
        "被害人",
    }
)

#: 执行程序中会出现的地位（提示用，不参与原被告判定）。
EXECUTION_HINT_STATUSES: frozenset[str] = frozenset({"applicant", "respondent"})


def _normalize(status: object) -> str:
    """统一去空白并转小写，兼容 ``" 原告 "`` 这类脏数据。"""
    return str(status or "").strip()


def is_plaintiff_side(status: object) -> bool:
    """该诉讼地位是否属于原告/申请人一侧。"""
    normalized = _normalize(status)
    if not normalized:
        return False
    return normalized in PLAINTIFF_SIDE_STATUSES or normalized.lower() in PLAINTIFF_SIDE_STATUSES


def is_defendant_side(status: object) -> bool:
    """该诉讼地位是否属于被告/被申请人一侧。"""
    normalized = _normalize(status)
    if not normalized:
        return False
    return normalized in DEFENDANT_SIDE_STATUSES or normalized.lower() in DEFENDANT_SIDE_STATUSES
