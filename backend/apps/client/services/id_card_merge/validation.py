"""Business logic services."""

from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from django.core.files.uploadedfile import UploadedFile


def validate_image_format(
    image: UploadedFile,
    *,
    supported_formats: set[str],
    supported_extensions: set[str],
) -> dict[str, Any] | None:
    content_type = getattr(image, "content_type", None)
    if content_type and content_type.lower() not in supported_formats:
        return {
            "success": False,
            "error": "INVALID_IMAGE_FORMAT",
            "message": f"不支持的图片格式: {content_type},请上传 JPG 或 PNG 格式",
        }

    filename = getattr(image, "name", "")
    if filename:
        ext = Path(filename).suffix
        if ext.lower() not in supported_extensions:
            return {
                "success": False,
                "error": "INVALID_IMAGE_FORMAT",
                "message": f"不支持的文件扩展名: {ext},请上传 JPG 或 PNG 格式",
            }
    return None


def validate_image_size(image: NDArray[np.uint8], name: str, *, min_image_size: int) -> dict[str, Any] | None:
    height, width = image.shape[:2]
    if width < min_image_size or height < min_image_size:
        return {
            "success": False,
            "error": "IMAGE_TOO_SMALL",
            "message": f"{name}图片分辨率太低 ({width}x{height}),请上传更高分辨率的图片",
        }
    return None


def order_corners(corners: NDArray[np.float32]) -> NDArray[np.float32]:
    corners = corners.astype(np.float32)
    sum_coords = corners[:, 0] + corners[:, 1]
    diff_coords = corners[:, 0] - corners[:, 1]

    ordered = np.zeros((4, 2), dtype=np.float32)
    ordered[0] = corners[np.argmin(sum_coords)]
    ordered[2] = corners[np.argmax(sum_coords)]
    ordered[1] = corners[np.argmax(diff_coords)]
    ordered[3] = corners[np.argmin(diff_coords)]
    return ordered


def validate_corners(corners: list[list[int]]) -> str | None | None:
    if not corners or len(corners) != 4:
        return "必须提供 4 个角点坐标"

    for i, point in enumerate(corners):
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            return f"第 {i + 1} 个点格式无效,应为 [x, y]"

        try:
            x, y = int(point[0]), int(point[1])
            if x < 0 or y < 0:
                return f"第 {i + 1} 个点坐标不能为负数"
        except (TypeError, ValueError):
            return f"第 {i + 1} 个点坐标必须为数字"

    corners_np = np.array(corners, dtype=np.float32)
    ordered = order_corners(corners_np)

    if not is_convex_quadrilateral(ordered):
        return "四角坐标不构成凸四边形"

    return None


def is_convex_quadrilateral(corners: NDArray[np.float32]) -> bool:
    n = len(corners)
    if n != 4:
        return False

    cross_products = []
    for i in range(n):
        p1 = corners[i]
        p2 = corners[(i + 1) % n]
        p3 = corners[(i + 2) % n]

        v1 = p2 - p1
        v2 = p3 - p2

        cross = v1[0] * v2[1] - v1[1] * v2[0]
        cross_products.append(cross)

    positive_count = sum(1 for cp in cross_products if cp > 1e-6)
    negative_count = sum(1 for cp in cross_products if cp < -1e-6)
    return positive_count == 4 or negative_count == 4
