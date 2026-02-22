"""
文档生成 API 集成测试

测试合同文档下载、文件夹下载、补充协议下载端点的
访问控制和错误处理流程。

Requirements: 5.3
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock, patch

import pytest

from apps.core.exceptions import NotFoundError, ValidationException
from apps.documents.api.generation_api import (
    download_contract_document,
    download_contract_folder,
    download_supplementary_agreement,
)
from tests.factories.contract_factories import ContractFactory
from tests.factories.organization_factories import LawyerFactory


def _make_request(
    user: Any = None,
    *,
    perm_open_access: bool = True,
    org_access: Any = None,
) -> Mock:
    """构造模拟 request 对象。"""
    request = Mock()
    request.user = user
    request.perm_open_access = perm_open_access
    request.org_access = org_access
    return request


@pytest.mark.django_db
@pytest.mark.integration
class TestDownloadContractDocumentAPI:
    """合同文档下载 API 测试"""

    def test_download_contract_document_success(self) -> None:
        """成功下载合同文档（返回文件响应）"""
        contract = ContractFactory(name="测试合同")
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        with (
            patch("apps.documents.api.generation_api._require_contract_access"),
            patch("apps.documents.api.generation_api._get_contract_generation_service") as mock_factory,
        ):
            mock_service = Mock()
            mock_service.generate_contract_document_result.return_value = (
                b"fake-docx-content",
                "测试合同.docx",
                None,  # no saved_path => file download
                None,  # no error
            )
            mock_factory.return_value = mock_service

            result = download_contract_document(request, contract.id)  # type: ignore[attr-defined]

            assert result["Content-Disposition"] is not None
            mock_service.generate_contract_document_result.assert_called_once_with(contract.id)  # type: ignore[attr-defined]

    def test_download_contract_document_saved_to_folder(self) -> None:
        """合同文档保存到绑定文件夹（返回 JSON）"""
        contract = ContractFactory()
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        with (
            patch("apps.documents.api.generation_api._require_contract_access"),
            patch("apps.documents.api.generation_api._get_contract_generation_service") as mock_factory,
        ):
            mock_service = Mock()
            mock_service.generate_contract_document_result.return_value = (
                b"",
                "合同.docx",
                "/path/to/folder",
                None,
            )
            mock_factory.return_value = mock_service

            result = download_contract_document(request, contract.id)  # type: ignore[attr-defined]

            assert result["success"] is True
            assert result["folder_path"] == "/path/to/folder"

    def test_download_contract_document_generation_error(self) -> None:
        """合同文档生成失败抛出 ValidationException"""
        contract = ContractFactory()
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        with (
            patch("apps.documents.api.generation_api._require_contract_access"),
            patch("apps.documents.api.generation_api._get_contract_generation_service") as mock_factory,
        ):
            mock_service = Mock()
            mock_service.generate_contract_document_result.return_value = (
                b"",
                "",
                None,
                "模板文件不存在",
            )
            mock_factory.return_value = mock_service

            with pytest.raises(ValidationException):
                download_contract_document(request, contract.id)  # type: ignore[attr-defined]


@pytest.mark.django_db
@pytest.mark.integration
class TestDownloadContractFolderAPI:
    """合同文件夹下载 API 测试"""

    def test_download_folder_success(self) -> None:
        """成功下载合同文件夹 ZIP"""
        contract = ContractFactory()
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        with (
            patch("apps.documents.api.generation_api._require_contract_access"),
            patch("apps.documents.api.generation_api._get_folder_generation_service") as mock_factory,
        ):
            mock_service = Mock()
            mock_service.generate_folder_with_documents_result.return_value = (
                b"fake-zip-content",
                "合同文件夹.zip",
                None,
                None,
            )
            mock_factory.return_value = mock_service

            result = download_contract_folder(request, contract.id)  # type: ignore[attr-defined]

            assert result["Content-Disposition"] is not None

    def test_download_folder_extracted_to_binding(self) -> None:
        """文件夹解压到绑定路径（返回 JSON）"""
        contract = ContractFactory()
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        with (
            patch("apps.documents.api.generation_api._require_contract_access"),
            patch("apps.documents.api.generation_api._get_folder_generation_service") as mock_factory,
        ):
            mock_service = Mock()
            mock_service.generate_folder_with_documents_result.return_value = (
                b"",
                "文件夹.zip",
                "/extract/path",
                None,
            )
            mock_factory.return_value = mock_service

            result = download_contract_folder(request, contract.id)  # type: ignore[attr-defined]

            assert result["success"] is True
            assert result["folder_path"] == "/extract/path"

    def test_download_folder_generation_error(self) -> None:
        """文件夹生成失败抛出 ValidationException"""
        contract = ContractFactory()
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        with (
            patch("apps.documents.api.generation_api._require_contract_access"),
            patch("apps.documents.api.generation_api._get_folder_generation_service") as mock_factory,
        ):
            mock_service = Mock()
            mock_service.generate_folder_with_documents_result.return_value = (
                b"",
                "",
                None,
                "文件夹模板不存在",
            )
            mock_factory.return_value = mock_service

            with pytest.raises(ValidationException):
                download_contract_folder(request, contract.id)  # type: ignore[attr-defined]


@pytest.mark.django_db
@pytest.mark.integration
class TestDownloadSupplementaryAgreementAPI:
    """补充协议下载 API 测试"""

    def test_download_agreement_success(self) -> None:
        """成功下载补充协议"""
        contract = ContractFactory()
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        with (
            patch("apps.documents.api.generation_api._require_contract_access"),
            patch("apps.documents.api.generation_api._get_supplementary_agreement_service") as mock_factory,
        ):
            mock_service = Mock()
            mock_service.generate_supplementary_agreement_result.return_value = (
                b"fake-docx",
                "补充协议.docx",
                None,
                None,
            )
            mock_factory.return_value = mock_service

            result = download_supplementary_agreement(request, contract.id, 1)  # type: ignore[attr-defined]

            assert result["Content-Disposition"] is not None

    def test_download_agreement_saved_to_folder(self) -> None:
        """补充协议保存到绑定文件夹"""
        contract = ContractFactory()
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        with (
            patch("apps.documents.api.generation_api._require_contract_access"),
            patch("apps.documents.api.generation_api._get_supplementary_agreement_service") as mock_factory,
        ):
            mock_service = Mock()
            mock_service.generate_supplementary_agreement_result.return_value = (
                b"",
                "补充协议.docx",
                "/saved/path",
                None,
            )
            mock_factory.return_value = mock_service

            result = download_supplementary_agreement(request, contract.id, 1)  # type: ignore[attr-defined]

            assert result["success"] is True
            assert result["folder_path"] == "/saved/path"

    def test_download_agreement_generation_error(self) -> None:
        """补充协议生成失败"""
        contract = ContractFactory()
        lawyer = LawyerFactory(is_admin=True)
        request = _make_request(user=lawyer)

        with (
            patch("apps.documents.api.generation_api._require_contract_access"),
            patch("apps.documents.api.generation_api._get_supplementary_agreement_service") as mock_factory,
        ):
            mock_service = Mock()
            mock_service.generate_supplementary_agreement_result.return_value = (
                b"",
                "",
                None,
                "补充协议不存在",
            )
            mock_factory.return_value = mock_service

            with pytest.raises(ValidationException):
                download_supplementary_agreement(request, contract.id, 1)  # type: ignore[attr-defined]
