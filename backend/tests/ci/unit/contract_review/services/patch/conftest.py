"""写补丁链路（草案区 + 单点应用）的共用夹具。

绑定文件夹的 ACL 是真的：`ContractFolderBinding` + `ContractAssignment` 各建一行，
文件落在 `tmp_path` 里。不打桩 `resolve_file`——这条链路最容易出的事故就是"绕过
ACL 直接拿路径"，用假 browse 测出来的绿是假的。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from apps.contracts.models import ContractAssignment, ContractFolderBinding
from apps.testing.factories import ContractFactory, LawyerFactory
from tests.ci.unit.contract_review.services.patch.docx_fixtures import make_docx


@pytest.fixture
def bound(tmp_path: Path) -> Any:
    """已绑定临时目录的合同 + 有 ACL 访问权的律师 + 一份真实 docx。"""

    def _make(paragraphs: list[str] | None = None) -> tuple[Any, Any, Path]:
        src_dir = tmp_path / "1-合同"
        src_dir.mkdir(parents=True, exist_ok=True)
        file_path = src_dir / "a.docx"
        file_path.write_bytes(make_docx(paragraphs))
        lawyer = LawyerFactory()
        contract = ContractFactory()
        ContractAssignment.objects.create(contract=contract, lawyer=lawyer)
        ContractFolderBinding.objects.create(contract=contract, folder_path=str(tmp_path))
        return lawyer, contract, file_path

    return _make
