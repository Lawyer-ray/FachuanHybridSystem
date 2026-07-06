"""盖章申请表单数据类。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StampFormData:
    """盖章申请表单数据。"""

    oa_case_number: str
    file_path: str
    file_type: str = "所函"
    stamp_types: list[str] = field(default_factory=lambda: ["公章", "电子公章"])
    stamp_copies: int = 3
