"""透视变换。"""

import logging
from typing import Any, cast

import cv2
import numpy as np
from numpy.typing import NDArray

logger = logging.getLogger(__name__)


def perspective_transform(
    image: NDArray[np.uint8],
    corners: NDArray[np.float32],
    *,
    id_card_aspect_ratio: float,
    min_output_width: int,
    logger: Any,
) -> NDArray[np.uint8]:
    src_pts = corners.astype(np.float32)

    width_top = np.linalg.norm(corners[1] - corners[0])
    width_bottom = np.linalg.norm(corners[2] - corners[3])
    height_left = np.linalg.norm(corners[3] - corners[0])
    height_right = np.linalg.norm(corners[2] - corners[1])

    avg_width = (width_top + width_bottom) / 2
    avg_height = (height_left + height_right) / 2

    if avg_width / avg_height > id_card_aspect_ratio:
        output_width = int(avg_width)
        output_height = int(output_width / id_card_aspect_ratio)
    else:
        output_height = int(avg_height)
        output_width = int(output_height * id_card_aspect_ratio)

    output_width = max(output_width, min_output_width)
    output_height = max(output_height, int(min_output_width / id_card_aspect_ratio))

    dst_pts = np.array(
        [
            [0, 0],
            [output_width - 1, 0],
            [output_width - 1, output_height - 1],
            [0, output_height - 1],
        ],
        dtype=np.float32,
    )

    matrix = cv2.getPerspectiveTransform(src_pts, dst_pts)
    warped = cv2.warpPerspective(
        image,
        matrix,
        (output_width, output_height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )

    logger.info(
        "透视变换完成",
        extra={"output_size": f"{output_width}x{output_height}"},
    )
    return cast(NDArray[np.uint8], warped)
