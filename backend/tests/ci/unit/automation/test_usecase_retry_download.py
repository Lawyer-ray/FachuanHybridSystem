"""Tests for apps/automation/usecases/court_sms/retry_download.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestRetryDownloadUsecase:
    """RetryDownloadUsecase 单元测试。"""

    def test_execute_delegates_to_retry_processing(self) -> None:
        """execute 调用 court_sms_service.retry_processing。"""
        from apps.automation.usecases.court_sms.retry_download import RetryDownloadUsecase

        mock_service = MagicMock()
        mock_service.retry_processing.return_value = {"retried": True}
        uc = RetryDownloadUsecase(court_sms_service=mock_service)

        result = uc.execute(sms_id=55)
        mock_service.retry_processing.assert_called_once_with(55)
        assert result == {"retried": True}

    def test_frozen_dataclass(self) -> None:
        """RetryDownloadUsecase 是 frozen dataclass。"""
        from apps.automation.usecases.court_sms.retry_download import RetryDownloadUsecase

        uc = RetryDownloadUsecase(court_sms_service=MagicMock())
        with pytest.raises(AttributeError):
            uc.court_sms_service = MagicMock()  # type: ignore[misc]

    def test_propagates_service_exception(self) -> None:
        """service.retry_processing 抛异常时向外传播。"""
        from apps.automation.usecases.court_sms.retry_download import RetryDownloadUsecase

        mock_service = MagicMock()
        mock_service.retry_processing.side_effect = ValueError("download failed")
        uc = RetryDownloadUsecase(court_sms_service=mock_service)

        with pytest.raises(ValueError, match="download failed"):
            uc.execute(sms_id=1)

    def test_different_sms_ids(self) -> None:
        """不同 sms_id 正确传递。"""
        from apps.automation.usecases.court_sms.retry_download import RetryDownloadUsecase

        mock_service = MagicMock()
        uc = RetryDownloadUsecase(court_sms_service=mock_service)

        for sms_id in [1, 100, 999]:
            uc.execute(sms_id=sms_id)
            mock_service.retry_processing.assert_called_with(sms_id)
