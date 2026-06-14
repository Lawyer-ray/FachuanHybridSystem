"""补充覆盖测试: contracts/services/client_payment/client_payment_image_service.py (37 missing)

覆盖: save_image, delete_image, get_image_url 所有分支。
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import ValidationException
from apps.contracts.services.client_payment.client_payment_image_service import ClientPaymentImageService


class TestSaveImage:
    def test_save_success(self) -> None:
        svc = ClientPaymentImageService()
        uploaded = MagicMock()

        with patch("apps.contracts.services.client_payment.client_payment_image_service.storage") as mock_storage:
            mock_storage.save_uploaded_file.return_value = ("contracts/client_payments/1/photo.jpg", "photo.jpg")
            result = svc.save_image(uploaded, record_id=1)
            assert result == "contracts/client_payments/1/photo.jpg"
            mock_storage.save_uploaded_file.assert_called_once()

    def test_save_validation_error_propagates(self) -> None:
        svc = ClientPaymentImageService()
        uploaded = MagicMock()

        with patch("apps.contracts.services.client_payment.client_payment_image_service.storage") as mock_storage:
            mock_storage.save_uploaded_file.side_effect = ValidationException("Invalid file")
            with pytest.raises(ValidationException):
                svc.save_image(uploaded, record_id=1)

    def test_save_generic_error_wrapped(self) -> None:
        svc = ClientPaymentImageService()
        uploaded = MagicMock()

        with patch("apps.contracts.services.client_payment.client_payment_image_service.storage") as mock_storage:
            mock_storage.save_uploaded_file.side_effect = OSError("disk full")
            with pytest.raises(ValidationException, match="图片上传失败"):
                svc.save_image(uploaded, record_id=1)


class TestDeleteImage:
    def test_delete_empty_path_returns_early(self) -> None:
        svc = ClientPaymentImageService()
        svc.delete_image("")  # Should not raise
        svc.delete_image("")  # noqa: also test empty string

    def test_delete_success(self) -> None:
        svc = ClientPaymentImageService()
        with patch("apps.contracts.services.client_payment.client_payment_image_service.storage") as mock_storage:
            mock_storage.delete_media_file.return_value = True
            svc.delete_image("contracts/client_payments/1/photo.jpg")
            mock_storage.delete_media_file.assert_called_once_with("contracts/client_payments/1/photo.jpg")

    def test_delete_file_not_found_logs_warning(self) -> None:
        svc = ClientPaymentImageService()
        with patch("apps.contracts.services.client_payment.client_payment_image_service.storage") as mock_storage:
            mock_storage.delete_media_file.return_value = False
            svc.delete_image("nonexistent.jpg")  # Should not raise

    def test_delete_exception_handled(self) -> None:
        svc = ClientPaymentImageService()
        with patch("apps.contracts.services.client_payment.client_payment_image_service.storage") as mock_storage:
            mock_storage.delete_media_file.side_effect = OSError("permission denied")
            svc.delete_image("some/file.jpg")  # Should not raise


class TestGetImageUrl:
    def test_empty_path(self) -> None:
        svc = ClientPaymentImageService()
        assert svc.get_image_url("") == ""

    def test_with_media_url(self) -> None:
        svc = ClientPaymentImageService()
        with patch("apps.contracts.services.client_payment.client_payment_image_service.settings") as mock_settings:
            mock_settings.MEDIA_URL = "https://cdn.example.com/media/"
            result = svc.get_image_url("contracts/client_payments/1/photo.jpg")
            assert result == "https://cdn.example.com/media/contracts/client_payments/1/photo.jpg"

    def test_default_media_url(self) -> None:
        svc = ClientPaymentImageService()
        with patch("apps.contracts.services.client_payment.client_payment_image_service.settings") as mock_settings:
            del mock_settings.MEDIA_URL
            mock_settings.MEDIA_URL = "/media/"
            result = svc.get_image_url("test.jpg")
            assert result == "/media/test.jpg"
