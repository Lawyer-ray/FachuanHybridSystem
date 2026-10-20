"""ContractFolderBrowseService 单测：合同 ACL、绑定解析与管理操作共享逻辑。"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.contracts.models import ContractFolderBinding
from apps.contracts.services.contract.integrations.folder_browse_service import ContractFolderBrowseService
from apps.core.exceptions import ForbiddenError, NotFoundError, PermissionDenied
from apps.testing.factories import ContractFactory


@pytest.fixture
def svc() -> ContractFolderBrowseService:
    return ContractFolderBrowseService()


@pytest.mark.django_db
class TestContractFolderBrowse:
    def _bind(self, tmp_path: Path):
        contract = ContractFactory()
        ContractFolderBinding.objects.create(contract=contract, folder_path=str(tmp_path))
        return contract

    def test_no_binding_404(self, svc, tmp_path):
        contract = ContractFactory()
        with pytest.raises(NotFoundError, match="未绑定文件夹"):
            svc.list_entries(owner_id=contract.id, perm_open_access=True)

    def test_acl_fail_closed_without_access(self, svc, tmp_path):
        contract = self._bind(tmp_path)
        with pytest.raises((PermissionDenied, ForbiddenError, NotFoundError)):
            svc.list_entries(owner_id=contract.id)

    def test_list_and_manage_roundtrip(self, svc, tmp_path):
        contract = self._bind(tmp_path)

        svc.mkdir(owner_id=contract.id, subpath="", name="1-委托材料", perm_open_access=True)
        saved = svc.save_uploads(
            owner_id=contract.id,
            subpath="1-委托材料",
            files=[SimpleUploadedFile("合同.pdf", b"%PDF-1.4")],
            perm_open_access=True,
        )
        assert saved["saved"][0]["subpath"] == "1-委托材料/合同.pdf"

        out = svc.list_entries(owner_id=contract.id, subpath="1-委托材料", perm_open_access=True)
        assert [f["name"] for f in out["files"]] == ["合同.pdf"]

        svc.rename(owner_id=contract.id, subpath="1-委托材料/合同.pdf", new_name="委托合同.pdf", perm_open_access=True)
        renamed = svc.list_entries(owner_id=contract.id, subpath="1-委托材料", perm_open_access=True)
        assert [f["name"] for f in renamed["files"]] == ["委托合同.pdf"]

    def test_resolve_file_for_preview(self, svc, tmp_path):
        (tmp_path / "说明.txt").write_text("hi")
        contract = self._bind(tmp_path)
        resolved = svc.resolve_file(owner_id=contract.id, subpath="说明.txt", perm_open_access=True)
        assert resolved == (tmp_path / "说明.txt").resolve()
