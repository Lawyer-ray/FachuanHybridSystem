from __future__ import annotations

import logging
from unittest.mock import MagicMock

import numpy as np
import pytest

from apps.client.services.id_card_merge.transform import perspective_transform


class TestPerspectiveTransform:

    def test_basic_transform(self):
        logger = MagicMock()
        img = np.ones((300, 200, 3), dtype=np.uint8) * 128
        corners = np.array(
            [[10, 10], [190, 10], [190, 290], [10, 290]],
            dtype=np.float32,
        )
        result = perspective_transform(
            img,
            corners,
            id_card_aspect_ratio=1.585,
            min_output_width=100,
            logger=logger,
        )
        assert result.dtype == np.uint8
        assert len(result.shape) == 3
        logger.info.assert_called_once()

    def test_wider_than_tall_image(self):
        logger = MagicMock()
        img = np.ones((200, 400, 3), dtype=np.uint8) * 200
        corners = np.array(
            [[10, 10], [390, 10], [390, 190], [10, 190]],
            dtype=np.float32,
        )
        result = perspective_transform(
            img,
            corners,
            id_card_aspect_ratio=1.585,
            min_output_width=50,
            logger=logger,
        )
        assert result.shape[2] == 3

    def test_min_output_width_enforced(self):
        logger = MagicMock()
        img = np.ones((50, 50, 3), dtype=np.uint8) * 100
        corners = np.array(
            [[0, 0], [49, 0], [49, 49], [0, 49]],
            dtype=np.float32,
        )
        result = perspective_transform(
            img,
            corners,
            id_card_aspect_ratio=1.585,
            min_output_width=400,
            logger=logger,
        )
        assert result.shape[1] >= 400

    def test_taller_image_branch(self):
        logger = MagicMock()
        img = np.ones((400, 200, 3), dtype=np.uint8) * 150
        corners = np.array(
            [[10, 10], [190, 10], [190, 390], [10, 390]],
            dtype=np.float32,
        )
        result = perspective_transform(
            img,
            corners,
            id_card_aspect_ratio=1.585,
            min_output_width=100,
            logger=logger,
        )
        assert result.dtype == np.uint8
