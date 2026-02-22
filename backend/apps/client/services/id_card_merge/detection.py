"""身份证边缘检测。"""

from typing import Any, cast

import cv2
import numpy as np
from numpy.typing import NDArray

from .validation import order_corners


def detect_id_card_corners(
    image: NDArray[np.uint8],
    *,
    id_card_aspect_ratio: float,
    logger: Any,
) -> NDArray[np.float32] | None:
    if image is None or image.size == 0:
        logger.warning("输入图像为空")
        return None

    height, width = image.shape[:2]
    image_area = height * width

    edges = _compute_edges(image)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        logger.warning("未检测到任何轮廓")
        return None

    best_contour = _find_best_contour(contours, image_area, id_card_aspect_ratio)

    if best_contour is None:
        logger.warning("未找到符合身份证特征的轮廓")
        return None

    corners = best_contour.reshape(4, 2)
    ordered_corners = order_corners(corners)

    logger.info(
        "身份证检测成功",
        extra={"corners": ordered_corners.tolist(), "area": cv2.contourArea(best_contour)},
    )
    return ordered_corners


def _compute_edges(image: NDArray[np.uint8]) -> NDArray[np.uint8]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    median_val = np.median(blurred)
    lower_threshold = int(max(0, 0.7 * median_val))
    upper_threshold = int(min(255, 1.3 * median_val))
    edges = cv2.Canny(blurred, lower_threshold, upper_threshold)
    kernel = np.ones((3, 3), np.uint8)
    return cast(NDArray[np.uint8], cv2.dilate(edges, kernel, iterations=1))


def _find_best_contour(contours: Any, image_area: int, id_card_aspect_ratio: float) -> Any:
    min_area = image_area * 0.05
    max_area = image_area * 0.95
    aspect_ratio_min = id_card_aspect_ratio * 0.7
    aspect_ratio_max = id_card_aspect_ratio * 1.3

    best_contour = None
    best_area: float = 0

    for contour in contours:
        area = cv2.contourArea(contour)
        if area < min_area or area > max_area:
            continue
        epsilon = 0.02 * cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, epsilon, True)
        if len(approx) != 4 or not cv2.isContourConvex(approx):
            continue
        rect = cv2.minAreaRect(approx)
        rect_width, rect_height = rect[1]
        if rect_width == 0 or rect_height == 0:
            continue
        if rect_width < rect_height:
            rect_width, rect_height = rect_height, rect_width
        aspect_ratio = rect_width / rect_height
        if aspect_ratio_min <= aspect_ratio <= aspect_ratio_max and area > best_area:
            best_area = area
            best_contour = approx

    return best_contour
