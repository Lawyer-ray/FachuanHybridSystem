"""
证件识别 API 单元测试

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5
"""

from unittest.mock import Mock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.client.api.clientidentitydoc_api import recognize_identity_doc
from apps.client.schemas import IdentityRecognizeOut
from apps.client.services.identity_extraction.data_classes import (
    ExtractionResult,
    OCRExtractionError,
    OllamaExtractionError,
)
from apps.core.exceptions import ServiceUnavailableError, ValidationException


@pytest.fixture
def mock_request() -> Mock:
    return Mock()


@pytest.fixture
def test_file() -> SimpleUploadedFile:
    return SimpleUploadedFile("test_id_card.jpg", b"fake_image_content", content_type="image/jpeg")


def _safe_extract_result(
    success: bool = True,
    doc_type: str = "身份证",
    extracted_data: dict | None = None,
    confidence: float = 0.95,
    error: str | None = None,
) -> dict:
    return {
        "success": success,
        "doc_type": doc_type,
        "extracted_data": extracted_data or {},
        "confidence": confidence,
        "error": error,
    }


@patch("apps.client.api.clientidentitydoc_api._get_identity_extraction_service")
def test_recognize_identity_doc_success(
    mock_get_service: Mock, mock_request: Mock, test_file: SimpleUploadedFile
) -> None:
    mock_service = Mock()
    mock_get_service.return_value = mock_service
    mock_service.safe_extract.return_value = _safe_extract_result(
        doc_type="身份证",
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
    )

    result = recognize_identity_doc(mock_request, file=test_file, doc_type="身份证")  # type: ignore[arg-type]

    assert isinstance(result, IdentityRecognizeOut)
    assert result.success is True
    assert result.doc_type == "身份证"
    assert result.extracted_data["name"] == "张三"
    assert result.extracted_data["id_number"] == "110101199001010001"
    assert result.confidence == 0.95
    assert result.error is None


@patch("apps.client.api.clientidentitydoc_api._get_identity_extraction_service")
def test_recognize_identity_doc_passport_success(
    mock_get_service: Mock, mock_request: Mock, test_file: SimpleUploadedFile
) -> None:
    mock_service = Mock()
    mock_get_service.return_value = mock_service
    mock_service.safe_extract.return_value = _safe_extract_result(
        doc_type="护照",
        extracted_data={
            "name": "ZHANG SAN",
            "passport_number": "E12345678",
            "nationality": "CHN",
            "expiry_date": "2030-01-01",
            "birth_date": "1990-01-01",
        },
        confidence=0.88,
    )

    result = recognize_identity_doc(mock_request, file=test_file, doc_type="护照")  # type: ignore[arg-type]

    assert result.success is True
    assert result.doc_type == "护照"
    assert result.extracted_data["name"] == "ZHANG SAN"
    assert result.confidence == 0.88


@patch("apps.client.api.clientidentitydoc_api._get_identity_extraction_service")
def test_recognize_identity_doc_business_license_success(
    mock_get_service: Mock, mock_request: Mock, test_file: SimpleUploadedFile
) -> None:
    mock_service = Mock()
    mock_get_service.return_value = mock_service
    mock_service.safe_extract.return_value = _safe_extract_result(
        doc_type="营业执照",
        extracted_data={
            "company_name": "北京测试科技有限公司",
            "credit_code": "91110000123456789X",
            "legal_representative": "张三",
            "address": "北京市朝阳区",
            "business_scope": "技术开发",
            "registration_date": "2020-01-01",
        },
        confidence=0.92,
    )

    result = recognize_identity_doc(mock_request, file=test_file, doc_type="营业执照")  # type: ignore[arg-type]

    assert result.success is True
    assert result.doc_type == "营业执照"
    assert result.extracted_data["company_name"] == "北京测试科技有限公司"
    assert result.confidence == 0.92


