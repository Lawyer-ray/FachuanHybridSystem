"""
合同文件夹绑定服务单元测试
"""

from unittest.mock import mock_open, patch

import pytest

from apps.contracts.models import Contract, ContractFolderBinding
from apps.contracts.services.folder_binding_service import FolderBindingService
from apps.core.exceptions import NotFoundError, ValidationException
from apps.core.path import Path


class TestFolderBindingService:
    """文件夹绑定服务测试"""

    def setup_method(self):
        """测试前准备"""
        self.service = FolderBindingService()

    def test_validate_folder_path_empty(self):
        """测试空路径验证"""
        is_valid, error = self.service.validate_folder_path("")
        assert not is_valid
        assert error == "请输入文件夹路径"

    def test_validate_folder_path_macos_linux(self):
        """测试 macOS/Linux 路径验证"""
        is_valid, error = self.service.validate_folder_path("/Users/test/Documents")
        assert is_valid
        assert error is None

    def test_validate_folder_path_windows(self):
        """测试 Windows 路径验证"""
        is_valid, error = self.service.validate_folder_path("C:\\Users\\test\\Documents")
        assert is_valid
        assert error is None

    def test_validate_folder_path_unc(self):
        """测试 UNC 路径验证"""
        is_valid, error = self.service.validate_folder_path("\\\\server\\share\\folder")
        assert is_valid
        assert error is None

    def test_validate_folder_path_smb(self):
        """测试 SMB 路径验证"""
        is_valid, error = self.service.validate_folder_path("smb://server/share/folder")
        assert is_valid
        assert error is None

    def test_validate_folder_path_invalid(self):
        """测试无效路径"""
        is_valid, error = self.service.validate_folder_path("invalid_path")
        assert not is_valid
        assert "请输入有效的文件夹路径" in error

    @pytest.mark.django_db
    def test_create_binding_success(self):
        """测试创建绑定成功"""
        # 创建测试合同
        contract = Contract.objects.create(name="测试合同", case_type="CIVIL")

        # 创建绑定
        binding = self.service.create_binding(contract.id, "/test/path")

        assert binding.contract_id == contract.id
        assert binding.folder_path == "/test/path"

    @pytest.mark.django_db
    def test_create_binding_contract_not_found(self):
        """测试合同不存在"""
        with pytest.raises(NotFoundError):
            self.service.create_binding(999, "/test/path")

    @pytest.mark.django_db
    def test_create_binding_invalid_path(self):
        """测试无效路径"""
        contract = Contract.objects.create(name="测试合同", case_type="CIVIL")

        with pytest.raises(ValidationException):
            self.service.create_binding(contract.id, "")

    @pytest.mark.django_db
    def test_get_binding_exists(self):
        """测试获取存在的绑定"""
        contract = Contract.objects.create(name="测试合同", case_type="CIVIL")

        # 创建绑定
        created_binding = self.service.create_binding(contract.id, "/test/path")

        # 获取绑定
        binding = self.service.get_binding(contract.id)

        assert binding is not None
        assert binding.id == created_binding.id

    @pytest.mark.django_db
    def test_get_binding_not_exists(self):
        """测试获取不存在的绑定"""
        contract = Contract.objects.create(name="测试合同", case_type="CIVIL")

        binding = self.service.get_binding(contract.id)
        assert binding is None

    @pytest.mark.django_db
    def test_delete_binding_success(self):
        """测试删除绑定成功"""
        contract = Contract.objects.create(name="测试合同", case_type="CIVIL")

        # 创建绑定
        self.service.create_binding(contract.id, "/test/path")

        # 删除绑定
        result = self.service.delete_binding(contract.id)
        assert result is True

        # 验证已删除
        binding = self.service.get_binding(contract.id)
        assert binding is None

    @pytest.mark.django_db
    def test_delete_binding_not_exists(self):
        """测试删除不存在的绑定"""
        contract = Contract.objects.create(name="测试合同", case_type="CIVIL")

        result = self.service.delete_binding(contract.id)
        assert result is False

    def test_format_path_for_display_short(self):
        """测试短路径格式化"""
        path = "/short/path"
        formatted = self.service.format_path_for_display(path, 50)
        assert formatted == path

    def test_format_path_for_display_long(self):
        """测试长路径格式化"""
        path = "/very/long/path/that/exceeds/the/maximum/length/limit/for/display"
        formatted = self.service.format_path_for_display(path, 30)
        assert "..." in formatted
        assert len(formatted) <= 30

    def test_format_path_for_display_empty(self):
        """测试空路径格式化"""
        formatted = self.service.format_path_for_display("", 50)
        assert formatted == ""

    @patch("pathlib.Path.mkdir")
    def test_ensure_subdirectories_success(self, mock_mkdir):
        """测试子目录创建成功"""
        result = self.service.ensure_subdirectories("/test/path")
        assert result is True
        assert mock_mkdir.called

    @patch("pathlib.Path.mkdir")
    def test_ensure_subdirectories_failure(self, mock_mkdir):
        """测试子目录创建失败"""
        mock_mkdir.side_effect = OSError("Permission denied")

        result = self.service.ensure_subdirectories("/test/path")
        assert result is False

    @pytest.mark.django_db
    @patch("builtins.open", new_callable=mock_open)
    @patch("pathlib.Path.mkdir")
    def test_save_file_to_bound_folder_success(self, mock_mkdir, mock_file):
        """测试文件保存成功"""
        contract = Contract.objects.create(name="测试合同", case_type="CIVIL")

        # 创建绑定
        self.service.create_binding(contract.id, "/test/path")

        # 保存文件
        result = self.service.save_file_to_bound_folder(contract.id, b"test content", "test.pdf")

        assert result is not None
        assert "test.pdf" in result
        mock_file.assert_called_once()

    @pytest.mark.django_db
    def test_save_file_to_bound_folder_no_binding(self):
        """测试保存文件但无绑定"""
        contract = Contract.objects.create(name="测试合同", case_type="CIVIL")

        result = self.service.save_file_to_bound_folder(contract.id, b"test content", "test.pdf")

        assert result is None

    @pytest.mark.django_db
    @patch("zipfile.ZipFile")
    @patch("pathlib.Path.mkdir")
    def test_extract_zip_to_bound_folder_success(self, mock_mkdir, mock_zipfile):
        """测试ZIP解压成功"""
        contract = Contract.objects.create(name="测试合同", case_type="CIVIL")

        # 创建绑定
        self.service.create_binding(contract.id, "/test/path")

        # 模拟ZIP文件
        mock_zip_instance = mock_zipfile.return_value.__enter__.return_value

        # 解压ZIP
        result = self.service.extract_zip_to_bound_folder(contract.id, b"fake zip content")

        assert result is not None
        assert result == "/test/path"
        mock_zip_instance.extractall.assert_called_once()

    @pytest.mark.django_db
    def test_extract_zip_to_bound_folder_no_binding(self):
        """测试解压ZIP但无绑定"""
        contract = Contract.objects.create(name="测试合同", case_type="CIVIL")

        result = self.service.extract_zip_to_bound_folder(contract.id, b"fake zip content")

        assert result is None
