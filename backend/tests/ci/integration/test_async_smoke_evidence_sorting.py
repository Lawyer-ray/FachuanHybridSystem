"""Smoke tests for async evidence sorting classify endpoint."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.django_db
class TestEvidenceSortingSmoke:
    def test_classify_endpoint_returns_response(self, authenticated_client):
        """The classify endpoint should return a valid response structure."""
        mock_classify_result = MagicMock()
        mock_img = MagicMock()
        mock_img.filename = "stmt.jpg"
        mock_img.category = "statement"
        mock_img.ocr_text = "对账单 ¥50000"
        mock_img.date = "20260101"
        mock_img.amount = "50000"
        mock_img.signed = True
        mock_img.confidence = 0.9
        mock_img.rotation = 0
        mock_classify_result.images = [mock_img]
        mock_classify_result.errors = []

        mock_svc = MagicMock()
        mock_svc.classify_images.return_value = mock_classify_result

        with patch("apps.evidence_sorting.api.evidence_sorting_api.ClassifierService", return_value=mock_svc):
            resp = authenticated_client.post(
                "/api/v1/evidence-sorting/classify",
                data=json.dumps({"images": [{"filename": "stmt.jpg", "data": "base64data"}]}),
                content_type="application/json",
            )

        assert resp.status_code in (200, 201), f"Classify failed: {resp.content}"

    def test_classify_empty_images(self, authenticated_client):
        """Classifying with no images should return an error or empty result."""
        resp = authenticated_client.post(
            "/api/v1/evidence-sorting/classify",
            data=json.dumps({"images": []}),
            content_type="application/json",
        )
        # Should return 200 with success=False or 400
        assert resp.status_code in (200, 400, 422)
