"""
证件识别 API 单元测试

测试 API 端点：
- POST /api/v1/client/identity-doc/recognize - 识别证件信息

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5
"""

from unittest.mock import Mock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.client.api.clientidentitydoc_api import recognize_identity_doc
from apps.client.schemas import IdentityRecognizeOut
from apps.client.services.identity_extraction.data_classes import (
    ExtractionResult,
    OCRExtractionError,
    OllamaExtractionError,
)
from apps.core.exceptions import ServiceUnavailableError, ValidationException


class TestIdentityDocRecognitionAPI(TestCase):
    """证件识别 API 测试"""

    def setUp(self):
        """测试设置"""
        self.mock_request = Mock()

        # 创建测试文件
        self.test_image_content = b"fake_image_content"
        self.test_file = SimpleUploadedFile("test_id_card.jpg", self.test_image_content, content_type="image/jpeg")

        # 测试证件类型
        self.doc_type = "身份证"

    @patch("apps.client.api.clientidentitydoc_api._get_identity_extraction_service")
    def test_recognize_identity_doc_success(self, mock_get_service):
        """测试证件识别成功"""
        # 准备测试数据
        mock_service = Mock()
        mock_get_service.return_value = mock_service

        # 模拟成功的提取结果
        mock_result = ExtractionResult(
            doc_type="身份证",
            raw_text="姓名：张三\n身份证号：110101199001010001\n地址：北京市朝阳区\n有效期限：2020.01.01-2030.01.01",
            extracted_data={
                "name": "张三",
                "id_number": "110101199001010001",
                "address": "北京市朝阳区",
                "expiry_date": "2030-01-01",
                "gender": "男",
                "ethnicity": "汉",
                "birth_date": "1990-01-01",
            },
            confidence=0.95,
            extraction_method="ocr_ollama",
        )
        mock_service.extract.return_value = mock_result

        # 调用 API
        result = recognize_identity_doc(self.mock_request, file=self.test_file, doc_type=self.doc_type)

        # 验证调用
        mock_service.extract.assert_called_once_with(self.test_image_content, self.doc_type)

        # 验证结果
        self.assertIsInstance(result, IdentityRecognizeOut)
        self.assertTrue(result.success)
        self.assertEqual(result.doc_type, "身份证")
        self.assertEqual(result.extracted_data["name"], "张三")
        self.assertEqual(result.extracted_data["id_number"], "110101199001010001")
        self.assertEqual(result.confidence, 0.95)
        self.assertIsNone(result.error)

    @patch("apps.client.api.clientidentitydoc_api._get_identity_extraction_service")
    def test_recognize_identity_doc_passport_success(self, mock_get_service):
        """测试护照识别成功"""
        # 准备测试数据
        mock_service = Mock()
        mock_get_service.return_value = mock_service

        # 模拟护照提取结果
        mock_result = ExtractionResult(
            doc_type="护照",
            raw_text="姓名：ZHANG SAN\n护照号：E12345678\n国籍：CHN\n有效期至：01JAN2030",
            extracted_data={
                "name": "ZHANG SAN",
                "passport_number": "E12345678",
                "nationality": "CHN",
                "expiry_date": "2030-01-01",
                "birth_date": "1990-01-01",
            },
            confidence=0.88,
            extraction_method="ocr_ollama",
        )
        mock_service.extract.return_value = mock_result

        # 调用 API
        result = recognize_identity_doc(self.mock_request, file=self.test_file, doc_type="护照")

        # 验证结果
        self.assertIsInstance(result, IdentityRecognizeOut)
        self.assertTrue(result.success)
        self.assertEqual(result.doc_type, "护照")
        self.assertEqual(result.extracted_data["name"], "ZHANG SAN")
        self.assertEqual(result.extracted_data["passport_number"], "E12345678")
        self.assertEqual(result.confidence, 0.88)

    @patch("apps.client.api.clientidentitydoc_api._get_identity_extraction_service")
    def test_recognize_identity_doc_business_license_success(self, mock_get_service):
        """测试营业执照识别成功"""
        # 准备测试数据
        mock_service = Mock()
        mock_get_service.return_value = mock_service

        # 模拟营业执照提取结果
        mock_result = ExtractionResult(
            doc_type="营业执照",
            raw_text="企业名称：北京测试科技有限公司\n统一社会信用代码：91110000123456789X\n法定代表人：张三",
            extracted_data={
                "company_name": "北京测试科技有限公司",
                "credit_code": "91110000123456789X",
                "legal_representative": "张三",
                "address": "北京市朝阳区测试街道1号",
                "business_scope": "技术开发、技术咨询",
                "registration_date": "2020-01-01",
            },
            confidence=0.92,
            extraction_method="ocr_ollama",
        )
        mock_service.extract.return_value = mock_result

        # 调用 API
        result = recognize_identity_doc(self.mock_request, file=self.test_file, doc_type="营业执照")

        # 验证结果
        self.assertIsInstance(result, IdentityRecognizeOut)
        self.assertTrue(result.success)
        self.assertEqual(result.doc_type, "营业执照")
        self.assertEqual(result.extracted_data["company_name"], "北京测试科技有限公司")
        self.assertEqual(result.extracted_data["credit_code"], "91110000123456789X")
        self.assertEqual(result.confidence, 0.92)

    @patch("apps.client.api.clientidentitydoc_api._get_identity_extraction_service")
    def test_recognize_identity_doc_validation_error(self, mock_get_service):
        """测试验证错误处理"""
        # 准备测试数据
        mock_service = Mock()
        mock_get_service.return_value = mock_service

        # 模拟验证异常
        mock_service.extract.side_effect = ValidationException("无效的证件类型")

        # 调用 API
        result = recognize_identity_doc(self.mock_request, file=self.test_file, doc_type="invalid_type")

        # 验证结果
        self.assertIsInstance(result, IdentityRecognizeOut)
        self.assertFalse(result.success)
        self.assertEqual(result.doc_type, "invalid_type")
        self.assertEqual(result.extracted_data, {})
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.error, "VALIDATION_ERROR: 无效的证件类型")

    @patch("apps.client.api.clientidentitydoc_api._get_identity_extraction_service")
    def test_recognize_identity_doc_ocr_error(self, mock_get_service):
        """测试 OCR 错误处理"""
        # 准备测试数据
        mock_service = Mock()
        mock_get_service.return_value = mock_service

        # 模拟 OCR 异常
        mock_service.extract.side_effect = OCRExtractionError("图片文字识别失败")

        # 调用 API
        result = recognize_identity_doc(self.mock_request, file=self.test_file, doc_type=self.doc_type)

        # 验证结果
        self.assertIsInstance(result, IdentityRecognizeOut)
        self.assertFalse(result.success)
        self.assertEqual(result.doc_type, self.doc_type)
        self.assertEqual(result.extracted_data, {})
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.error, "识别失败: 图片文字识别失败")

    @patch("apps.client.api.clientidentitydoc_api._get_identity_extraction_service")
    def test_recognize_identity_doc_ollama_error(self, mock_get_service):
        """测试 Ollama 错误处理"""
        # 准备测试数据
        mock_service = Mock()
        mock_get_service.return_value = mock_service

        # 模拟 Ollama 异常
        mock_service.extract.side_effect = OllamaExtractionError("AI 信息提取失败")

        # 调用 API
        result = recognize_identity_doc(self.mock_request, file=self.test_file, doc_type=self.doc_type)

        # 验证结果
        self.assertIsInstance(result, IdentityRecognizeOut)
        self.assertFalse(result.success)
        self.assertEqual(result.doc_type, self.doc_type)
        self.assertEqual(result.extracted_data, {})
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.error, "识别失败: AI 信息提取失败")

    @patch("apps.client.api.clientidentitydoc_api._get_identity_extraction_service")
    def test_recognize_identity_doc_service_unavailable_error(self, mock_get_service):
        """测试服务不可用错误处理"""
        # 准备测试数据
        mock_service = Mock()
        mock_get_service.return_value = mock_service

        # 模拟服务不可用异常
        mock_service.extract.side_effect = ServiceUnavailableError("Ollama 服务不可用")

        # 调用 API
        result = recognize_identity_doc(self.mock_request, file=self.test_file, doc_type=self.doc_type)

        # 验证结果
        self.assertIsInstance(result, IdentityRecognizeOut)
        self.assertFalse(result.success)
        self.assertEqual(result.doc_type, self.doc_type)
        self.assertEqual(result.extracted_data, {})
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.error, "服务不可用: SERVICE_UNAVAILABLE: Ollama 服务不可用")

    @patch("apps.client.api.clientidentitydoc_api._get_identity_extraction_service")
    def test_recognize_identity_doc_unknown_error(self, mock_get_service):
        """测试未知错误处理"""
        # 准备测试数据
        mock_service = Mock()
        mock_get_service.return_value = mock_service

        # 模拟未知异常
        mock_service.extract.side_effect = Exception("未知错误")

        # 调用 API
        result = recognize_identity_doc(self.mock_request, file=self.test_file, doc_type=self.doc_type)

        # 验证结果
        self.assertIsInstance(result, IdentityRecognizeOut)
        self.assertFalse(result.success)
        self.assertEqual(result.doc_type, self.doc_type)
        self.assertEqual(result.extracted_data, {})
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.error, "未知错误: 未知错误")

    def test_recognize_identity_doc_file_reading(self):
        """测试文件读取功能"""
        # 创建测试文件
        test_content = b"test_image_data_12345"
        test_file = SimpleUploadedFile("test.jpg", test_content, content_type="image/jpeg")

        # 读取文件内容
        file_content = test_file.read()

        # 验证文件内容
        self.assertEqual(file_content, test_content)

    def test_api_response_structure_success(self):
        """测试成功响应结构"""
        # 创建成功响应
        response = IdentityRecognizeOut(
            success=True,
            doc_type="身份证",
            extracted_data={"name": "张三", "id_number": "110101199001010001"},
            confidence=0.95,
        )

        # 验证响应结构
        self.assertTrue(response.success)
        self.assertEqual(response.doc_type, "身份证")
        self.assertIsInstance(response.extracted_data, dict)
        self.assertEqual(response.confidence, 0.95)
        self.assertIsNone(response.error)

    def test_api_response_structure_error(self):
        """测试错误响应结构"""
        # 创建错误响应
        response = IdentityRecognizeOut(
            success=False, doc_type="身份证", extracted_data={}, confidence=0.0, error="识别失败"
        )

        # 验证响应结构
        self.assertFalse(response.success)
        self.assertEqual(response.doc_type, "身份证")
        self.assertEqual(response.extracted_data, {})
        self.assertEqual(response.confidence, 0.0)
        self.assertEqual(response.error, "识别失败")


