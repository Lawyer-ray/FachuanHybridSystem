from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from django.test import Client, override_settings
from django.urls import reverse

from apps.contracts.models import (
    Contract,
    ContractFolderBinding,
    ContractParty,
    ContractPayment,
    FinalizedMaterial,
    InvoiceStatus,
    MaterialCategory,
    PartyRole,
    SupplementaryAgreement,
)
from apps.testing.factories import ClientFactory, ContractFactory, LawyerFactory


def create_authenticated_client(user: Any) -> Client:
    client = Client()
    client.force_login(user)
    return client


def get_json_response(response: Any) -> Any:
    return response.json()


@pytest.fixture
def contracts_admin_user() -> Any:
    return LawyerFactory(is_admin=True, is_staff=True, is_superuser=True)


@pytest.fixture
def api_client(contracts_admin_user: Any) -> Client:
    return create_authenticated_client(contracts_admin_user)


def _assert_status(response: Any, expected_status: int = 200) -> None:
    assert response.status_code == expected_status, response.content.decode("utf-8", errors="ignore")


def _post_json(client: Client, path: str, data: dict[str, Any]) -> Any:
    return client.post(
        path,
        data=json.dumps(data),
        content_type="application/json",
        HTTP_HOST="localhost",
    )


def _put_json(client: Client, path: str, data: dict[str, Any]) -> Any:
    return client.put(
        path,
        data=json.dumps(data),
        content_type="application/json",
        HTTP_HOST="localhost",
    )


