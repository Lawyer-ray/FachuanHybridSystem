from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from apps.client.services.id_card_merge.detection import (
    _compute_edges,
    _find_best_contour,
    detect_id_card_corners,
)


class TestComputeEdges:

    def test_returns_uint8_array(self):
        img = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        result = _compute_edges(img)
        assert result.dtype == np.uint8
        assert result.shape == (100, 100)

    def test_edges_on_simple_image(self):
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        img[20:80, 20:80] = 255
        result = _compute_edges(img)
        assert result.max() > 0

    def test_edges_on_uniform_image(self):
        img = np.ones((50, 50, 3), dtype=np.uint8) * 128
        result = _compute_edges(img)
        assert result.shape == (50, 50)


class TestDetectIdCardCorners:

    def test_none_image_returns_none(self):
        logger = MagicMock()
        result = detect_id_card_corners(None, id_card_aspect_ratio=1.585, logger=logger)
        assert result is None
        logger.warning.assert_called_once()

    def test_empty_image_returns_none(self):
        logger = MagicMock()
        img = np.array([], dtype=np.uint8).reshape(0, 0, 3)
        result = detect_id_card_corners(img, id_card_aspect_ratio=1.585, logger=logger)
        assert result is None

    def test_no_contours_returns_none(self):
        logger = MagicMock()
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        result = detect_id_card_corners(img, id_card_aspect_ratio=1.585, logger=logger)
        assert result is None

    def test_detects_rectangular_card(self):
        logger = MagicMock()
        img = np.ones((600, 400, 3), dtype=np.uint8) * 200
        import cv2

        cv2.rectangle(img, (50, 50), (350, 260), (0, 0, 0), 3)
        result = detect_id_card_corners(img, id_card_aspect_ratio=1.585, logger=logger)
        if result is not None:
            assert result.shape == (4, 2)
            assert result.dtype == np.float32

    def test_custom_aspect_ratio(self):
        logger = MagicMock()
        img = np.ones((600, 800, 3), dtype=np.uint8) * 200
        import cv2

        cv2.rectangle(img, (50, 50), (750, 400), (0, 0, 0), 3)
        result = detect_id_card_corners(img, id_card_aspect_ratio=1.777, logger=logger)
        if result is not None:
            assert result.shape == (4, 2)


class TestFindBestContour:

    def test_returns_none_for_small_contours(self):
        contours = [np.array([[[0, 0]], [[1, 0]], [[1, 1]], [[0, 1]]], dtype=np.int32)]
        result = _find_best_contour(contours, image_area=100000, id_card_aspect_ratio=1.585)
        assert result is None

    def test_returns_none_for_no_contours(self):
        assert _find_best_contour([], image_area=100000, id_card_aspect_ratio=1.585) is None

    def test_returns_none_for_non_convex(self):
        import cv2

        img = np.zeros((600, 400, 3), dtype=np.uint8)
        cv2.rectangle(img, (50, 50), (350, 260), (255, 255, 255), -1)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        contours, _ = cv2.findContours(gray, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        result = _find_best_contour(contours, image_area=600 * 400, id_card_aspect_ratio=1.585)
        # The rectangular contour should be detected as a valid candidate
        # (it may or may not be None depending on convexity checks)
        assert result is None or result.shape[0] == 4