@patch("apps.client.api.clientidentitydoc_api._get_identity_extraction_service")
def test_recognize_identity_doc_validation_error(
    mock_get_service: Mock, mock_request: Mock, test_file: SimpleUploadedFile
) -> None:
    mock_service = Mock()
    mock_get_service.return_value = mock_service
    mock_service.safe_extract.return_value = _safe_extract_result(
        success=False,
        confidence=0.0,
        error="VALIDATION_ERROR: 无效的证件类型",
    )

    result = recognize_identity_doc(mock_request, file=test_file, doc_type="invalid_type")  # type: ignore[arg-type]

    assert result.success is False
    assert result.extracted_data == {}
    assert result.confidence == 0.0
    assert result.error == "VALIDATION_ERROR: 无效的证件类型"


@patch("apps.client.api.clientidentitydoc_api._get_identity_extraction_service")
def test_recognize_identity_doc_ocr_error(
    mock_get_service: Mock, mock_request: Mock, test_file: SimpleUploadedFile
) -> None:
    mock_service = Mock()
    mock_get_service.return_value = mock_service
    mock_service.safe_extract.return_value = _safe_extract_result(
        success=False, confidence=0.0, error="识别失败: 图片文字识别失败"
    )

    result = recognize_identity_doc(mock_request, file=test_file, doc_type="身份证")  # type: ignore[arg-type]

    assert result.success is False
    assert result.error == "识别失败: 图片文字识别失败"


@patch("apps.client.api.clientidentitydoc_api._get_identity_extraction_service")
def test_recognize_identity_doc_ollama_error(
    mock_get_service: Mock, mock_request: Mock, test_file: SimpleUploadedFile
) -> None:
    mock_service = Mock()
    mock_get_service.return_value = mock_service
    mock_service.safe_extract.return_value = _safe_extract_result(
        success=False, confidence=0.0, error="识别失败: AI 信息提取失败"
    )

    result = recognize_identity_doc(mock_request, file=test_file, doc_type="身份证")  # type: ignore[arg-type]

    assert result.success is False
    assert result.error == "识别失败: AI 信息提取失败"


@patch("apps.client.api.clientidentitydoc_api._get_identity_extraction_service")
def test_recognize_identity_doc_service_unavailable(
    mock_get_service: Mock, mock_request: Mock, test_file: SimpleUploadedFile
) -> None:
    mock_service = Mock()
    mock_get_service.return_value = mock_service
    mock_service.safe_extract.return_value = _safe_extract_result(
        success=False, confidence=0.0, error="服务不可用: Ollama 服务不可用"
    )

    result = recognize_identity_doc(mock_request, file=test_file, doc_type="身份证")  # type: ignore[arg-type]

    assert result.success is False
    assert "服务不可用" in (result.error or "")


@patch("apps.client.api.clientidentitydoc_api._get_identity_extraction_service")
def test_recognize_identity_doc_unknown_error(
    mock_get_service: Mock, mock_request: Mock, test_file: SimpleUploadedFile
) -> None:
    mock_service = Mock()
    mock_get_service.return_value = mock_service
    mock_service.safe_extract.return_value = _safe_extract_result(
        success=False, confidence=0.0, error="未知错误: 未知错误"
    )

    result = recognize_identity_doc(mock_request, file=test_file, doc_type="身份证")  # type: ignore[arg-type]

    assert result.success is False
    assert result.error == "未知错误: 未知错误"


def test_identity_recognize_out_success_schema() -> None:
    schema = IdentityRecognizeOut(
        success=True,
        doc_type="身份证",
        extracted_data={"name": "张三", "id_number": "110101199001010001"},
        confidence=0.95,
    )
    assert schema.success is True
    assert schema.doc_type == "身份证"
    assert schema.extracted_data["name"] == "张三"
    assert schema.confidence == 0.95
    assert schema.error is None


def test_identity_recognize_out_error_schema() -> None:
    schema = IdentityRecognizeOut(
        success=False,
        doc_type="身份证",
        extracted_data={},
        confidence=0.0,
        error="OCR 识别失败",
    )
    assert schema.success is False
    assert schema.extracted_data == {}
    assert schema.error == "OCR 识别失败"


def test_identity_recognize_out_confidence_bounds() -> None:
    schema_min = IdentityRecognizeOut(success=True, doc_type="身份证", extracted_data={}, confidence=0.0)
    assert schema_min.confidence == 0.0

    schema_max = IdentityRecognizeOut(success=True, doc_type="身份证", extracted_data={}, confidence=1.0)
    assert schema_max.confidence == 1.0
