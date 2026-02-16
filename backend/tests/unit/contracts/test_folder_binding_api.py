"""
合同文件夹绑定 API 单元测试

测试 API 端点：
- POST /contracts/{contract_id}/folder-binding - 创建/更新绑定
- GET /contracts/{contract_id}/folder-binding - 获取绑定信息
- DELETE /contracts/{contract_id}/folder-binding - 删除绑定

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5
"""

from unittest.mock import Mock, patch

import pytest
from django.http import Http404
from django.test import TestCase

from apps.contracts.api.folder_binding_api import create_folder_binding, delete_folder_binding, get_folder_binding
from apps.contracts.models import ContractFolderBinding
from apps.contracts.schemas import FolderBindingCreateSchema, FolderBindingResponseSchema
from apps.core.exceptions import NotFoundError, ValidationException


class TestFolderBindingAPI(TestCase):
    """文件夹绑定 API 测试"""

    def setUp(self):
        """测试设置"""
        self.contract_id = 1
        self.folder_path = "/Users/test/Documents/案件文件夹"
        self.mock_request = Mock()

    @patch("apps.contracts.api.folder_binding_api._get_folder_binding_service")
    def test_create_folder_binding_new(self, mock_get_service):
        """测试创建新的文件夹绑定"""
        # 准备测试数据
        mock_service = Mock()
        mock_get_service.return_value = mock_service

        # 模拟不存在绑定
        mock_service.get_binding.return_value = None

        # 模拟创建绑定
        mock_binding = Mock()
        mock_binding.id = 1
        mock_binding.contract_id = self.contract_id
        mock_binding.folder_path = self.folder_path
        mock_binding.created_at = "2024-01-01T00:00:00Z"
        mock_binding.updated_at = "2024-01-01T00:00:00Z"
        mock_service.create_binding.return_value = mock_binding

        # 模拟路径格式化
        mock_service.format_path_for_display.return_value = "...案件文件夹"

        # 模拟子目录创建成功
        mock_service.ensure_subdirectories.return_value = True

        # 创建请求数据
        data = FolderBindingCreateSchema(folder_path=self.folder_path)

        # 调用 API
        result = create_folder_binding(self.mock_request, self.contract_id, data)

        # 验证调用
        mock_service.get_binding.assert_called_once_with(self.contract_id)
        mock_service.create_binding.assert_called_once_with(self.contract_id, self.folder_path)
        mock_service.format_path_for_display.assert_called_once_with(self.folder_path)
        mock_service.ensure_subdirectories.assert_called_once_with(self.folder_path)

        # 验证结果
        self.assertIsInstance(result, FolderBindingResponseSchema)
        self.assertEqual(result.contract_id, self.contract_id)
        self.assertEqual(result.folder_path, self.folder_path)
        self.assertTrue(result.is_accessible)

    @patch("apps.contracts.api.folder_binding_api._get_folder_binding_service")
    def test_create_folder_binding_update_existing(self, mock_get_service):
        """测试更新现有的文件夹绑定"""
        # 准备测试数据
        mock_service = Mock()
        mock_get_service.return_value = mock_service

        # 模拟存在绑定
        existing_binding = Mock()
        mock_service.get_binding.return_value = existing_binding

        # 模拟更新绑定
        mock_binding = Mock()
        mock_binding.id = 1
        mock_binding.contract_id = self.contract_id
        mock_binding.folder_path = self.folder_path
        mock_binding.created_at = "2024-01-01T00:00:00Z"
        mock_binding.updated_at = "2024-01-01T01:00:00Z"
        mock_service.update_binding.return_value = mock_binding

        # 模拟路径格式化
        mock_service.format_path_for_display.return_value = "...案件文件夹"

        # 模拟子目录创建成功
        mock_service.ensure_subdirectories.return_value = True

        # 创建请求数据
        data = FolderBindingCreateSchema(folder_path=self.folder_path)

        # 调用 API
        result = create_folder_binding(self.mock_request, self.contract_id, data)

        # 验证调用
        mock_service.get_binding.assert_called_once_with(self.contract_id)
        mock_service.update_binding.assert_called_once_with(self.contract_id, self.folder_path)
        mock_service.create_binding.assert_not_called()

        # 验证结果
        self.assertIsInstance(result, FolderBindingResponseSchema)
        self.assertEqual(result.contract_id, self.contract_id)
        self.assertEqual(result.folder_path, self.folder_path)
        self.assertTrue(result.is_accessible)

    @patch("apps.contracts.api.folder_binding_api._get_folder_binding_service")
    def test_create_folder_binding_not_accessible(self, mock_get_service):
        """测试创建绑定但文件夹不可访问"""
        # 准备测试数据
        mock_service = Mock()
        mock_get_service.return_value = mock_service

        # 模拟不存在绑定
        mock_service.get_binding.return_value = None

        # 模拟创建绑定
        mock_binding = Mock()
        mock_binding.id = 1
        mock_binding.contract_id = self.contract_id
        mock_binding.folder_path = self.folder_path
        mock_binding.created_at = "2024-01-01T00:00:00Z"
        mock_binding.updated_at = "2024-01-01T00:00:00Z"
        mock_service.create_binding.return_value = mock_binding

        # 模拟路径格式化
        mock_service.format_path_for_display.return_value = "...案件文件夹"

        # 模拟子目录创建失败
        mock_service.ensure_subdirectories.side_effect = Exception("无法访问文件夹")

        # 创建请求数据
        data = FolderBindingCreateSchema(folder_path=self.folder_path)

        # 调用 API
        result = create_folder_binding(self.mock_request, self.contract_id, data)

        # 验证结果
        self.assertIsInstance(result, FolderBindingResponseSchema)
        self.assertFalse(result.is_accessible)

    @patch("apps.contracts.api.folder_binding_api._get_folder_binding_service")
    def test_create_folder_binding_contract_not_found(self, mock_get_service):
        """测试创建绑定时合同不存在"""
        # 准备测试数据
        mock_service = Mock()
        mock_get_service.return_value = mock_service

        # 模拟合同不存在
        mock_service.get_binding.side_effect = NotFoundError("合同不存在")

        # 创建请求数据
        data = FolderBindingCreateSchema(folder_path=self.folder_path)

        # 调用 API 并验证异常
        with self.assertRaises(Http404):
            create_folder_binding(self.mock_request, self.contract_id, data)

    @patch("apps.contracts.api.folder_binding_api._get_folder_binding_service")
    def test_create_folder_binding_validation_error(self, mock_get_service):
        """测试创建绑定时路径验证失败"""
        # 准备测试数据
        mock_service = Mock()
        mock_get_service.return_value = mock_service

        # 模拟路径验证失败
        mock_service.get_binding.side_effect = ValidationException("路径格式无效")

        # 创建请求数据
        data = FolderBindingCreateSchema(folder_path="invalid_path")

        # 调用 API 并验证异常
        with self.assertRaises(ValidationException):
            create_folder_binding(self.mock_request, self.contract_id, data)

    @patch("apps.contracts.api.folder_binding_api._get_folder_binding_service")
    def test_get_folder_binding_exists(self, mock_get_service):
        """测试获取存在的文件夹绑定"""
        # 准备测试数据
        mock_service = Mock()
        mock_get_service.return_value = mock_service

        # 模拟存在绑定
        mock_binding = Mock()
        mock_binding.id = 1
        mock_binding.contract_id = self.contract_id
        mock_binding.folder_path = self.folder_path
        mock_binding.created_at = "2024-01-01T00:00:00Z"
        mock_binding.updated_at = "2024-01-01T00:00:00Z"
        mock_service.get_binding.return_value = mock_binding

        # 模拟路径格式化
        mock_service.format_path_for_display.return_value = "...案件文件夹"

        # 模拟子目录检查成功
        mock_service.ensure_subdirectories.return_value = True

        # 调用 API
        result = get_folder_binding(self.mock_request, self.contract_id)

        # 验证调用
        mock_service.get_binding.assert_called_once_with(self.contract_id)
        mock_service.format_path_for_display.assert_called_once_with(self.folder_path)
        mock_service.ensure_subdirectories.assert_called_once_with(self.folder_path)

        # 验证结果
        self.assertIsInstance(result, FolderBindingResponseSchema)
        self.assertEqual(result.contract_id, self.contract_id)
        self.assertEqual(result.folder_path, self.folder_path)
        self.assertTrue(result.is_accessible)

    @patch("apps.contracts.api.folder_binding_api._get_folder_binding_service")
    def test_get_folder_binding_not_exists(self, mock_get_service):
        """测试获取不存在的文件夹绑定"""
        # 准备测试数据
        mock_service = Mock()
        mock_get_service.return_value = mock_service

        # 模拟不存在绑定
        mock_service.get_binding.return_value = None

        # 调用 API
        result = get_folder_binding(self.mock_request, self.contract_id)

        # 验证调用
        mock_service.get_binding.assert_called_once_with(self.contract_id)

        # 验证结果
        self.assertIsNone(result)

    @patch("apps.contracts.api.folder_binding_api._get_folder_binding_service")
    def test_get_folder_binding_not_accessible(self, mock_get_service):
        """测试获取绑定但文件夹不可访问"""
        # 准备测试数据
        mock_service = Mock()
        mock_get_service.return_value = mock_service

        # 模拟存在绑定
        mock_binding = Mock()
        mock_binding.id = 1
        mock_binding.contract_id = self.contract_id
        mock_binding.folder_path = self.folder_path
        mock_binding.created_at = "2024-01-01T00:00:00Z"
        mock_binding.updated_at = "2024-01-01T00:00:00Z"
        mock_service.get_binding.return_value = mock_binding

        # 模拟路径格式化
        mock_service.format_path_for_display.return_value = "...案件文件夹"

        # 模拟子目录检查失败
        mock_service.ensure_subdirectories.side_effect = Exception("无法访问文件夹")

        # 调用 API
        result = get_folder_binding(self.mock_request, self.contract_id)

        # 验证结果
        self.assertIsInstance(result, FolderBindingResponseSchema)
        self.assertFalse(result.is_accessible)

    @patch("apps.contracts.api.folder_binding_api._get_folder_binding_service")
    def test_delete_folder_binding_success(self, mock_get_service):
        """测试成功删除文件夹绑定"""
        # 准备测试数据
        mock_service = Mock()
        mock_get_service.return_value = mock_service

        # 模拟删除成功
        mock_service.delete_binding.return_value = True

        # 调用 API
        result = delete_folder_binding(self.mock_request, self.contract_id)

        # 验证调用
        mock_service.delete_binding.assert_called_once_with(self.contract_id)

        # 验证结果
        self.assertEqual(result["success"], True)
        self.assertEqual(result["message"], "绑定已删除")

    @patch("apps.contracts.api.folder_binding_api._get_folder_binding_service")
    def test_delete_folder_binding_not_exists(self, mock_get_service):
        """测试删除不存在的文件夹绑定"""
        # 准备测试数据
        mock_service = Mock()
        mock_get_service.return_value = mock_service

        # 模拟删除失败（绑定不存在）
        mock_service.delete_binding.return_value = False

        # 调用 API
        result = delete_folder_binding(self.mock_request, self.contract_id)

        # 验证调用
        mock_service.delete_binding.assert_called_once_with(self.contract_id)

        # 验证结果
        self.assertEqual(result["success"], False)
        self.assertEqual(result["message"], "绑定不存在")


