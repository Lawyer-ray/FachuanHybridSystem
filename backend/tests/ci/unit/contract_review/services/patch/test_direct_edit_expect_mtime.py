"""`/direct-edit/apply` 的 `expect_mtime` 贯通（乐观锁）。

**为什么要从 HTTP 层测**：服务层 `DirectEditService.apply` 早就支持
`expect_mtime` 并会下传给 `BoundFolderBrowseService.save_file_content`，但 API
层此前**没把它接过来**，于是 `bound_folder_browse.py` 里那段
`if expect_mtime is not None:` 整段跳过——两人同开同一份 docx 时，后落笔的一
方静默覆盖前一个人的修订，界面上没有任何异常。这种「参数支持了但没接线」的
缺陷只能靠端到端断言，单测服务层是测不出来的。

三条口径：

1. 传入的 mtime 与磁盘不一致 → **409**（不是 200 + `applied=false`：调用方
   需要能区分「没找到选区」与「文件被别人改过」）；
2. 冲突时文件字节**一个都没变**（409 之前不许已经落盘）；
3. mtime 一致 → 正常落盘（回归：别把乐观锁做成恒 409）。

`expect_mtime` 走 query 参数，与同仓库 `contracts/{id}/folder-save` 同口径。
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from django.test import Client as DjangoTestClient
from docx import Document

from apps.contracts.models import ContractAssignment, ContractFolderBinding
from apps.testing.factories import ContractFactory, LawyerFactory

SUBPATH = "1-合同/a.docx"
SELECTION = "甲方应于三十日内支付货款。"
SUGGESTED = "甲方应于十五日内支付货款。"


def _docx_bytes() -> bytes:
    doc = Document()
    doc.add_paragraph(SELECTION)
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


@pytest.fixture
def client() -> DjangoTestClient:
    return DjangoTestClient()


@pytest.fixture
def bound(tmp_path: Path) -> Any:
    """一份已绑定临时目录的合同 + 有 ACL 访问权的律师 + 真实 docx。"""

    def _make() -> tuple[Any, Any, Path]:
        src_dir = tmp_path / "1-合同"
        src_dir.mkdir(parents=True, exist_ok=True)
        file_path = src_dir / "a.docx"
        file_path.write_bytes(_docx_bytes())
        lawyer = LawyerFactory()
        contract = ContractFactory()
        ContractAssignment.objects.create(contract=contract, lawyer=lawyer)
        ContractFolderBinding.objects.create(contract=contract, folder_path=str(tmp_path))
        return lawyer, contract, file_path

    return _make


def _apply(client: DjangoTestClient, contract_id: int, *, expect_mtime: float | None) -> Any:
    url = f"/api/v1/contract-review/direct-edit/apply?expect_mtime={expect_mtime}" if expect_mtime is not None else (
        "/api/v1/contract-review/direct-edit/apply"
    )
    return client.post(
        url,
        data={"contract_id": contract_id, "subpath": SUBPATH, "selection": SELECTION, "suggested": SUGGESTED},
        content_type="application/json",
    )


class TestExpectMtime:
    @pytest.mark.django_db(transaction=True)
    def test_mismatched_mtime_returns_409_and_leaves_file_untouched(
        self, client: DjangoTestClient, bound: Any
    ) -> None:
        lawyer, contract, file_path = bound()
        client.force_login(lawyer)
        before = file_path.read_bytes()
        stale = file_path.stat().st_mtime - 3600  # 别人改过：磁盘 mtime 已经往前走了

        resp = _apply(client, contract.id, expect_mtime=stale)

        assert resp.status_code == 409, resp.content
        body = resp.json()
        assert body["code"] == "FILE_MODIFIED"
        # 冲突不是「已应用但没生效」：字节必须原样（否则等于静默覆盖后再报错）
        assert file_path.read_bytes() == before

    @pytest.mark.django_db(transaction=True)
    def test_matching_mtime_applies(self, client: DjangoTestClient, bound: Any) -> None:
        lawyer, contract, file_path = bound()
        client.force_login(lawyer)
        current = file_path.stat().st_mtime

        resp = _apply(client, contract.id, expect_mtime=current)

        assert resp.status_code == 200, resp.content
        assert resp.json()["applied"] is True
        # 落盘后能读到修订插入的文本（visible_text 口径：含 w:ins、不含 w:del）
        from apps.contract_review.services.formatting.docx_revision_tool import visible_text

        doc = Document(BytesIO(file_path.read_bytes()))
        assert SUGGESTED in visible_text(doc.paragraphs[0])
