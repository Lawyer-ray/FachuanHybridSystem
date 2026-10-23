"""folder_refs 服务测试：引用创建 / 读取 / 渲染、路径逃逸、post_delete 安全。

ACL 不在这里重测（ContractAccessPolicy 由 contracts 侧覆盖），测试把
``_require_access`` 置为 no-op 或按需抛错，专注本服务的编排与安全语义。
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest

from apps.agent.models import AgentSession
from apps.agent.services import folder_refs
from apps.agent.services.folder_refs import create_folder_ref, read_folder_file_content, render_folder_file_pages
from apps.contracts.models import Contract, ContractFolderBinding
from apps.core.exceptions import NotFoundError, PermissionDenied, ValidationException
from apps.organization.models import LawFirm, Lawyer


@pytest.fixture()
def lawyer(db: Any) -> Lawyer:
    firm = LawFirm.objects.create(name="folder-ref-测试律所")
    # pragma: allowlist secret —— 与 integration 测试同款的哑密码
    return Lawyer.objects.create_user(
        username="folderref-lawyer",  # pragma: allowlist secret
        password="x-test-12345678",  # pragma: allowlist secret
        law_firm=firm,
    )


@pytest.fixture()
def bound_contract(db: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, lawyer: Lawyer) -> tuple[Contract, Path]:
    """有本地绑定 + 已放行 ACL 的合同；返回 (合同, 绑定根)。"""
    from apps.contracts.services.contract.integrations.folder_browse_service import ContractFolderBrowseService

    monkeypatch.setattr(ContractFolderBrowseService, "_require_access", lambda self, **kw: None)
    root = tmp_path / "bound"
    (root / "1-一审" / "2-立案材料").mkdir(parents=True)
    (root / "1-一审" / "2-立案材料" / "起诉状.txt").write_text("一审起诉状正文", encoding="utf-8")
    contract = Contract.objects.create(name="folder-ref-测试合同", case_type="civil")
    ContractFolderBinding.objects.create(contract=contract, folder_path=str(root))
    return contract, root


def _pdf_bytes() -> bytes:
    import pymupdf as fitz

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 80), "folder-ref 测试页", fontsize=11, fontname="china-s")
    data = doc.tobytes()
    doc.close()
    return data


class TestCreateFolderRef:
    def test_escape_rejected(self, bound_contract: tuple[Contract, Path], lawyer: Lawyer) -> None:
        contract, _ = bound_contract
        with pytest.raises(ValidationException):
            create_folder_ref(
                session=AgentSession.objects.create(user=lawyer),
                user_id=lawyer.id,
                user=lawyer,
                org_access=None,
                perm_open_access=False,
                owner_kind="contract",
                owner_id=contract.id,
                subpath="../../etc/passwd",
            )

    def test_absolute_path_rejected(self, bound_contract: tuple[Contract, Path], lawyer: Lawyer) -> None:
        contract, _ = bound_contract
        with pytest.raises(ValidationException):
            create_folder_ref(
                session=AgentSession.objects.create(user=lawyer),
                user_id=lawyer.id,
                user=lawyer,
                org_access=None,
                perm_open_access=False,
                owner_kind="contract",
                owner_id=contract.id,
                subpath="/etc/passwd",
            )

    def test_no_binding_raises_not_found(self, db: Any, lawyer: Lawyer, monkeypatch: pytest.MonkeyPatch) -> None:
        from apps.contracts.services.contract.integrations.folder_browse_service import ContractFolderBrowseService

        monkeypatch.setattr(ContractFolderBrowseService, "_require_access", lambda self, **kw: None)
        contract = Contract.objects.create(name="无绑定合同", case_type="civil")
        with pytest.raises(NotFoundError):
            create_folder_ref(
                session=AgentSession.objects.create(user=lawyer),
                user_id=lawyer.id,
                user=lawyer,
                org_access=None,
                perm_open_access=False,
                owner_kind="contract",
                owner_id=contract.id,
                subpath="任何.txt",
            )

    def test_acl_denied_propagates(
        self, bound_contract: tuple[Contract, Path], lawyer: Lawyer, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        contract, _ = bound_contract
        from apps.contracts.services.contract.integrations.folder_browse_service import ContractFolderBrowseService

        def _deny(self: Any, **kw: Any) -> None:
            raise PermissionDenied(message="无权访问该合同")

        monkeypatch.setattr(ContractFolderBrowseService, "_require_access", _deny)
        with pytest.raises(PermissionDenied):
            create_folder_ref(
                session=AgentSession.objects.create(user=lawyer),
                user_id=lawyer.id,
                user=lawyer,
                org_access=None,
                perm_open_access=False,
                owner_kind="contract",
                owner_id=contract.id,
                subpath="1-一审/2-立案材料/起诉状.txt",
            )

    def test_success_records_metadata_without_copy(self, bound_contract: tuple[Contract, Path], lawyer: Lawyer) -> None:
        contract, root = bound_contract
        session = AgentSession.objects.create(user=lawyer)
        ref = create_folder_ref(
            session=session,
            user_id=lawyer.id,
            user=lawyer,
            org_access=None,
            perm_open_access=False,
            owner_kind="contract",
            owner_id=contract.id,
            subpath="1-一审/2-立案材料/起诉状.txt",
        )
        assert ref.filename == "起诉状.txt"
        assert ref.storage_path == ""  # 引用型不落 media——post_delete 物理清理的开关
        assert ref.ref_contract_id == contract.id
        assert ref.ref_subpath == "1-一审/2-立案材料/起诉状.txt"
        assert ref.size > 0
        assert ref.mime == "text/plain"

    def test_delete_ref_keeps_source_file(self, bound_contract: tuple[Contract, Path], lawyer: Lawyer) -> None:
        """关键安全断言：删除引用（或级联删会话）绝不物理删除绑定文件夹里的原文件。"""
        contract, root = bound_contract
        session = AgentSession.objects.create(user=lawyer)
        ref = create_folder_ref(
            session=session,
            user_id=lawyer.id,
            user=lawyer,
            org_access=None,
            perm_open_access=False,
            owner_kind="contract",
            owner_id=contract.id,
            subpath="1-一审/2-立案材料/起诉状.txt",
        )
        source = root / "1-一审" / "2-立案材料" / "起诉状.txt"
        ref.delete()
        session.delete()
        assert source.exists()
        assert source.read_text(encoding="utf-8") == "一审起诉状正文"


class TestReadAndRender:
    def test_content_returns_base64_of_source(self, bound_contract: tuple[Contract, Path], lawyer: Lawyer) -> None:
        contract, _ = bound_contract
        payload = read_folder_file_content(
            owner_kind="contract",
            owner_id=contract.id,
            subpath="1-一审/2-立案材料/起诉状.txt",
            user=lawyer,
            org_access=None,
            perm_open_access=False,
        )
        assert payload["filename"] == "起诉状.txt"
        assert base64.b64decode(payload["content_base64"]).decode("utf-8") == "一审起诉状正文"
        assert payload["attachment_id"] == f"folder:{contract.id}/1-一审/2-立案材料/起诉状.txt"

    def test_missing_file_raises_not_found(self, bound_contract: tuple[Contract, Path], lawyer: Lawyer) -> None:
        contract, _ = bound_contract
        with pytest.raises(NotFoundError):
            read_folder_file_content(
                owner_kind="contract",
                owner_id=contract.id,
                subpath="1-一审/2-立案材料/不存在.txt",
                user=lawyer,
                org_access=None,
                perm_open_access=False,
            )

    def test_render_pdf_pages_succeeds(self, bound_contract: tuple[Contract, Path], lawyer: Lawyer) -> None:
        contract, root = bound_contract
        (root / "1-一审" / "2-立案材料" / "判决书.pdf").write_bytes(_pdf_bytes())
        outcome = render_folder_file_pages(
            owner_kind="contract",
            owner_id=contract.id,
            subpath="1-一审/2-立案材料/判决书.pdf",
            user=lawyer,
            org_access=None,
            perm_open_access=False,
            pages="1",
            dpi=72,
            fmt="png",
            max_pages=1,
            user_id=lawyer.id,
        )
        assert not outcome.error, outcome.detail
        assert outcome.total_pages == 1
        assert len(outcome.pages) == 1
        assert outcome.pages[0].image_bytes  # 真出了图

    def test_oversize_file_rejected_on_content(
        self, bound_contract: tuple[Contract, Path], lawyer: Lawyer, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        contract, root = bound_contract
        big = root / "1-一审" / "2-立案材料" / "大文件.bin"
        big.write_bytes(b"x" * 16)
        monkeypatch.setattr(folder_refs, "MAX_FOLDER_FILE_BYTES", 10)
        with pytest.raises(ValidationException) as excinfo:
            read_folder_file_content(
                owner_kind="contract",
                owner_id=contract.id,
                subpath="1-一审/2-立案材料/大文件.bin",
                user=lawyer,
                org_access=None,
                perm_open_access=False,
            )
        assert "读取上限" in str(excinfo.value)

    def test_oversize_file_reports_too_large_on_render(
        self, bound_contract: tuple[Contract, Path], lawyer: Lawyer, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        contract, root = bound_contract
        big = root / "1-一审" / "2-立案材料" / "大文件.bin"
        big.write_bytes(b"x" * 16)
        monkeypatch.setattr(folder_refs, "MAX_FOLDER_FILE_BYTES", 10)
        outcome = render_folder_file_pages(
            owner_kind="contract",
            owner_id=contract.id,
            subpath="1-一审/2-立案材料/大文件.bin",
            user=lawyer,
            org_access=None,
            perm_open_access=False,
        )
        assert outcome.error == "too_large"
        assert "读取上限" in (outcome.detail or "")

    def test_render_unsupported_mime_reports_error(self, bound_contract: tuple[Contract, Path], lawyer: Lawyer) -> None:
        contract, root = bound_contract
        (root / "1-一审" / "2-立案材料" / "起诉状.txt").write_text("纯文本没有页图形态", encoding="utf-8")
        outcome = render_folder_file_pages(
            owner_kind="contract",
            owner_id=contract.id,
            subpath="1-一审/2-立案材料/起诉状.txt",
            user=lawyer,
            org_access=None,
            perm_open_access=False,
        )
        assert outcome.error == "unsupported_mime"
        assert outcome.pages == []

class TestCaseOwnerKind:
    def test_case_ref_reads_case_binding_folder(self, db, tmp_path, monkeypatch, lawyer) -> None:
        """案件引用走 CaseFolderBrowseService：读案件绑定文件夹的原文件。"""
        from apps.cases.models import Case
        from apps.cases.services.material.case_folder_browse_service import CaseFolderBrowseService

        monkeypatch.setattr(CaseFolderBrowseService, "_require_access", lambda self, **kw: None)
        root = tmp_path / "case-bound"
        (root / "证据").mkdir(parents=True)
        (root / "证据" / "微信记录.txt").write_text("案件证据正文", encoding="utf-8")
        from apps.cases.models import CaseFolderBinding

        case = Case.objects.create(is_filed=True)
        CaseFolderBinding.objects.create(case=case, folder_path=str(root))
        session = AgentSession.objects.create(user=lawyer)
        ref = create_folder_ref(
            session=session,
            user_id=lawyer.id,
            user=lawyer,
            org_access=None,
            perm_open_access=False,
            owner_kind="case",
            owner_id=case.id,
            subpath="证据/微信记录.txt",
        )
        assert ref.ref_owner_kind == "case"
        assert ref.filename == "微信记录.txt"
        payload = read_folder_file_content(
            owner_kind="case",
            owner_id=case.id,
            subpath="证据/微信记录.txt",
            user=lawyer,
            org_access=None,
            perm_open_access=False,
        )
        assert base64.b64decode(payload["content_base64"]).decode("utf-8") == "案件证据正文"
        assert payload["attachment_id"] == f"folder:case:{case.id}/证据/微信记录.txt"

    def test_unknown_kind_rejected(self, db, lawyer) -> None:
        with pytest.raises(ValidationException):
            create_folder_ref(
                session=AgentSession.objects.create(user=lawyer),
                user_id=lawyer.id,
                user=lawyer,
                org_access=None,
                perm_open_access=False,
                owner_kind="client",
                owner_id=1,
                subpath="x.txt",
            )