@pytest.mark.django_db
@pytest.mark.integration
class TestContractHttpSmoke:
    def test_contract_crud_lawyers_and_all_parties(self, api_client: Client, contracts_admin_user: Any) -> None:
        secondary_lawyer = LawyerFactory(law_firm=contracts_admin_user.law_firm)
        principal_client = ClientFactory(name="合同冒烟委托人")

        create_response = _post_json(
            api_client,
            "/api/v1/contracts/contracts",
            {
                "payload": {
                    "name": "合同冒烟测试",
                    "case_type": "civil",
                    "status": "active",
                    "fee_mode": "fixed",
                    "fixed_amount": 10000.0,
                    "lawyer_ids": [contracts_admin_user.id],
                }
            },
        )
        _assert_status(create_response)
        created = get_json_response(create_response)
        contract_id = int(created["id"])

        ContractParty.objects.create(
            contract_id=contract_id,
            client=principal_client,
            role=PartyRole.PRINCIPAL,
        )

        list_response = api_client.get(
            "/api/v1/contracts/contracts",
            {"status": "active"},
            HTTP_HOST="localhost",
        )
        _assert_status(list_response)
        listed_contracts = get_json_response(list_response)
        assert any(item["id"] == contract_id for item in listed_contracts)

        detail_response = api_client.get(
            f"/api/v1/contracts/contracts/{contract_id}",
            HTTP_HOST="localhost",
        )
        _assert_status(detail_response)
        detail_payload = get_json_response(detail_response)
        assert detail_payload["name"] == "合同冒烟测试"

        update_response = _put_json(
            api_client,
            f"/api/v1/contracts/contracts/{contract_id}?confirm_finance=true",
            {
                "payload": {
                    "name": "合同冒烟测试-更新",
                    "status": "closed",
                    "fixed_amount": 12000.0,
                }
            },
        )
        _assert_status(update_response)
        updated_payload = get_json_response(update_response)
        assert updated_payload["name"] == "合同冒烟测试-更新"
        assert updated_payload["status"] == "closed"

        lawyer_response = _put_json(
            api_client,
            f"/api/v1/contracts/contracts/{contract_id}/lawyers",
            {"lawyer_ids": [contracts_admin_user.id, secondary_lawyer.id]},
        )
        _assert_status(lawyer_response)
        assigned_ids = set(
            Contract.objects.get(id=contract_id).assignments.values_list("lawyer_id", flat=True)
        )
        assert assigned_ids == {contracts_admin_user.id, secondary_lawyer.id}

        all_parties_response = api_client.get(
            f"/api/v1/contracts/contracts/{contract_id}/all-parties",
            HTTP_HOST="localhost",
        )
        _assert_status(all_parties_response)
        all_parties = get_json_response(all_parties_response)
        assert isinstance(all_parties, list)
        assert all_parties

        delete_response = api_client.delete(
            f"/api/v1/contracts/contracts/{contract_id}",
            HTTP_HOST="localhost",
        )
        _assert_status(delete_response)
        assert get_json_response(delete_response)["success"] is True
        assert not Contract.objects.filter(id=contract_id).exists()

    def test_contract_full_creation_and_supplementary_agreements(self, api_client: Client, contracts_admin_user: Any) -> None:
        case_client = ClientFactory(name="案件委托人")
        supplementary_client = ClientFactory(name="补充协议当事人")

        create_response = _post_json(
            api_client,
            "/api/v1/contracts/contracts/full",
            {
                "name": "合同+案件冒烟",
                "case_type": "civil",
                "status": "active",
                "fee_mode": "fixed",
                "fixed_amount": 8000.0,
                "lawyer_ids": [contracts_admin_user.id],
                "cases": [
                    {
                        "name": "合同对应案件",
                        "case_type": "civil",
                        "target_amount": 30000.0,
                        "parties": [
                            {
                                "client_id": case_client.id,
                                "legal_status": "plaintiff",
                            }
                        ],
                    }
                ],
            },
        )
        _assert_status(create_response)
        contract_id = int(get_json_response(create_response)["id"])
        contract = Contract.objects.get(id=contract_id)
        assert contract.cases.count() == 1

        ContractParty.objects.create(
            contract=contract,
            client=case_client,
            role=PartyRole.PRINCIPAL,
        )

        agreement_create_response = _post_json(
            api_client,
            "/api/v1/contracts/supplementary-agreements",
            {
                "contract_id": contract_id,
                "name": "第一次补充协议",
                "party_ids": [supplementary_client.id],
            },
        )
        _assert_status(agreement_create_response)
        agreement_payload = get_json_response(agreement_create_response)
        agreement_id = int(agreement_payload["id"])
        assert agreement_payload["name"] == "第一次补充协议"

        agreement_detail_response = api_client.get(
            f"/api/v1/contracts/supplementary-agreements/{agreement_id}",
            HTTP_HOST="localhost",
        )
        _assert_status(agreement_detail_response)
        assert get_json_response(agreement_detail_response)["id"] == agreement_id

        agreement_list_response = api_client.get(
            f"/api/v1/contracts/contracts/{contract_id}/supplementary-agreements",
            HTTP_HOST="localhost",
        )
        _assert_status(agreement_list_response)
        agreement_list = get_json_response(agreement_list_response)
        assert len(agreement_list) == 1

        agreement_update_response = _put_json(
            api_client,
            f"/api/v1/contracts/supplementary-agreements/{agreement_id}",
            {
                "name": "第一次补充协议-更新",
                "party_ids": [case_client.id, supplementary_client.id],
            },
        )
        _assert_status(agreement_update_response)
        updated_agreement = get_json_response(agreement_update_response)
        assert updated_agreement["name"] == "第一次补充协议-更新"

        all_parties_response = api_client.get(
            f"/api/v1/contracts/contracts/{contract_id}/all-parties",
            HTTP_HOST="localhost",
        )
        _assert_status(all_parties_response)
        all_parties = get_json_response(all_parties_response)
        assert isinstance(all_parties, list)
        assert len(all_parties) >= 1

        agreement_delete_response = api_client.delete(
            f"/api/v1/contracts/supplementary-agreements/{agreement_id}",
            HTTP_HOST="localhost",
        )
        _assert_status(agreement_delete_response)
        assert get_json_response(agreement_delete_response)["success"] is True
        assert not SupplementaryAgreement.objects.filter(id=agreement_id).exists()

    def test_contract_payments_and_finance_stats(self, api_client: Client) -> None:
        contract = ContractFactory(fixed_amount=10000.0)

        create_payment_response = _post_json(
            api_client,
            "/api/v1/contracts/finance/payments",
            {
                "contract_id": contract.id,
                "amount": 3000.0,
                "received_at": "2026-04-04",
                "invoiced_amount": 1000.0,
                "invoice_status": InvoiceStatus.UNINVOICED,
                "note": "首期款",
                "confirm": True,
            },
        )
        _assert_status(create_payment_response)
        payment_payload = get_json_response(create_payment_response)
        payment_id = int(payment_payload["id"])
        assert payment_payload["contract"] == contract.id

        list_response = api_client.get(
            "/api/v1/contracts/finance/payments",
            {"contract_id": contract.id},
            HTTP_HOST="localhost",
        )
        _assert_status(list_response)
        listed_payments = get_json_response(list_response)
        assert len(listed_payments) == 1

        update_response = _put_json(
            api_client,
            f"/api/v1/contracts/finance/payments/{payment_id}",
            {
                "amount": 3500.0,
                "invoiced_amount": 2000.0,
                "note": "首期款-更新",
                "confirm": True,
            },
        )
        _assert_status(update_response)
        updated_payment = get_json_response(update_response)
        assert float(updated_payment["amount"]) == 3500.0

        stats_response = api_client.get(
            "/api/v1/contracts/finance/stats",
            {"contract_id": contract.id},
            HTTP_HOST="localhost",
        )
        _assert_status(stats_response)
        stats_payload = get_json_response(stats_response)
        assert float(stats_payload["total_received_all"]) == 3500.0
        assert float(stats_payload["total_invoiced_all"]) == 2000.0

        delete_response = api_client.delete(
            f"/api/v1/contracts/finance/payments/{payment_id}?confirm=true",
            HTTP_HOST="localhost",
        )
        _assert_status(delete_response)
        assert get_json_response(delete_response)["success"] is True
        assert not ContractPayment.objects.filter(id=payment_id).exists()

    def test_folder_binding_and_folder_scan_endpoints(self, api_client: Client) -> None:
        contract = ContractFactory()

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "incoming").mkdir()
            (root / "archive").mkdir()

            with (
                override_settings(FOLDER_BROWSE_ROOTS=[str(root)]),
                patch("apps.contracts.api.folder_binding_api._require_contract_access"),
            ):
                browse_response = api_client.get(
                    "/api/v1/contracts/folder-browse",
                    {"path": str(root)},
                    HTTP_HOST="localhost",
                )
                _assert_status(browse_response)
                browse_payload = get_json_response(browse_response)
                assert browse_payload["browsable"] is True
                assert len(browse_payload["entries"]) == 2

                create_binding_response = _post_json(
                    api_client,
                    f"/api/v1/contracts/{contract.id}/folder-binding",
                    {"folder_path": str(root)},
                )
                _assert_status(create_binding_response)
                binding_payload = get_json_response(create_binding_response)
                assert binding_payload["contract_id"] == contract.id
                assert ContractFolderBinding.objects.filter(contract_id=contract.id).exists()

                get_binding_response = api_client.get(
                    f"/api/v1/contracts/{contract.id}/folder-binding",
                    HTTP_HOST="localhost",
                )
                _assert_status(get_binding_response)
                assert get_json_response(get_binding_response)["folder_path"] == str(root)

                delete_binding_response = api_client.delete(
                    f"/api/v1/contracts/{contract.id}/folder-binding",
                    HTTP_HOST="localhost",
                )
                _assert_status(delete_binding_response)
                assert get_json_response(delete_binding_response)["success"] is True

        session_id = uuid4()
        mock_session = Mock(id=session_id, status="running", task_id="task-1")
        mock_service = Mock()
        mock_service.start_scan.return_value = mock_session
        mock_service.list_scan_subfolders.return_value = {
            "root_path": "/tmp/contracts",
            "subfolders": [{"relative_path": "incoming", "display_name": "incoming"}],
        }
        mock_service.get_session.return_value = mock_session
        mock_service.build_status_payload.return_value = {
            "session_id": str(session_id),
            "status": "completed",
            "progress": 100,
            "current_file": "",
            "summary": {
                "total_files": 1,
                "deduped_files": 1,
                "classified_files": 1,
            },
            "candidates": [
                {
                    "source_path": "/tmp/contracts/incoming/invoice.pdf",
                    "filename": "invoice.pdf",
                    "file_size": 128,
                    "modified_at": "2026-04-04T10:00:00+08:00",
                    "base_name": "invoice",
                    "version_token": "V1",
                    "extract_method": "pdf",
                    "text_excerpt": "invoice",
                    "suggested_category": MaterialCategory.INVOICE,
                    "confidence": 0.99,
                    "reason": "smoke",
                    "selected": True,
                }
            ],
            "error_message": "",
        }
        mock_service.confirm_import.return_value = {
            "session_id": str(session_id),
            "status": "imported",
            "imported_count": 1,
        }

        with (
            patch("apps.contracts.api.folder_scan_api._require_contract_access"),
            patch("apps.contracts.api.folder_scan_api._get_service", return_value=mock_service),
        ):
            start_response = _post_json(
                api_client,
                f"/api/v1/contracts/{contract.id}/folder-scan",
                {"rescan": False, "scan_subfolder": "incoming"},
            )
            _assert_status(start_response)
            assert get_json_response(start_response)["session_id"] == str(session_id)

            subfolders_response = api_client.get(
                f"/api/v1/contracts/{contract.id}/folder-scan/subfolders",
                HTTP_HOST="localhost",
            )
            _assert_status(subfolders_response)
            assert get_json_response(subfolders_response)["subfolders"][0]["relative_path"] == "incoming"

            status_response = api_client.get(
                f"/api/v1/contracts/{contract.id}/folder-scan/{session_id}",
                HTTP_HOST="localhost",
            )
            _assert_status(status_response)
            assert get_json_response(status_response)["status"] == "completed"

            confirm_response = _post_json(
                api_client,
                f"/api/v1/contracts/{contract.id}/folder-scan/{session_id}/confirm",
                {
                    "items": [
                        {
                            "source_path": "/tmp/contracts/incoming/invoice.pdf",
                            "selected": True,
                            "category": MaterialCategory.INVOICE,
                        }
                    ]
                },
            )
            _assert_status(confirm_response)
            assert get_json_response(confirm_response)["imported_count"] == 1

    def test_contract_document_endpoints(self, api_client: Client) -> None:
        contract = ContractFactory(name="文档冒烟合同")
        agreement = SupplementaryAgreement.objects.create(contract=contract, name="文档补充协议")

        contract_generation_service = Mock()
        contract_generation_service.get_preview_context.return_value = [{"key": "合同名称", "value": contract.name}]
        contract_generation_service.generate_contract_document_result.return_value = (
            b"contract-docx",
            "合同.docx",
            None,
            None,
        )

        folder_generation_service = Mock()
        folder_generation_service.generate_folder_with_documents_result.return_value = (
            b"",
            "合同文件夹.zip",
            "/tmp/export/contracts",
            None,
        )

        supplementary_generation_service = Mock()
        supplementary_generation_service.get_preview_context.return_value = [
            {"key": "补充协议名称", "value": agreement.name}
        ]
        supplementary_generation_service.generate_supplementary_agreement_result.return_value = (
            b"agreement-docx",
            "补充协议.docx",
            None,
            None,
        )

        with (
            patch("apps.documents.api.generation_api._require_contract_access"),
            patch(
                "apps.documents.api.generation_api._get_contract_generation_service",
                return_value=contract_generation_service,
            ),
            patch(
                "apps.documents.api.generation_api._get_folder_generation_service",
                return_value=folder_generation_service,
            ),
            patch(
                "apps.documents.api.generation_api._get_supplementary_agreement_service",
                return_value=supplementary_generation_service,
            ),
        ):
            preview_contract_response = api_client.get(
                f"/api/v1/documents/contracts/{contract.id}/preview",
                HTTP_HOST="localhost",
            )
            _assert_status(preview_contract_response)
            assert get_json_response(preview_contract_response)["success"] is True

            preview_agreement_response = api_client.get(
                f"/api/v1/documents/contracts/{contract.id}/supplementary-agreements/{agreement.id}/preview",
                HTTP_HOST="localhost",
            )
            _assert_status(preview_agreement_response)
            assert get_json_response(preview_agreement_response)["success"] is True

            contract_download_response = api_client.get(
                f"/api/v1/documents/contracts/{contract.id}/download",
                HTTP_HOST="localhost",
            )
            _assert_status(contract_download_response)
            assert contract_download_response["Content-Disposition"] is not None

            folder_download_response = api_client.get(
                f"/api/v1/documents/contracts/{contract.id}/folder/download",
                HTTP_HOST="localhost",
            )
            _assert_status(folder_download_response)
            assert get_json_response(folder_download_response)["folder_path"] == "/tmp/export/contracts"

            agreement_download_response = api_client.get(
                f"/api/v1/documents/contracts/{contract.id}/supplementary-agreements/{agreement.id}/download",
                HTTP_HOST="localhost",
            )
            _assert_status(agreement_download_response)
            assert agreement_download_response["Content-Disposition"] is not None


