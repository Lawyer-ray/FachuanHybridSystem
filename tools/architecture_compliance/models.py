"""
架构合规性工具的数据模型

定义违规、重构结果、报告等核心数据结构。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Violation:
    """违规基类"""

    file_path: str
    line_number: int
    code_snippet: str
    violation_type: str
    severity: str  # 'high', 'medium', 'low'
    description: str

    def to_dict(self) -> dict[str, object]:
        """转换为字典"""
        return asdict(self)

    def to_json(self) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


@dataclass
class ApiViolation(Violation):
    """API层违规：直接数据库访问"""

    model_name: str = ""
    orm_method: str = ""  # 'objects.filter', 'objects.get', etc.
    suggested_service_method: str = ""


@dataclass
class ServiceViolation(Violation):
    """Service层违规：跨模块导入或静态方法滥用"""

    violation_subtype: str = ""  # 'cross_module_import', 'static_method_abuse'
    imported_model: Optional[str] = None
    method_name: Optional[str] = None


@dataclass
class ModelViolation(Violation):
    """Model层违规：save()中包含业务逻辑"""

    model_name: str = ""
    method_name: str = ""
    business_logic_description: str = ""


@dataclass
class RefactoringResult:
    """单次重构结果"""

    success: bool
    file_path: str
    changes_made: list[str] = field(default_factory=list)
    tests_passed: bool = False
    rollback_id: Optional[str] = None
    error_message: Optional[str] = None

    def to_dict(self) -> dict[str, object]:
        """转换为字典"""
        return asdict(self)


@dataclass
class ViolationReport:
    """违规扫描报告"""

    total_violations: int
    violations_by_type: dict[str, int] = field(default_factory=dict)
    violations_by_severity: dict[str, int] = field(default_factory=dict)
    detailed_violations: list[Violation] = field(default_factory=list)
    scan_timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, object]:
        """转换为字典（datetime转为ISO格式字符串）"""
        data: dict[str, object] = {
            "total_violations": self.total_violations,
            "violations_by_type": self.violations_by_type,
            "violations_by_severity": self.violations_by_severity,
            "detailed_violations": [v.to_dict() for v in self.detailed_violations],
            "scan_timestamp": self.scan_timestamp.isoformat(),
        }
        return data

    def to_json(self) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


@dataclass
class BatchResult:
    """批次重构结果"""

    batch_id: str
    total_attempted: int = 0
    successful: int = 0
    failed: int = 0
    skipped: int = 0
    results: list[RefactoringResult] = field(default_factory=list)
    execution_time: float = 0.0

    def to_dict(self) -> dict[str, object]:
        """转换为字典"""
        return asdict(self)
