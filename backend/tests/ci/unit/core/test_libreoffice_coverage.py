"""测试 LibreOffice 查找

覆盖: apps/core/services/libreoffice.py
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from apps.core.services.libreoffice import find_libreoffice


class TestFindLibreOffice:
    """测试 LibreOffice 路径查找"""

    @patch("apps.core.services.libreoffice.shutil.which")
    def test_found_in_path_soffice(self, mock_which: MagicMock) -> None:
        mock_which.side_effect = lambda name: "/usr/bin/soffice" if name == "soffice" else None
        result = find_libreoffice()
        assert result == "/usr/bin/soffice"

    @patch("apps.core.services.libreoffice.shutil.which")
    def test_found_in_path_libreoffice(self, mock_which: MagicMock) -> None:
        mock_which.side_effect = lambda name: "/usr/bin/libreoffice" if name == "libreoffice" else None
        result = find_libreoffice()
        assert result == "/usr/bin/libreoffice"

    @patch("apps.core.services.libreoffice.shutil.which")
    @patch("apps.core.services.libreoffice.platform.system")
    def test_not_in_path_on_darwin(self, mock_system: MagicMock, mock_which: MagicMock) -> None:
        mock_which.return_value = None
        mock_system.return_value = "Darwin"
        with patch.object(Path, "is_file", return_value=False):
            result = find_libreoffice()
            assert result is None

    @patch("apps.core.services.libreoffice.shutil.which")
    @patch("apps.core.services.libreoffice.platform.system")
    def test_not_in_path_on_linux(self, mock_system: MagicMock, mock_which: MagicMock) -> None:
        mock_which.return_value = None
        mock_system.return_value = "Linux"
        with patch.object(Path, "is_file", return_value=False):
            result = find_libreoffice()
            assert result is None

    @patch("apps.core.services.libreoffice.shutil.which")
    @patch("apps.core.services.libreoffice.platform.system")
    def test_darwin_candidate_found(self, mock_system: MagicMock, mock_which: MagicMock) -> None:
        mock_which.return_value = None
        mock_system.return_value = "Darwin"
        with patch.object(Path, "is_file", return_value=True):
            result = find_libreoffice()
            assert result is not None
            assert "soffice" in result

    @patch("apps.core.services.libreoffice.shutil.which")
    @patch("apps.core.services.libreoffice.platform.system")
    def test_linux_candidate_found(self, mock_system: MagicMock, mock_which: MagicMock) -> None:
        mock_which.return_value = None
        mock_system.return_value = "Linux"
        with patch.object(Path, "is_file", return_value=True):
            result = find_libreoffice()
            assert result is not None
            assert "libreoffice" in result or "soffice" in result

    @patch("apps.core.services.libreoffice.shutil.which")
    @patch("apps.core.services.libreoffice.platform.system")
    def test_windows_no_candidates(self, mock_system: MagicMock, mock_which: MagicMock) -> None:
        """Windows 没有平台特定候选路径"""
        mock_which.return_value = None
        mock_system.return_value = "Windows"
        result = find_libreoffice()
        assert result is None