@pytest.mark.django_db
@pytest.mark.integration
class TestContractAdminSmoke:
    def test_contract_admin_pages_and_custom_actions(
        self,
        api_client: Client,
        contracts_admin_user: Any,
    ) -> None:
        contract = ContractFactory()
        material_one = FinalizedMaterial.objects.create(
            contract=contract,
            file_path="contracts/material-1.pdf",
            original_filename="材料1.pdf",
            category=MaterialCategory.INVOICE,
            order=0,
        )
        material_two = FinalizedMaterial.objects.create(
            contract=contract,
            file_path="contracts/material-2.pdf",
            original_filename="材料2.pdf",
            category=MaterialCategory.SUPPLEMENTARY_AGREEMENT,
            order=1,
        )

        batch_service = Mock()
        batch_service.list_unbound_case_type_cards.return_value = []
        batch_service.preview.return_value = {"rows": [], "total": 0}
        batch_service.save.return_value = {"saved_count": 0, "skipped_count": 0}

        oa_session = Mock(id=11)
        oa_service = Mock()
        oa_service.list_missing_oa_contracts.return_value = []
        oa_service.create_or_get_active_session.return_value = oa_session
        oa_service.submit_session_task.return_value = oa_session
        oa_service.get_session.return_value = oa_session
        oa_service.build_status_payload.return_value = {
            "session_id": 11,
            "status": "completed",
            "contracts": [],
        }
        oa_service.save_manual_contract_oa_fields.return_value = {
            "saved_count": 0,
            "error_count": 0,
            "errors": [],
        }

        with (
            patch(
                "apps.contracts.admin.wiring_admin.get_contract_batch_folder_binding_service",
                return_value=batch_service,
            ),
            patch(
                "apps.contracts.admin.wiring_admin.get_contract_oa_sync_service",
                return_value=oa_service,
            ),
        ):
            contract_changelist = api_client.get(
                reverse("admin:contracts_contract_changelist"),
                HTTP_HOST="localhost",
            )
            _assert_status(contract_changelist)

            supplementary_changelist = api_client.get(
                reverse("admin:contracts_supplementaryagreement_changelist"),
                HTTP_HOST="localhost",
            )
            _assert_status(supplementary_changelist)

            batch_page_response = api_client.get(
                reverse("admin:contracts_contract_batch_folder_binding"),
                HTTP_HOST="localhost",
            )
            _assert_status(batch_page_response)

            batch_preview_response = _post_json(
                api_client,
                reverse("admin:contracts_contract_batch_folder_binding_preview"),
                {"case_type_roots": []},
            )
            _assert_status(batch_preview_response)
            assert get_json_response(batch_preview_response)["success"] is True

            batch_save_response = _post_json(
                api_client,
                reverse("admin:contracts_contract_batch_folder_binding_save"),
                {
                    "case_type_roots": [],
                    "contract_selections": [],
                },
            )
            _assert_status(batch_save_response)
            assert get_json_response(batch_save_response)["success"] is True

            batch_open_folder_response = _post_json(
                api_client,
                reverse("admin:contracts_contract_batch_folder_binding_open_folder"),
                {
                    "root_path": "/tmp/contracts",
                    "folder_path": "/tmp/contracts/civil",
                },
            )
            _assert_status(batch_open_folder_response)
            assert get_json_response(batch_open_folder_response)["success"] is True

            oa_page_response = api_client.get(
                reverse("admin:contracts_contract_oa_sync"),
                HTTP_HOST="localhost",
            )
            _assert_status(oa_page_response)

            oa_start_response = _post_json(
                api_client,
                reverse("admin:contracts_contract_oa_sync_start"),
                {},
            )
            _assert_status(oa_start_response)
            assert get_json_response(oa_start_response)["success"] is True

            oa_status_response = api_client.get(
                reverse("admin:contracts_contract_oa_sync_status", args=[11]),
                HTTP_HOST="localhost",
            )
            _assert_status(oa_status_response)
            assert get_json_response(oa_status_response)["success"] is True

            oa_save_response = _post_json(
                api_client,
                reverse("admin:contracts_contract_oa_sync_save"),
                {"entries": []},
            )
            _assert_status(oa_save_response)
            assert get_json_response(oa_save_response)["success"] is True

        reorder_response = _post_json(
            api_client,
            reverse("admin:contracts_contract_reorder_materials", args=[contract.id]),
            {"ids": [material_two.id, material_one.id]},
        )
        _assert_status(reorder_response)
        assert get_json_response(reorder_response)["ok"] is True

        material_one.refresh_from_db()
        material_two.refresh_from_db()
        assert material_two.order == 0
        assert material_one.order == 1
