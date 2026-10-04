"""归档材料预览路径收敛测试（安全审计：material.file_path 不得直读任意路径）。

覆盖 ``apps/contracts/api/archive_api.py::preview_archive_material``：

1. 绝对路径（MEDIA_ROOT 外）→ 404，不读文件；
2. ``../`` 穿越 / 指向他合同归档目录 → 404；
3. 本合同归档目录（contracts/finalized/{contract_id}）内的文件正常 200。

说明：视图内的 ``sync_to_async(get_material_or_none)`` 在工作线程查库，测试事务
里的行对其不可见，因此对 material 查找做 stub（路径收敛才是被测对象）。
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from django.test import RequestFactory, override_settings

from apps.contracts.api.archive_api import preview_archive_material
from apps.contracts.models import Contract
from apps.contracts.models.finalized_material import FinalizedMaterial

PDF_BYTES = b"%PDF-1.4 archive preview"


@pytest.fixture
def contract(db: Any) -> Contract:
    return Contract.objects.create(name="归档预览测试合同", case_type="civil")


def _make_material(contract: Contract, file_path: str) -> FinalizedMaterial:
    return FinalizedMaterial.objects.create(
        contract=contract,
        file_path=file_path,
        original_filename="材料.pdf",
    )


def _call_preview(contract: Contract, material: FinalizedMaterial) -> Any:
    request = RequestFactory().get(f"/api/v1/contracts/{contract.id}/archive/materials/{material.id}/preview")

    def _fake_get_material_or_none(material_id: int, contract_id: int) -> FinalizedMaterial | None:
        return material if material_id == material.id and contract_id == contract.id else None

    with (
        patch(
            "apps.contracts.api.archive_api._ensure_contract_access",
            new=AsyncMock(return_value=contract),
        ),
        patch(
            "apps.contracts.services.archive.archive_query_service.get_material_or_none",
            new=_fake_get_material_or_none,
        ),
    ):
        return asyncio.run(preview_archive_material(request, contract.id, material.id))


@pytest.mark.django_db
def test_absolute_path_outside_media_root_rejected(contract: Contract, tmp_path: Any) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("top secret")
    material = _make_material(contract, str(secret))
    media = tmp_path / "media"
    with override_settings(MEDIA_ROOT=str(media)):
        response = _call_preview(contract, material)
    assert response.status_code == 404
    assert b"top secret" not in getattr(response, "content", b"")


@pytest.mark.django_db
def test_traversal_escape_rejected(contract: Contract, tmp_path: Any) -> None:
    media = tmp_path / "media"
    leak = media / "leak.txt"
    leak.parent.mkdir(parents=True, exist_ok=True)
    leak.write_bytes(b"media root leak")
    material = _make_material(contract, "contracts/finalized/../../leak.txt")
    with override_settings(MEDIA_ROOT=str(media)):
        response = _call_preview(contract, material)
    assert response.status_code == 404
    assert b"media root leak" not in response.content


@pytest.mark.django_db
def test_other_contract_directory_rejected(contract: Contract, tmp_path: Any) -> None:
    other = Contract.objects.create(name="别的合同", case_type="civil")
    media = tmp_path / "media"
    foreign = media / "contracts" / "finalized" / str(other.id) / "a.pdf"
    foreign.parent.mkdir(parents=True, exist_ok=True)
    foreign.write_bytes(PDF_BYTES)
    material = _make_material(contract, f"contracts/finalized/{other.id}/a.pdf")
    with override_settings(MEDIA_ROOT=str(media)):
        response = _call_preview(contract, material)
    assert response.status_code == 404
    assert PDF_BYTES not in response.content


@pytest.mark.django_db
def test_own_directory_file_previewed(contract: Contract, tmp_path: Any) -> None:
    media = tmp_path / "media"
    own = media / "contracts" / "finalized" / str(contract.id) / "a.pdf"
    own.parent.mkdir(parents=True, exist_ok=True)
    own.write_bytes(PDF_BYTES)
    material = _make_material(contract, f"contracts/finalized/{contract.id}/a.pdf")
    with override_settings(MEDIA_ROOT=str(media)):
        response = _call_preview(contract, material)
    assert response.status_code == 200
    assert response.content == PDF_BYTES
    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Disposition"].startswith("inline")


@pytest.mark.django_db
def test_missing_file_in_own_directory_404(contract: Contract, tmp_path: Any) -> None:
    media = tmp_path / "media"
    material = _make_material(contract, f"contracts/finalized/{contract.id}/ghost.pdf")
    with override_settings(MEDIA_ROOT=str(media)):
        response = _call_preview(contract, material)
    assert response.status_code == 404
    assert PDF_BYTES not in response.content
    assert response.status_code == 404
