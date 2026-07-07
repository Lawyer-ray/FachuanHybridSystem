"""归档材料提交表单数据类。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ArchiveFormData:
    """归档材料提交表单数据。"""

    oa_case_number: str
    file_paths: list[str] = field(default_factory=list)
    description: str = "详见卷宗"
