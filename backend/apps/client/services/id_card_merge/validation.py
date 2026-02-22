"""图片与坐标校验。"""

from pathlib import Path
from typing import Any

from django.core.files.uploadedfile import UploadedFile
from django.utils.translation import gettext as _

import numpy as np
from numpy.typing import NDArray


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
            "message": _("不支持的图片格式: %(ct)s，请上传 JPG 或 PNG 格式") % {"ct": content_type},
        }

    filename = getattr(image, "name", "")
    if filename:
        ext = Path(filename).suffix
        if ext.lower() not in supported_extensions:
            return {
                "success": False,
                "error": "INVALID_IMAGE_FORMAT",
                "message": _("不支持的文件扩展名: %(ext)s，请上传 JPG 或 PNG 格式") % {"ext": ext},
            }
    return None


def validate_image_size(image: NDArray[np.uint8], name: str, *, min_image_size: int) -> dict[str, Any] | None:
    height, width = image.shape[:2]
    if width < min_image_size or height < min_image_size:
        return {
            "success": False,
            "error": "IMAGE_TOO_SMALL",
            "message": _("%(name)s图片分辨率太低 (%(w)sx%(h)s)，请上传更高分辨率的图片") % {"name": name, "w": width, "h": height},
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


def validate_corners(corners: list[list[int]]) -> str | None:
    if not corners or len(corners) != 4:
        return _("必须提供 4 个角点坐标")

    for i, point in enumerate(corners):
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            return _("第 %(n)s 个点格式无效，应为 [x, y]") % {"n": i + 1}

        try:
            x, y = int(point[0]), int(point[1])
            if x < 0 or y < 0:
                return _("第 %(n)s 个点坐标不能为负数") % {"n": i + 1}
        except (TypeError, ValueError):
            return _("第 %(n)s 个点坐标必须为数字") % {"n": i + 1}

    corners_np = np.array(corners, dtype=np.float32)
    ordered = order_corners(corners_np)

    if not is_convex_quadrilateral(ordered):
        return _("四角坐标不构成凸四边形")

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
