"""当事人 ID 卡合并校验与 JSON 导入校验单元测试。"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from apps.client.services.id_card_merge.validation import (
    is_convex_quadrilateral,
    order_corners,
    validate_corners,
    validate_image_format,
    validate_image_size,
)
from apps.client.services.importer.validator import ClientJsonImportValidator
from apps.core.exceptions import ValidationException


# ── validate_image_format ──────────────────────────────────────────────────

def test_validate_image_format_valid() -> None:
    """有效格式返回 None。"""
    image = SimpleNamespace(content_type="image/jpeg", name="photo.jpg")
    result = validate_image_format(
        image,
        supported_formats={"image/jpeg", "image/png"},
        supported_extensions={".jpg", ".jpeg", ".png"},
    )
    assert result is None


def test_validate_image_format_invalid_content_type() -> None:
    """无效 content_type 返回错误。"""
    image = SimpleNamespace(content_type="image/gif", name="photo.gif")
    result = validate_image_format(
        image,
        supported_formats={"image/jpeg", "image/png"},
        supported_extensions={".jpg", ".png"},
    )
    assert result is not None
    assert result["success"] is False
    assert result["error"] == "INVALID_IMAGE_FORMAT"


def test_validate_image_format_invalid_extension() -> None:
    """无效扩展名返回错误。"""
    image = SimpleNamespace(content_type="image/jpeg", name="photo.gif")
    result = validate_image_format(
        image,
        supported_formats={"image/jpeg", "image/png"},
        supported_extensions={".jpg", ".png"},
    )
    assert result is not None
    assert result["error"] == "INVALID_IMAGE_FORMAT"


def test_validate_image_format_no_content_type() -> None:
    """无 content_type 时仅检查扩展名。"""
    image = SimpleNamespace(content_type=None, name="photo.jpg")
    result = validate_image_format(
        image,
        supported_formats={"image/jpeg"},
        supported_extensions={".jpg"},
    )
    assert result is None


# ── validate_image_size ────────────────────────────────────────────────────

def test_validate_image_size_valid() -> None:
    """足够大的图片返回 None。"""
    image = np.zeros((500, 600, 3), dtype=np.uint8)
    result = validate_image_size(image, "正面", min_image_size=200)
    assert result is None


def test_validate_image_size_too_small() -> None:
    """太小的图片返回错误。"""
    image = np.zeros((50, 50, 3), dtype=np.uint8)
    result = validate_image_size(image, "正面", min_image_size=200)
    assert result is not None
    assert result["error"] == "IMAGE_TOO_SMALL"


def test_validate_image_size_borderline() -> None:
    """刚好达到最小尺寸返回 None。"""
    image = np.zeros((200, 200, 3), dtype=np.uint8)
    result = validate_image_size(image, "正面", min_image_size=200)
    assert result is None


# ── order_corners ──────────────────────────────────────────────────────────

def test_order_corners_basic() -> None:
    """基本角点排序。"""
    corners = np.array([
        [100, 100],  # top-left
        [300, 100],  # top-right
        [300, 200],  # bottom-right
        [100, 200],  # bottom-left
    ], dtype=np.float32)
    ordered = order_corners(corners)
    assert ordered.shape == (4, 2)
    # top-left 应有最小 sum
    assert ordered[0][0] + ordered[0][1] <= ordered[2][0] + ordered[2][1]


# ── validate_corners ───────────────────────────────────────────────────────

def test_validate_corners_valid() -> None:
    """有效四角坐标返回 None。"""
    corners = [[100, 100], [300, 100], [300, 200], [100, 200]]
    assert validate_corners(corners) is None


def test_validate_corners_not_4_points() -> None:
    """非 4 个点返回错误。"""
    assert validate_corners([[0, 0], [1, 1]]) is not None


def test_validate_corners_empty() -> None:
    """空列表返回错误。"""
    assert validate_corners([]) is not None


def test_validate_corners_invalid_point_format() -> None:
    """点格式无效返回错误。"""
    assert validate_corners([[100, 100], [300, 100], [300], [100, 200]]) is not None


def test_validate_corners_negative_coords() -> None:
    """负坐标返回错误。"""
    assert validate_corners([[-1, 0], [100, 0], [100, 100], [0, 100]]) is not None


def test_validate_corners_non_numeric() -> None:
    """非数字坐标返回错误。"""
    assert validate_corners([["a", 0], [100, 0], [100, 100], [0, 100]]) is not None


# ── is_convex_quadrilateral ────────────────────────────────────────────────

def test_is_convex_true() -> None:
    """凸四边形返回 True。"""
    corners = np.array([
        [0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]
    ], dtype=np.float32)
    assert is_convex_quadrilateral(corners) is True


def test_is_convex_wrong_count() -> None:
    """非 4 个点返回 False。"""
    corners = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]], dtype=np.float32)
    assert is_convex_quadrilateral(corners) is False


# ── ClientJsonImportValidator ──────────────────────────────────────────────

class TestClientJsonImportValidator:

    def _validator(self) -> ClientJsonImportValidator:
        return ClientJsonImportValidator()

    def test_valid_natural(self) -> None:
        """有效自然人数据不抛出异常。"""
        self._validator().validate({
            "name": "张三",
            "client_type": "natural",
        })

    def test_valid_legal(self) -> None:
        """有效法人数据不抛出异常。"""
        self._validator().validate({
            "name": "北京科技有限公司",
            "client_type": "legal",
            "legal_representative": "李四",
        })

    def test_missing_name(self) -> None:
        """缺少名称抛出异常。"""
        with pytest.raises(ValidationException):
            self._validator().validate({"client_type": "natural"})

    def test_invalid_client_type(self) -> None:
        """无效类型抛出异常。"""
        with pytest.raises(ValidationException):
            self._validator().validate({"name": "张三", "client_type": "invalid"})

    def test_missing_client_type(self) -> None:
        """缺少类型抛出异常。"""
        with pytest.raises(ValidationException):
            self._validator().validate({"name": "张三"})

    def test_legal_missing_representative(self) -> None:
        """法人缺少法定代表人抛出异常。"""
        with pytest.raises(ValidationException):
            self._validator().validate({"name": "公司", "client_type": "legal"})

    def test_identity_docs_valid(self) -> None:
        """有效证件文档不抛出异常。"""
        self._validator().validate({
            "name": "张三",
            "client_type": "natural",
            "identity_docs": [{"doc_type": "id_card", "file_path": "docs/1.pdf"}],
        })

    def test_identity_docs_not_list(self) -> None:
        """证件文档非列表抛出异常。"""
        with pytest.raises(ValidationException):
            self._validator().validate({
                "name": "张三",
                "client_type": "natural",
                "identity_docs": "not_a_list",
            })

    def test_identity_docs_missing_doc_type(self) -> None:
        """证件文档缺少 doc_type 抛出异常。"""
        with pytest.raises(ValidationException):
            self._validator().validate({
                "name": "张三",
                "client_type": "natural",
                "identity_docs": [{"file_path": "docs/1.pdf"}],
            })

    def test_identity_docs_missing_file_path(self) -> None:
        """证件文档缺少 file_path 抛出异常。"""
        with pytest.raises(ValidationException):
            self._validator().validate({
                "name": "张三",
                "client_type": "natural",
                "identity_docs": [{"doc_type": "id_card"}],
            })

    def test_identity_docs_invalid_item_type(self) -> None:
        """证件文档项非字典抛出异常。"""
        with pytest.raises(ValidationException):
            self._validator().validate({
                "name": "张三",
                "client_type": "natural",
                "identity_docs": ["not_a_dict"],
            })
