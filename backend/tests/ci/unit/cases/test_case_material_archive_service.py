"""归档落盘服务：目录定位、子目录映射、不覆盖命名、副本分离、核对说明。

假案件目录与命名沿用 `test_scan_archive_naming.py` 的脱敏案例（张某诉某公司买卖合同纠纷一案）。
落盘用 tmp_path 真实目录；「未绑定 / 无权限」走真实 `CaseFolderBinding` 行验证，
绑定服务注入与越界这类纯编排分支用 MagicMock 注入，不碰库。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from apps.cases.models import CaseFolderBinding
from apps.cases.services.material.case_material_archive_service import ArchiveItem, CaseMaterialArchiveService
from apps.cases.services.material.scan_archive_naming import DUPLICATE_SUBDIR
from apps.core.exceptions import ValidationException
from apps.testing.factories import CaseFactory

CASE_NAME = "张某诉某公司买卖合同纠纷一案"
DATE = "20261106"
LITIGATION_SUBDIRS = ["1-起诉状", "2-当事人身份证明", "4-证据目录", "9-其他立案材料"]
#: 单份 PDF 字节（内容不重要，只验证落盘字节与入参一致）
PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


@pytest.fixture
def svc() -> CaseMaterialArchiveService:
    return CaseMaterialArchiveService()


def _litigation_dir(tmp_path: Path, subdirs: list[str] | None = None) -> Path:
    """假案件目录：`<tmp>/3-一审/1-立案材料/{子目录…}`（不多建任何层级）。"""
    material = tmp_path / "3-一审" / "1-立案材料"
    material.mkdir(parents=True)
    for name in LITIGATION_SUBDIRS if subdirs is None else subdirs:
        (material / name).mkdir()
    return material


def _bound_case(tmp_path: Path, subdirs: list[str] | None = None) -> tuple[Path, int]:
    """建假案件目录 + 真实绑定行，返回（立案材料目录, case_id）。"""
    material = _litigation_dir(tmp_path, subdirs)
    case = CaseFactory(name=CASE_NAME)
    CaseFolderBinding.objects.create(case=case, folder_path=str(tmp_path))
    return material, case.id


def _complaint(content: bytes = PDF, **kwargs) -> ArchiveItem:
    return ArchiveItem(doc_type="传统起诉状", material_type="complaint", content=content, **kwargs)


@pytest.mark.django_db
class TestArchivePlacement:
    def test_follows_existing_draft_ordinal_and_version(self, svc, tmp_path):
        """同目录已有 V4 草稿 → 扫描件沿用 1- 与 V4，不是 V1/V5。"""
        material, case_id = _bound_case(tmp_path)
        complaint_dir = material / "1-起诉状"
        (complaint_dir / f"1-传统起诉状（{CASE_NAME}）V4_20261106.docx").write_bytes(b"draft")

        result = svc.archive(case_id=case_id, items=[_complaint()], date=DATE, perm_open_access=True)

        assert len(result.written) == 1
        archived = result.written[0]
        assert archived.filename == f"1-传统起诉状（{CASE_NAME}）V4_20261106.pdf"
        assert archived.subdir == "3-一审/1-立案材料/1-起诉状"
        assert archived.is_duplicate is False
        assert archived.absolute_path == str(complaint_dir / archived.filename)
        assert Path(archived.absolute_path).read_bytes() == PDF
        assert result.root == str(tmp_path.resolve())
        assert (result.skipped, result.duplicates) == ([], [])

    def test_three_identical_copies_split_primary_and_duplicates(self, svc, tmp_path):
        """一案三份：组内第一份进主目录，第 2、3 份进「其余副本」并带（第N份）。"""
        material, case_id = _bound_case(tmp_path)
        complaint_dir = material / "1-起诉状"
        # 三份打印件的签章位置/噪点不同，平均差在阈值内 → 应判为同一份文书的重复件
        items = [
            _complaint(page_signatures=[[0.30, 0.70, 0.30, 0.70]]),
            _complaint(page_signatures=[[0.30, 0.70, 0.30, 0.71]]),
            _complaint(page_signatures=[[0.29, 0.70, 0.30, 0.70]]),
        ]

        result = svc.archive(case_id=case_id, items=items, date=DATE, perm_open_access=True)

        base = f"1-传统起诉状（{CASE_NAME}）V1_20261106"
        assert [f.filename for f in result.written] == [f"{base}.pdf", f"{base}（第2份）.pdf", f"{base}（第3份）.pdf"]
        assert [f.is_duplicate for f in result.written] == [False, True, True]
        assert result.written[0].subdir == "3-一审/1-立案材料/1-起诉状"
        assert result.written[1].subdir == f"3-一审/1-立案材料/1-起诉状/{DUPLICATE_SUBDIR}"
        assert (complaint_dir / f"{base}.pdf").read_bytes() == PDF
        assert (complaint_dir / DUPLICATE_SUBDIR / f"{base}（第3份）.pdf").read_bytes() == PDF
        assert result.duplicates == [["传统起诉状", "传统起诉状", "传统起诉状"]]

    def test_write_duplicates_false_keeps_primary_and_still_reports(self, svc, tmp_path):
        """副本不落盘，但仍上报在 duplicates 里，且不创建副本目录。"""
        material, case_id = _bound_case(tmp_path)
        complaint_dir = material / "1-起诉状"
        items = [
            _complaint(page_signatures=[[0.30, 0.70, 0.30, 0.70]]),
            _complaint(page_signatures=[[0.30, 0.70, 0.30, 0.71]]),
        ]

        result = svc.archive(
            case_id=case_id,
            items=items,
            date=DATE,
            perm_open_access=True,
            write_duplicates=False,
        )

        assert [f.is_duplicate for f in result.written] == [False]
        assert result.duplicates == [["传统起诉状", "传统起诉状"]]
        assert result.skipped == []
        assert not (complaint_dir / DUPLICATE_SUBDIR).exists()

    def test_items_without_signature_are_all_primary(self, svc, tmp_path):
        """没有页指纹一律当正本：第二份不覆盖第一份，只追加 _2。"""
        material, case_id = _bound_case(tmp_path)
        complaint_dir = material / "1-起诉状"

        result = svc.archive(case_id=case_id, items=[_complaint(), _complaint()], date=DATE, perm_open_access=True)

        base = f"1-传统起诉状（{CASE_NAME}）V1_20261106"
        assert [f.filename for f in result.written] == [f"{base}.pdf", f"{base}_2.pdf"]
        assert [f.is_duplicate for f in result.written] == [False, False]
        assert result.duplicates == []
        assert not (complaint_dir / DUPLICATE_SUBDIR).exists()

    def test_existing_target_file_is_not_overwritten(self, svc, tmp_path):
        """目标文件已存在 → 追加 _2，既有文件一个字节都不动。"""
        material, case_id = _bound_case(tmp_path)
        complaint_dir = material / "1-起诉状"
        existing = complaint_dir / f"1-传统起诉状（{CASE_NAME}）V1_20261106.pdf"
        existing.write_bytes(b"kept")

        result = svc.archive(case_id=case_id, items=[_complaint()], date=DATE, perm_open_access=True)

        assert result.written[0].filename == f"1-传统起诉状（{CASE_NAME}）V1_20261106_2.pdf"
        assert existing.read_bytes() == b"kept"
        assert (complaint_dir / result.written[0].filename).read_bytes() == PDF

    def test_item_subdir_wins_over_material_type(self, svc, tmp_path):
        _, case_id = _bound_case(tmp_path)
        item = ArchiveItem(doc_type="证据清单", material_type="complaint", content=PDF, subdir="4-证据目录")

        result = svc.archive(case_id=case_id, items=[item], date=DATE, perm_open_access=True)

        assert result.written[0].subdir == "3-一审/1-立案材料/4-证据目录"
        assert result.written[0].filename == f"1-证据清单（{CASE_NAME}）V1_20261106.pdf"

    def test_unknown_material_type_falls_back_to_other_materials(self, svc, tmp_path):
        _, case_id = _bound_case(tmp_path)
        item = ArchiveItem(doc_type="情况说明", material_type="mystery_doc", content=PDF)

        result = svc.archive(case_id=case_id, items=[item], date=DATE, perm_open_access=True)

        assert result.written[0].subdir == "3-一审/1-立案材料/9-其他立案材料"

    def test_without_matching_subdir_is_skipped(self, svc, tmp_path):
        """子目录都在但一个都不匹配（也没有「其他」）→ 记 skipped，不硬塞进别处。"""
        material, case_id = _bound_case(tmp_path, subdirs=["1-起诉状"])
        item = ArchiveItem(doc_type="财产保全申请书", material_type="mystery_doc", content=PDF)

        result = svc.archive(case_id=case_id, items=[item], date=DATE, perm_open_access=True)

        assert result.written == []
        assert result.skipped[0]["doc_type"] == "财产保全申请书"
        assert "未找到匹配的子目录" in result.skipped[0]["reason"]
        assert list(material.rglob("*.pdf")) == []

    def test_flat_material_dir_gets_the_file_directly(self, svc, tmp_path):
        """立案材料目录下没有子目录（模板未建层级）→ 直接落在它本身。"""
        material, case_id = _bound_case(tmp_path, subdirs=[])

        result = svc.archive(case_id=case_id, items=[_complaint()], date=DATE, perm_open_access=True)

        assert result.written[0].subdir == "3-一审/1-立案材料"
        assert (material / result.written[0].filename).read_bytes() == PDF

    def test_empty_content_is_skipped(self, svc, tmp_path):
        material, case_id = _bound_case(tmp_path)

        result = svc.archive(case_id=case_id, items=[_complaint(content=b"")], date=DATE, perm_open_access=True)

        assert result.written == []
        assert result.skipped == [{"doc_type": "传统起诉状", "reason": "内容为空"}]
        assert list(material.rglob("*.pdf")) == []

    def test_subdir_escaping_the_material_dir_is_skipped(self, svc, tmp_path):
        material, case_id = _bound_case(tmp_path)
        item = ArchiveItem(doc_type="传统起诉状", material_type="complaint", content=PDF, subdir="../逃逸")

        result = svc.archive(case_id=case_id, items=[item], date=DATE, perm_open_access=True)

        assert result.written == []
        assert "子目录越界" in result.skipped[0]["reason"]
        assert not (material.parent / "逃逸").exists()

    def test_shallow_litigation_dir_wins(self, svc, tmp_path):
        """绑定根下另一条更深的分支也叫「立案材料」时，取层级更浅的那个。"""
        deeper = tmp_path / "9-历史" / "2026" / "立案材料"
        deeper.mkdir(parents=True)
        material, case_id = _bound_case(tmp_path)

        result = svc.archive(case_id=case_id, items=[_complaint()], date=DATE, perm_open_access=True)

        assert result.written[0].subdir == "3-一审/1-立案材料/1-起诉状"
        assert (material / "1-起诉状" / result.written[0].filename).exists()
        assert list(deeper.rglob("*.pdf")) == []

    def test_unbound_case_raises_validation_error(self, svc, tmp_path):
        case = CaseFactory(name=CASE_NAME)

        with pytest.raises(ValidationException, match="案件未绑定文件夹"):
            svc.archive(case_id=case.id, items=[_complaint()], date=DATE, perm_open_access=True)

    def test_missing_folder_raises_instead_of_creating_tree(self, svc, tmp_path):
        """绑定目录已被删除 → 报错，不替用户把整棵案件目录树建出来。"""
        case = CaseFactory(name=CASE_NAME)
        gone = tmp_path / "已删除的案件目录"
        CaseFolderBinding.objects.create(case=case, folder_path=str(gone))

        with pytest.raises(ValidationException, match="案件文件夹不可访问"):
            svc.archive(case_id=case.id, items=[_complaint()], date=DATE, perm_open_access=True)

        assert not gone.exists()


@pytest.mark.django_db
class TestNotice:
    def test_notice_lists_written_files(self, svc, tmp_path):
        material, case_id = _bound_case(tmp_path)

        result = svc.archive(case_id=case_id, items=[_complaint()], date=DATE, perm_open_access=True)

        notice = material / "00-拆分与核对说明.md"
        assert result.notice_path == str(notice)
        text = notice.read_text(encoding="utf-8")
        assert "本文件由系统自动生成" in text
        assert "| 序号 | 文书名 | 目标子目录 | 文件名 | 字节数 | 是否副本 |" in text
        assert (
            f"| 1 | 传统起诉状 | 3-一审/1-立案材料/1-起诉状 | {result.written[0].filename} | {len(PDF)} | 否 |" in text
        )

    def test_notice_lists_skipped_items(self, svc, tmp_path):
        material, case_id = _bound_case(tmp_path, subdirs=["1-起诉状"])
        item = ArchiveItem(doc_type="财产保全申请书", material_type="mystery_doc", content=PDF)

        svc.archive(case_id=case_id, items=[item], date=DATE, perm_open_access=True)

        text = (material / "00-拆分与核对说明.md").read_text(encoding="utf-8")
        assert "## 未归档条目" in text
        assert "财产保全申请书" in text

    def test_write_notice_false_writes_nothing(self, svc, tmp_path):
        material, case_id = _bound_case(tmp_path)

        result = svc.archive(
            case_id=case_id, items=[_complaint()], date=DATE, perm_open_access=True, write_notice=False
        )

        assert result.notice_path is None
        assert not (material / "00-拆分与核对说明.md").exists()


class TestBindingServiceInjection:
    def test_missing_binding_raises_and_access_args_are_forwarded(self):
        """绑定服务返回 None → 抛 ValidationException；权限口径原样交给绑定服务。"""
        binding_service = MagicMock()
        binding_service.get_binding.return_value = None
        svc = CaseMaterialArchiveService(binding_service=binding_service)

        with pytest.raises(ValidationException, match="案件未绑定文件夹"):
            svc.archive(case_id=7, items=[_complaint()], date=DATE, perm_open_access=True)

        binding_service.get_binding.assert_called_once_with(7, user=None, org_access=None, perm_open_access=True)
