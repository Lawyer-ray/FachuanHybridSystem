"""补充覆盖测试: contracts/services/contract/integrations/_candidate_post_processor.py

覆盖: post_process_candidates 的跳过规则 / 归档匹配 / 云存储相对路径 /
docx 收集（本地与云存储）、_mark_already_imported 哈希比对分支。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from apps.contracts.models.contract import Contract
from apps.contracts.models.finalized_material import FinalizedMaterial, MaterialCategory

POST_PROC_MOD = "apps.contracts.services.contract.integrations._candidate_post_processor"


def _make_processor() -> Any:
    from apps.contracts.services.contract.integrations._candidate_post_processor import CandidatePostProcessor

    return CandidatePostProcessor(scan_service=MagicMock())


def _classify_result(
    *,
    code: str = "lt_6",
    name: str = "匹配项",
    category: str = "case_material",
    confidence: float = 0.9,
    reason: str = "关键词命中",
) -> dict[str, Any]:
    return {
        "archive_item_code": code,
        "archive_item_name": name,
        "category": category,
        "confidence": confidence,
        "reason": reason,
    }


# ── post_process_candidates: 分类与跳过分支 ────────────────────────


class TestPostProcessClassifyBranches:
    def test_skip_result_deselects_candidate(self):
        processor = _make_processor()
        candidates = [
            {"source_path": "/scan/内部文件.pdf", "filename": "内部文件.pdf", "suggested_category": "case_material"}
        ]
        with patch(f"{POST_PROC_MOD}.classify_archive_material") as mock_classify:
            mock_classify.return_value = {
                **_classify_result(category="skip", code=""),
                "reason": "跳过规则命中：内部文件",
            }
            result = processor.post_process_candidates(
                candidates=candidates,
                archive_category="litigation",
                scan_folder="/scan",
            )
        assert len(result) == 1
        assert result[0]["selected"] is False
        assert result[0]["skip_reason"] == "跳过规则命中：内部文件"

    def test_invoice_category_skips_archive_matching(self):
        processor = _make_processor()
        candidates = [{"source_path": "/scan/发票.pdf", "filename": "发票.pdf", "suggested_category": "invoice"}]
        with patch(f"{POST_PROC_MOD}.classify_archive_material") as mock_classify:
            mock_classify.return_value = _classify_result(code="lt_20", category="case_material")
            result = processor.post_process_candidates(
                candidates=candidates,
                archive_category="litigation",
                scan_folder="/scan",
            )
        # invoice 分支直接 append，不做归档编号回填
        mock_classify.assert_called_once()
        assert result[0]["suggested_category"] == "invoice"
        assert "archive_item_code" not in result[0]

    def test_archive_code_hit_backfills_fields(self):
        processor = _make_processor()
        candidates = [
            {"source_path": "/scan/起诉状.pdf", "filename": "起诉状.pdf", "suggested_category": "archive_document"}
        ]
        with patch(f"{POST_PROC_MOD}.classify_archive_material") as mock_classify:
            mock_classify.return_value = _classify_result(code="lt_6", name="起诉状", confidence=0.95)
            result = processor.post_process_candidates(
                candidates=candidates,
                archive_category="litigation",
                scan_folder="/scan",
            )
        assert result[0]["suggested_category"] == "case_material"
        assert result[0]["archive_item_code"] == "lt_6"
        assert result[0]["archive_item_name"] == "起诉状"
        assert result[0]["confidence"] == 0.95
        assert result[0]["reason"] == "关键词命中"
        assert result[0].get("selected") is not False

    def test_archive_code_miss_deselects(self):
        processor = _make_processor()
        candidates = [
            {"source_path": "/scan/未知文件.pdf", "filename": "未知文件.pdf", "suggested_category": "case_material"}
        ]
        with patch(f"{POST_PROC_MOD}.classify_archive_material") as mock_classify:
            mock_classify.return_value = _classify_result(code="", name="未匹配", reason="无关键词命中")
            result = processor.post_process_candidates(
                candidates=candidates,
                archive_category="litigation",
                scan_folder="/scan",
            )
        assert result[0]["suggested_category"] == "case_material"
        assert result[0]["archive_item_code"] == ""
        assert result[0]["archive_item_name"] == "未匹配"
        assert result[0]["selected"] is False
        assert result[0]["reason"] == "无关键词命中"

    def test_unclassified_category_passthrough(self):
        """模板/其他类别不走 classify，仅做保单/保函过滤。"""
        processor = _make_processor()
        candidates = [
            {"source_path": "/scan/合同.pdf", "filename": "合同.pdf", "suggested_category": "contract_original"}
        ]
        with patch(f"{POST_PROC_MOD}.classify_archive_material") as mock_classify:
            result = processor.post_process_candidates(
                candidates=candidates,
                archive_category="litigation",
                scan_folder="/scan",
            )
        mock_classify.assert_not_called()
        assert result[0]["suggested_category"] == "contract_original"

    def test_baohan_and_baodan_deselected(self):
        processor = _make_processor()
        candidates = [
            {"source_path": "/p/保单合同.pdf", "filename": "保单合同.pdf", "suggested_category": "contract_original"},
            {"source_path": "/p/保函.pdf", "filename": "保函.pdf", "suggested_category": "contract_original"},
            {"source_path": "/p/普通.pdf", "filename": "普通.pdf", "suggested_category": "contract_original"},
        ]
        result = processor.post_process_candidates(
            candidates=candidates,
            archive_category="litigation",
            scan_folder="/p",
        )
        assert result[0]["selected"] is False
        assert result[1]["selected"] is False
        assert result[2].get("selected") is not False


# ── post_process_candidates: case_material 相对路径 reason ─────────


class TestPostProcessRelativePathReason:
    def test_local_nested_folder_becomes_reason(self, tmp_path: Path):
        processor = _make_processor()
        sub = tmp_path / "02-立案"
        sub.mkdir()
        src = sub / "起诉状.pdf"
        src.write_bytes(b"%PDF")
        candidates = [
            {
                "source_path": str(src),
                "filename": "起诉状.pdf",
                "suggested_category": "supervision_card",
            }
        ]
        result = processor.post_process_candidates(
            candidates=candidates,
            archive_category="litigation",
            scan_folder=str(tmp_path),
        )
        # supervision_card 类别未被 classify 分支处理，但也不是 case_material → reason 不设置
        assert "reason" not in result[0]

        candidates2 = [
            {
                "source_path": str(src),
                "filename": "起诉状.pdf",
                "suggested_category": "case_material",
                "archive_item_code": "lt_6",
            }
        ]
        result2 = processor.post_process_candidates(
            candidates=candidates2,
            archive_category="litigation",
            scan_folder=str(tmp_path),
        )
        assert result2[0]["reason"] == "02-立案"

    def test_local_root_level_file_no_reason(self, tmp_path: Path):
        processor = _make_processor()
        src = tmp_path / "材料.pdf"
        src.write_bytes(b"%PDF")
        candidates = [
            {
                "source_path": str(src),
                "filename": "材料.pdf",
                "suggested_category": "case_material",
                "archive_item_code": "nl_9",
            }
        ]
        with patch(f"{POST_PROC_MOD}.classify_archive_material") as mock_classify:
            mock_classify.return_value = _classify_result(code="nl_9", reason="关键词命中")
            result = processor.post_process_candidates(
                candidates=candidates,
                archive_category="non_litigation",
                scan_folder=str(tmp_path),
            )
        # 根目录下相对路径为空 → reason 保持为分类器给出的原因
        assert result[0]["reason"] == "关键词命中"

    def test_cloud_rel_path_and_fallback(self):
        processor = _make_processor()
        candidates = [
            {
                "source_path": "contracts/c1/03-证据/清单.pdf",
                "filename": "清单.pdf",
                "suggested_category": "case_material",
                "archive_item_code": "lt_10",
            },
            {
                "source_path": "other-root/清单2.pdf",
                "filename": "清单2.pdf",
                "suggested_category": "case_material",
                "archive_item_code": "lt_10",
            },
        ]
        provider = MagicMock()
        with patch.object(processor, "_collect_docx_files", return_value=[]):
            result = processor.post_process_candidates(
                candidates=candidates,
                archive_category="litigation",
                scan_folder="contracts/c1",
                storage_provider=provider,
            )
        # 云路径分支：reason 为完整相对路径（含文件名）
        assert result[0]["reason"] == "03-证据/清单.pdf"
        # 云路径不在扫描根下时退回完整路径
        assert result[1]["reason"] == "other-root/清单2.pdf"


# ── post_process_candidates: docx 追加与已导入标记 ─────────────────


class TestPostProcessDocxAppendAndMark:
    def test_non_litigation_appends_docx(self):
        processor = _make_processor()
        docx_candidates = [{"source_path": "/scan/常法修订版.docx", "is_docx": True}]
        with patch.object(processor, "_collect_docx_files", return_value=docx_candidates) as mock_collect:
            result = processor.post_process_candidates(
                candidates=[],
                archive_category="non_litigation",
                scan_folder="/scan",
            )
        mock_collect.assert_called_once_with("/scan", "non_litigation", storage_provider=None)
        assert result == docx_candidates

    def test_litigation_skips_docx_collection(self):
        processor = _make_processor()
        with patch.object(processor, "_collect_docx_files", return_value=[]) as mock_collect:
            result = processor.post_process_candidates(
                candidates=[],
                archive_category="litigation",
                scan_folder="/scan",
            )
        mock_collect.assert_not_called()
        assert result == []

    def test_contract_id_triggers_mark(self):
        processor = _make_processor()
        candidates = [{"source_path": "/scan/a.pdf", "filename": "a.pdf", "suggested_category": "invoice"}]
        with (
            patch.object(processor, "_collect_docx_files", return_value=[]),
            patch.object(processor, "_mark_already_imported") as mock_mark,
        ):
            result = processor.post_process_candidates(
                candidates=candidates,
                archive_category="litigation",
                scan_folder="/scan",
                contract_id=9,
            )
        mock_mark.assert_called_once()
        assert mock_mark.call_args.kwargs["contract_id"] == 9
        assert result == candidates

    def test_zero_contract_id_skips_mark(self):
        processor = _make_processor()
        with patch.object(processor, "_mark_already_imported") as mock_mark:
            processor.post_process_candidates(
                candidates=[],
                archive_category="litigation",
                scan_folder="/scan",
                contract_id=0,
            )
        mock_mark.assert_not_called()


# ── _collect_docx_files: 本地分支 ─────────────────────────────────


class TestCollectDocxFilesLocal:
    def test_not_non_litigation_returns_empty(self):
        processor = _make_processor()
        assert processor._collect_docx_files("/scan", "litigation") == []

    def test_missing_root_returns_empty(self, tmp_path: Path):
        processor = _make_processor()
        assert processor._collect_docx_files(str(tmp_path / "不存在"), "non_litigation") == []

    def test_with_provider_dispatches_to_cloud(self):
        processor = _make_processor()
        cloud_result = [{"source_path": "cloud/修订版.docx", "is_docx": True}]
        provider = MagicMock()
        with patch.object(processor, "_collect_docx_files_cloud", return_value=cloud_result) as mock_cloud:
            result = processor._collect_docx_files("/cloud-root", "non_litigation", storage_provider=provider)
        assert result is cloud_result
        # 关键词元组与云根路径透传
        args = mock_cloud.call_args.args
        assert args[0] == "/cloud-root"
        assert args[1] is provider
        assert set(args[2]) == {"修订版", "批注版", "律师修订"}

    def test_collects_and_classifies_docx(self, tmp_path: Path):
        lawyer_letter = tmp_path / "律师函修订版.docx"
        lawyer_letter.write_bytes(b"PK1")
        revision = tmp_path / "服务合同批注版.docx"
        revision.write_bytes(b"PK2")
        unrelated = tmp_path / "普通合同.docx"
        unrelated.write_bytes(b"PK3")
        txt = tmp_path / "证据修订版.txt"
        txt.write_bytes(b"text")

        processor = _make_processor()
        processor._scan_service._deduplicate_files.return_value = [
            {
                "path": lawyer_letter,
                "base_name": "律师函修订版",
                "version_token": "v1",
            },
            {
                "path": revision,
                "base_name": "服务合同批注版",
                "version_token": "v2",
            },
        ]
        result = processor._collect_docx_files(str(tmp_path), "non_litigation")
        assert len(result) == 2
        by_name = {c["filename"]: c for c in result}
        letter = by_name["律师函修订版.docx"]
        assert letter["archive_item_code"] == "nl_8"
        assert letter["archive_item_name"] == "法律意见书、律师函等"
        assert letter["reason"] == "常法docx（律师函）→ nl_8"
        rev = by_name["服务合同批注版.docx"]
        assert rev["archive_item_code"] == "nl_9"
        assert rev["archive_item_name"] == "案件其它关联材料"
        assert rev["reason"] == "常法docx（修订版/批注版）→ nl_9"
        for c in result:
            assert c["is_docx"] is True
            assert c["selected"] is True
            assert c["suggested_category"] == "case_material"
            assert c["confidence"] == 0.85
        # 去重服务收到的是按路径排序的文件列表（仅含关键词命中的 docx/doc）
        dedup_arg = processor._scan_service._deduplicate_files.call_args.args[0]
        assert lawyer_letter in dedup_arg
        assert revision in dedup_arg
        assert unrelated not in dedup_arg


# ── _collect_docx_files_cloud ─────────────────────────────────────


def _cloud_file(name: str, path: str, size: int = 100, modified_at: int = 1000) -> SimpleNamespace:
    return SimpleNamespace(name=name, path=path, size=size, modified_at=modified_at, is_dir=False)


class TestCollectDocxFilesCloud:
    def test_empty_walk_returns_empty(self):
        processor = _make_processor()
        provider = MagicMock()
        provider.walk.return_value = iter([("/root", [], [])])
        result = processor._collect_docx_files_cloud("/root", provider, ("修订版",))
        assert result == []

    def test_filters_and_classifies(self):
        processor = _make_processor()
        provider = MagicMock()
        provider.walk.return_value = iter(
            [
                (
                    "/root",
                    [],
                    [
                        _cloud_file("律师函修订版.docx", "/root/律师函修订版.docx", 10, 2000),
                        _cloud_file("普通.docx", "/root/普通.docx", 20, 3000),  # 无关键词
                        _cloud_file("目录", "/root/dir", 0, 4000),  # 目录（is_dir 由构造置 False，改手工）
                        _cloud_file("合同修订版.doc", "/root/合同修订版.doc", 30, 1000),
                    ],
                )
            ]
        )
        # 模拟目录条目
        walk_rows = list(provider.walk.return_value)
        files = walk_rows[0][2]
        files[2] = SimpleNamespace(name="目录", path="/root/dir", size=0, modified_at=4000, is_dir=True)
        provider.walk.return_value = iter([("/root", [], files)])

        result = processor._collect_docx_files_cloud("/root", provider, ("修订版", "批注版", "律师修订"))
        assert len(result) == 2
        letter = next(c for c in result if c["filename"] == "律师函修订版.docx")
        assert letter["archive_item_code"] == "nl_8"
        assert letter["source_path"] == "/root/律师函修订版.docx"
        assert letter["file_size"] == 10
        doc = next(c for c in result if c["filename"] == "合同修订版.doc")
        assert doc["archive_item_code"] == "nl_9"
        # 云存储分支 base_name 为归一化后的完整文件名（含扩展名）
        assert doc["base_name"] == "合同修订版.doc"

    def test_dedup_by_stem_keeps_latest(self):
        processor = _make_processor()
        provider = MagicMock()
        provider.walk.return_value = iter(
            [
                (
                    "/root",
                    [],
                    [
                        _cloud_file("合同修订版.docx", "/root/旧-合同修订版.docx", 10, 1000),
                        _cloud_file("合同修订版.docx", "/root/新-合同修订版.docx", 20, 5000),
                        _cloud_file("合同修订版.doc", "/root/更旧-合同修订版.doc", 30, 500),
                    ],
                )
            ]
        )
        result = processor._collect_docx_files_cloud("/root", provider, ("修订版",))
        # 同名 stem 分组后仅保留 modified_at 最新的一条
        assert len(result) == 1
        assert result[0]["source_path"] == "/root/新-合同修订版.docx"


# ── _mark_already_imported ────────────────────────────────────────


@pytest.mark.django_db
class TestMarkAlreadyImported:
    def _make_contract(self) -> Contract:
        return Contract.objects.create(name="哈希比对合同", case_type="civil")

    def test_no_existing_hashes_marks_all_false(self, tmp_path: Path):
        contract = self._make_contract()
        src = tmp_path / "新文件.pdf"
        src.write_bytes(b"unique-bytes")
        processor = _make_processor()
        candidates = [{"source_path": str(src), "filename": "新文件.pdf"}]
        processor._mark_already_imported(candidates, contract_id=contract.id)
        assert candidates[0]["already_imported"] is False

    def test_same_hash_marked_and_deselected(self, tmp_path: Path):
        contract = self._make_contract()
        src = tmp_path / "重复内容.pdf"
        content = b"same-content-bytes"
        src.write_bytes(content)
        import hashlib

        FinalizedMaterial.objects.create(
            contract=contract,
            file_path="contracts/finalized/x.pdf",
            original_filename="已导入.pdf",
            category=MaterialCategory.CASE_MATERIAL,
            content_hash=hashlib.sha256(content).hexdigest(),
        )
        processor = _make_processor()
        candidates = [
            {"source_path": str(src), "filename": "重复内容.pdf"},
            {"source_path": str(tmp_path / "别的.pdf"), "filename": "别的.pdf"},  # 不存在的本地文件
        ]
        (tmp_path / "别的.pdf").write_bytes(b"other")
        processor._mark_already_imported(candidates, contract_id=contract.id)
        assert candidates[0]["already_imported"] is True
        assert candidates[0]["selected"] is False
        assert candidates[1]["already_imported"] is False

    def test_skip_reason_candidate_not_checked(self, tmp_path: Path):
        contract = self._make_contract()
        import hashlib

        src = tmp_path / "跳过项.pdf"
        src.write_bytes(b"skipped")
        FinalizedMaterial.objects.create(
            contract=contract,
            file_path="contracts/finalized/y.pdf",
            original_filename="跳过项.pdf",
            category=MaterialCategory.CASE_MATERIAL,
            content_hash=hashlib.sha256(b"skipped").hexdigest(),
        )
        processor = _make_processor()
        candidates = [{"source_path": str(src), "filename": "跳过项.pdf", "skip_reason": "跳过规则"}]
        processor._mark_already_imported(candidates, contract_id=contract.id)
        assert candidates[0]["already_imported"] is False
        assert "selected" not in candidates[0]

    def test_empty_source_path_skipped(self, tmp_path: Path):
        contract = self._make_contract()
        FinalizedMaterial.objects.create(
            contract=contract,
            file_path="contracts/finalized/z.pdf",
            original_filename="占位.pdf",
            category=MaterialCategory.CASE_MATERIAL,
            content_hash="f" * 64,
        )
        processor = _make_processor()
        candidates = [{"source_path": "", "filename": "空路径.pdf"}]
        processor._mark_already_imported(candidates, contract_id=contract.id)
        assert "already_imported" not in candidates[0]

    def test_missing_local_file_skipped(self, tmp_path: Path):
        contract = self._make_contract()
        FinalizedMaterial.objects.create(
            contract=contract,
            file_path="contracts/finalized/w.pdf",
            original_filename="占位2.pdf",
            category=MaterialCategory.CASE_MATERIAL,
            content_hash="e" * 64,
        )
        processor = _make_processor()
        candidates = [{"source_path": str(tmp_path / "ghost.pdf"), "filename": "ghost.pdf"}]
        processor._mark_already_imported(candidates, contract_id=contract.id)
        assert "already_imported" not in candidates[0]

    def test_provider_read_bytes_matched(self):
        contract = self._make_contract()
        import hashlib

        FinalizedMaterial.objects.create(
            contract=contract,
            file_path="contracts/finalized/c.pdf",
            original_filename="云端.pdf",
            category=MaterialCategory.CASE_MATERIAL,
            content_hash=hashlib.sha256(b"cloud-bytes").hexdigest(),
        )
        provider = MagicMock()
        provider.read_file.return_value = b"cloud-bytes"
        processor = _make_processor()
        candidates = [{"source_path": "cloud/云端.pdf", "filename": "云端.pdf"}]
        processor._mark_already_imported(candidates, contract_id=contract.id, storage_provider=provider)
        provider.read_file.assert_called_once_with("cloud/云端.pdf")
        assert candidates[0]["already_imported"] is True
        assert candidates[0]["selected"] is False

    def test_provider_read_error_isolated(self):
        contract = self._make_contract()
        FinalizedMaterial.objects.create(
            contract=contract,
            file_path="contracts/finalized/d.pdf",
            original_filename="异常.pdf",
            category=MaterialCategory.CASE_MATERIAL,
            content_hash="d" * 64,
        )
        provider = MagicMock()
        provider.read_file.side_effect = RuntimeError("webdav down")
        processor = _make_processor()
        candidates = [
            {"source_path": "cloud/异常.pdf", "filename": "异常.pdf"},
            {"source_path": "cloud/正常.pdf", "filename": "正常.pdf"},
        ]
        provider.read_file.side_effect = [RuntimeError("webdav down"), b"normal-bytes"]
        processor._mark_already_imported(candidates, contract_id=contract.id, storage_provider=provider)
        assert "already_imported" not in candidates[0]
        assert candidates[1]["already_imported"] is False


# ── _relative_path_str 补充分支 ───────────────────────────────────


class TestRelativePathStrExtra:
    def test_outside_root_returns_empty(self, tmp_path: Path):
        processor = _make_processor()
        other = tmp_path / "other"
        other.mkdir()
        result = processor._relative_path_str(source_path=str(other / "f.txt"), scan_root=tmp_path / "scan-root")
        assert result == ""

    def test_none_source_returns_empty(self):
        processor = _make_processor()
        result = processor._relative_path_str(source_path="", scan_root=Path("/tmp"))
        assert result == ""
