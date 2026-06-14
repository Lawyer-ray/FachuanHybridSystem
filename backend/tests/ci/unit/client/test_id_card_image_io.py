from __future__ import annotations

import numpy as np
from unittest.mock import MagicMock

import pytest

from apps.client.services.id_card_merge.image_io import read_uploaded_image


class TestReadUploadedImage:

    def test_reads_valid_image(self):
        logger = MagicMock()
        import cv2

        img = np.zeros((50, 50, 3), dtype=np.uint8)
        img[10:40, 10:40] = 255
        _, buf = cv2.imencode(".png", img)

        mock_file = MagicMock()
        mock_file.name = "test.png"
        mock_file.read.return_value = buf.tobytes()

        result = read_uploaded_image(mock_file, logger=logger)
        assert result is not None
        assert result.shape == (50, 50, 3)

    def test_invalid_bytes_returns_none(self):
        logger = MagicMock()
        mock_file = MagicMock()
        mock_file.name = "bad.png"
        mock_file.read.return_value = b"not an image"

        result = read_uploaded_image(mock_file, logger=logger)
        assert result is None

    def test_seek_called(self):
        logger = MagicMock()
        mock_file = MagicMock()
        mock_file.name = "test.png"
        mock_file.read.return_value = b"\x00" * 10

        read_uploaded_image(mock_file, logger=logger)
        assert mock_file.seek.call_count >= 2

    def test_exception_returns_none(self):
        logger = MagicMock()
        mock_file = MagicMock()
        mock_file.seek.side_effect = RuntimeError("io error")

        result = read_uploaded_image(mock_file, logger=logger)
        assert result is None
        logger.warning.assert_called_once()