class TestFolderBindingSchemas(TestCase):
    """文件夹绑定 Schema 测试"""

    def test_folder_binding_create_schema_valid(self):
        """测试有效的创建绑定 Schema"""
        data = {"folder_path": "/Users/test/Documents/案件文件夹"}
        schema = FolderBindingCreateSchema(**data)
        self.assertEqual(schema.folder_path, "/Users/test/Documents/案件文件夹")

    def test_folder_binding_create_schema_empty_path(self):
        """测试空路径的创建绑定 Schema"""
        with self.assertRaises(ValueError) as context:
            FolderBindingCreateSchema(folder_path="")
        self.assertIn("文件夹路径不能为空", str(context.exception))

    def test_folder_binding_create_schema_whitespace_path(self):
        """测试空白字符路径的创建绑定 Schema"""
        with self.assertRaises(ValueError) as context:
            FolderBindingCreateSchema(folder_path="   ")
        self.assertIn("文件夹路径不能为空", str(context.exception))

    def test_folder_binding_create_schema_strips_whitespace(self):
        """测试创建绑定 Schema 自动去除空白字符"""
        data = {"folder_path": "  /Users/test/Documents/案件文件夹  "}
        schema = FolderBindingCreateSchema(**data)
        self.assertEqual(schema.folder_path, "/Users/test/Documents/案件文件夹")

    def test_folder_binding_response_schema_from_binding(self):
        """测试从绑定对象创建响应 Schema"""
        # 创建模拟绑定对象
        mock_binding = Mock()
        mock_binding.id = 1
        mock_binding.contract_id = 123
        mock_binding.folder_path = "/Users/test/Documents/案件文件夹"
        mock_binding.created_at = "2024-01-01T00:00:00Z"
        mock_binding.updated_at = "2024-01-01T01:00:00Z"

        # 创建响应 Schema
        schema = FolderBindingResponseSchema.from_binding(
            mock_binding, is_accessible=True, display_path="...案件文件夹"
        )

        # 验证结果
        self.assertEqual(schema.id, 1)
        self.assertEqual(schema.contract_id, 123)
        self.assertEqual(schema.folder_path, "/Users/test/Documents/案件文件夹")
        self.assertEqual(schema.folder_path_display, "...案件文件夹")
        self.assertTrue(schema.is_accessible)

    def test_folder_binding_response_schema_from_binding_defaults(self):
        """测试从绑定对象创建响应 Schema 使用默认值"""
        # 创建模拟绑定对象
        mock_binding = Mock()
        mock_binding.id = 1
        mock_binding.contract_id = 123
        mock_binding.folder_path = "/Users/test/Documents/案件文件夹"
        mock_binding.created_at = "2024-01-01T00:00:00Z"
        mock_binding.updated_at = "2024-01-01T01:00:00Z"

        # 创建响应 Schema（使用默认值）
        schema = FolderBindingResponseSchema.from_binding(mock_binding)

        # 验证结果
        self.assertEqual(schema.folder_path_display, "/Users/test/Documents/案件文件夹")
        self.assertTrue(schema.is_accessible)
