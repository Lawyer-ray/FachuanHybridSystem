"""归档材料管理 API Schema。"""

from __future__ import annotations

from typing import Any

from ninja import Schema


class ReorderIn(Schema):
    orders: dict[str, list[int]]


class MoveIn(Schema):
    target_code: str


class SuccessOut(Schema):
    success: bool = True


class ClearAllOut(Schema):
    success: bool = True
    deleted_count: int = 0


class GenerateArchiveFolderOut(Schema):
    """生成归档文件夹输出"""

    success: bool = True
    generated_docs: list[str] = []
    archive_dir: str = ""
    errors: list[str] = []


class ToggleCompactOut(Schema):
    """精简视图切换输出"""

    success: bool = True
    compact_archive: bool = False


class ChecklistItemOut(Schema):
    """检查清单项输出"""

    code: str
    name: str
    template: str | None = None
    required: bool
    auto_detect: str | None = None
    source: str
    completed: bool = False
    material_ids: list[int] = []
    materials: list[dict[str, Any]] = []
    has_case_material: bool = False


class ChecklistOut(Schema):
    """检查清单输出"""

    archive_category: str
    archive_category_label: str
    compact_archive: bool = False
    items: list[ChecklistItemOut]
    completed_count: int = 0
    total_count: int = 0
    required_completed_count: int = 0
    required_total_count: int = 0
    completion_percentage: float = 0.0


class UploadArchiveItemOut(Schema):
    """上传归档材料输出"""

    id: int = 0
    filename: str = ""


class ConfirmArchiveOut(Schema):
    """确认归档输出"""

    success: bool = True
    message: str = ""


class SyncCaseMaterialsOut(Schema):
    """同步案件材料输出"""

    success: bool = True
    synced_count: int = 0
    message: str = ""


class ScaleToA4Out(Schema):
    """A4缩放输出"""

    success: bool = True
    scaled_count: int = 0
    message: str = ""


class LearnRulesOut(Schema):
    """学习分类规则输出"""

    success: bool = True
    learned: int = 0
    updated: int = 0
    skipped: int = 0
    message: str = ""
