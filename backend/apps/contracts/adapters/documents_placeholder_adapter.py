"""documents 归档占位符内容的 contracts 出口。

原先 contracts 直接 import documents 的**私有**函数
（``_get_lawyer_work_log_content`` / ``_generate_random_work_log_content``），
既跨模块又跨了私有边界。这里以公开薄函数封装，私有性收敛在 documents 内部。
"""

from __future__ import annotations

from datetime import date
from typing import Any


def get_lawyer_work_log_content(case: Any) -> str:
    """从案件的 CaseLog 生成律师工作日志内容（排除自动捕获日志，硬换行分隔）。"""
    from apps.documents.services.placeholders import archive

    return str(archive._get_lawyer_work_log_content(case))


def random_work_log_content(start_date: date, end_date: date) -> str:
    """为常法顾问合同按服务期随机生成律师工作日志内容（CaseLog 无内容时的兜底）。"""
    from apps.documents.services.placeholders import archive

    return str(archive._generate_random_work_log_content(start_date, end_date))
