"""Admin 归档材料路径收敛测试（安全审计 2026-10-19：file_path 不得直读/直删任意路径）。

覆盖 ``apps/contracts/admin/mixins/archive_mixin.py`` 的 preview / delete 视图
（口径同 API 侧 ``test_archive_material_preview.py``）：

1. 绝对路径（MEDIA_ROOT 外）→ 404，不读文件；
2. ``../`` 穿越 / 指向他合同归档目录 → 404；
3. 本合同归档目录（contracts/finalized/{contract_id}）内的文件正常预览；
4. 删除视图对越界路径跳过物理删除（记录仍删除），不误删任意文件。
"""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, override_settings

from apps.contracts.admin.contract_admin import ContractAdmin
from apps.contracts.models import Contract
from apps.contracts.models.finalized_material import FinalizedMaterial
from apps.organization.models import Lawyer

PDF_BYTES = b"%PDF-1.4 admin archive preview"


@pytest.fixture
def superuser(db: Any) -> Lawyer:
    # 未挂律所的平台级管理员（is_admin + law_firm_id=None）→ 行级全放行，
    # 使路径收敛本身成为被测对象
    return Lawyer.objects.create_superuser(
        username="archive_admin_su",
        password="pw-12345678",  # pragma: allowlist secret
        real_name="归档管理员",
        is_staff=True,
    )


@pytest.fixture
def contract(db: Any) -> Contract:
    return Contract.objects.create(name="归档路径收敛测试合同", case_type="civil")


def _make_material(contract: Contract, file_path: str) -> FinalizedMaterial:
    return FinalizedMaterial.objects.create(
        contract=contract,
        file_path=file_path,
        original_filename="材料.pdf",
    )


def _make_admin() -> ContractAdmin:
    return ContractAdmin(Contract, AdminSite())


def _call_preview(superuser: Lawyer, contract: Contract, material: FinalizedMaterial) -> Any:
    request = RequestFactory().get(f"/admin/contracts/contract/{contract.id}/archive/materials/{material.id}/preview")
    request.user = superuser
    return _make_admin().preview_archive_material_view(request, contract.id, material.id)


def _call_delete(superuser: Lawyer, contract: Contract, material: FinalizedMaterial) -> Any:
    request = RequestFactory().post(f"/admin/contracts/contract/{contract.id}/archive/materials/{material.id}/delete")
    request.user = superuser
    return _make_admin().delete_archive_material_view(request, contract.id, material.id)


@pytest.mark.django_db
def test_preview_absolute_path_outside_media_root_rejected(
    contract: Contract, superuser: Lawyer, tmp_path: Any
) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("top secret")
    material = _make_material(contract, str(secret))
    media = tmp_path / "media"
    with override_settings(MEDIA_ROOT=str(media)):
        response = _call_preview(superuser, contract, material)
    assert response.status_code == 404
    assert b"top secret" not in getattr(response, "content", b"")


@pytest.mark.django_db
def test_preview_traversal_escape_rejected(contract: Contract, superuser: Lawyer, tmp_path: Any) -> None:
    media = tmp_path / "media"
    leak = media / "leak.txt"
    leak.parent.mkdir(parents=True, exist_ok=True)
    leak.write_bytes(b"media root leak")
    material = _make_material(contract, "contracts/finalized/../../leak.txt")
    with override_settings(MEDIA_ROOT=str(media)):
        response = _call_preview(superuser, contract, material)
    assert response.status_code == 404
    assert b"media root leak" not in response.content


@pytest.mark.django_db
def test_preview_other_contract_directory_rejected(contract: Contract, superuser: Lawyer, tmp_path: Any) -> None:
    other = Contract.objects.create(name="别的合同C", case_type="civil")
    media = tmp_path / "media"
    foreign = media / "contracts" / "finalized" / str(other.id) / "a.pdf"
    foreign.parent.mkdir(parents=True, exist_ok=True)
    foreign.write_bytes(PDF_BYTES)
    material = _make_material(contract, f"contracts/finalized/{other.id}/a.pdf")
    with override_settings(MEDIA_ROOT=str(media)):
        response = _call_preview(superuser, contract, material)
    assert response.status_code == 404
    assert PDF_BYTES not in response.content


@pytest.mark.django_db
def test_preview_own_directory_file_previewed(contract: Contract, superuser: Lawyer, tmp_path: Any) -> None:
    media = tmp_path / "media"
    own = media / "contracts" / "finalized" / str(contract.id) / "a.pdf"
    own.parent.mkdir(parents=True, exist_ok=True)
    own.write_bytes(PDF_BYTES)
    material = _make_material(contract, f"contracts/finalized/{contract.id}/a.pdf")
    with override_settings(MEDIA_ROOT=str(media)):
        response = _call_preview(superuser, contract, material)
    assert response.status_code == 200
    assert response.content == PDF_BYTES
    assert response["Content-Type"] == "application/pdf"


@pytest.mark.django_db
def test_delete_skips_file_outside_contract_dir(contract: Contract, superuser: Lawyer, tmp_path: Any) -> None:
    """file_path 指向合同归档目录外 → 物理文件保留、记录照常删除（不误删任意文件）。"""
    media = tmp_path / "media"
    outside = media / "elsewhere" / "victim.txt"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_bytes(b"victim content")
    material = _make_material(contract, str(outside))  # 绝对路径直存（历史脏数据形态）
    with override_settings(MEDIA_ROOT=str(media)):
        response = _call_delete(superuser, contract, material)

    assert response.status_code == 200
    assert outside.exists()  # 越界路径未被 unlink
    assert outside.read_bytes() == b"victim content"
    assert not FinalizedMaterial.objects.filter(pk=material.pk).exists()


@pytest.mark.django_db
def test_delete_removes_file_inside_contract_dir(contract: Contract, superuser: Lawyer, tmp_path: Any) -> None:
    media = tmp_path / "media"
    own = media / "contracts" / "finalized" / str(contract.id) / "a.pdf"
    own.parent.mkdir(parents=True, exist_ok=True)
    own.write_bytes(PDF_BYTES)
    material = _make_material(contract, f"contracts/finalized/{contract.id}/a.pdf")
    with override_settings(MEDIA_ROOT=str(media)):
        response = _call_delete(superuser, contract, material)

    assert response.status_code == 200
    assert not own.exists()
    assert not FinalizedMaterial.objects.filter(pk=material.pk).exists()