class TestIdentityRecognizeSchemas(TestCase):
    """证件识别 Schema 测试"""

    def test_identity_recognize_out_success_schema(self):
        """测试成功识别输出 Schema"""
        data = {
            "success": True,
            "doc_type": "身份证",
            "extracted_data": {
                "name": "张三",
                "id_number": "110101199001010001",
                "address": "北京市朝阳区",
                "expiry_date": "2030-01-01",
            },
            "confidence": 0.95,
        }

        schema = IdentityRecognizeOut(**data)

        self.assertTrue(schema.success)
        self.assertEqual(schema.doc_type, "身份证")
        self.assertEqual(schema.extracted_data["name"], "张三")
        self.assertEqual(schema.confidence, 0.95)
        self.assertIsNone(schema.error)

    def test_identity_recognize_out_error_schema(self):
        """测试错误识别输出 Schema"""
        data = {
            "success": False,
            "doc_type": "身份证",
            "extracted_data": {},
            "confidence": 0.0,
            "error": "OCR 识别失败",
        }

        schema = IdentityRecognizeOut(**data)

        self.assertFalse(schema.success)
        self.assertEqual(schema.doc_type, "身份证")
        self.assertEqual(schema.extracted_data, {})
        self.assertEqual(schema.confidence, 0.0)
        self.assertEqual(schema.error, "OCR 识别失败")

    def test_identity_recognize_out_empty_extracted_data(self):
        """测试空提取数据的输出 Schema"""
        data = {"success": True, "doc_type": "护照", "extracted_data": {}, "confidence": 0.5}

        schema = IdentityRecognizeOut(**data)

        self.assertTrue(schema.success)
        self.assertEqual(schema.doc_type, "护照")
        self.assertEqual(schema.extracted_data, {})
        self.assertEqual(schema.confidence, 0.5)

    def test_identity_recognize_out_confidence_bounds(self):
        """测试置信度边界值"""
        # 测试最小值
        schema_min = IdentityRecognizeOut(success=True, doc_type="身份证", extracted_data={}, confidence=0.0)
        self.assertEqual(schema_min.confidence, 0.0)

        # 测试最大值
        schema_max = IdentityRecognizeOut(success=True, doc_type="身份证", extracted_data={}, confidence=1.0)
        self.assertEqual(schema_max.confidence, 1.0)
