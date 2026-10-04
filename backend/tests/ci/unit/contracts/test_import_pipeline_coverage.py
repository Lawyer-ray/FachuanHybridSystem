"""补充覆盖测试: contracts/services/contract/integrations/_import_pipeline.py

覆盖: ImportPipeline.confirm_import 的状态校验 / 候选校验 / 分类归一化 /
本地与云存储读取 / docx 转换 / 监督卡检测 / 哈希与同名去重 / 工作日志导入,
以及 _convert_docx_to_temp_pdf(_from_bytes)。
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import MagicMock, patch

import pytest

from apps.contracts.models.folder_scan_session import ContractFolderScanStatus
from apps.core.exceptions import ValidationException

PIPELINE_MOD = "apps.contracts.services.contract.integrations._import_pipeline"


def _make_session(status: str = ContractFolderScanStatus.COMPLETED, payload: dict | None = None) -> MagicMock:
    session = MagicMock()
    session.id = 12345
    session.status = status
    session.result_payload = payload if payload is not None else {"candidates": []}
    session.started_by_id = 7
    return session


def _make_pipeline() -> Any:
    from apps.contracts.services.contract.integrations._import_pipeline import ImportPipeline

    return ImportPipeline()


@contextmanager
def _patched_pipeline(
    pipeline: Any,
    *,
    quality_card: bool = False,
    duplicate: bool = False,
    content_hash: str = "a" * 64,
) -> Iterator[dict[str, Any]]:
    """confirm_import 打桩环境: 模型 / 哈希 / 监督卡 / 材料存储全部 mock。

    MaterialService 在 __init__ 时已实例化，因此除打桩类之外还替换实例属性。
    """
    material_model = MagicMock()
    material_model.objects.filter.return_value.exists.return_value = duplicate
    created = MagicMock()
    created.id = 1
    material_model.objects.create.return_value = created

    session_model = MagicMock()
    material_service = MagicMock()
    material_service.save_material_file.return_value = ("rel/path.pdf", "原文件名.pdf")

    card_fn = MagicMock(return_value=quality_card)
    hash_fn = MagicMock(return_value=content_hash)

    with (
        patch(f"{PIPELINE_MOD}.FinalizedMaterial", material_model),
        patch(f"{PIPELINE_MOD}.ContractFolderScanSession", session_model),
        patch(f"{PIPELINE_MOD}.compute_file_hash_from_bytes", hash_fn),
        patch(f"{PIPELINE_MOD}.has_quality_card_on_last_page", card_fn),
    ):
        original_service = pipeline._material_service
        pipeline._material_service = material_service
        try:
            yield {
                "FinalizedMaterial": material_model,
                "ContractFolderScanSession": session_model,
                "material_service": material_service,
                "card_fn": card_fn,
                "hash_fn": hash_fn,
            }
        finally:
            pipeline._material_service = original_service


def _session_update_kwargs(base: dict[str, Any]) -> dict[str, Any]:
    return base["ContractFolderScanSession"].objects.filter.return_value.update.call_args.kwargs


# ── confirm_import: 会话状态校验 ──────────────────────────────────


class TestConfirmImportSessionStatus:
    @pytest.mark.django_db
    def test_imported_session_rejected(self):
        pipeline = _make_pipeline()
        with pytest.raises(ValidationException, match="该扫描已导入"):
            pipeline.confirm_import(
                contract_id=1,
                session=_make_session(status=ContractFolderScanStatus.IMPORTED),
                items=[],
            )

    @pytest.mark.django_db
    def test_running_session_rejected(self):
        pipeline = _make_pipeline()
        with pytest.raises(ValidationException, match="扫描尚未完成"):
            pipeline.confirm_import(
                contract_id=1,
                session=_make_session(status=ContractFolderScanStatus.RUNNING),
                items=[],
            )


# ── confirm_import: 候选项校验 ────────────────────────────────────


class TestConfirmImportItemValidation:
    @pytest.mark.django_db
    def test_unselected_item_skipped(self):
        pipeline = _make_pipeline()
        session = _make_session(payload={"candidates": [{"source_path": "/tmp/a.pdf"}]})
        with _patched_pipeline(pipeline) as base:
            result = pipeline.confirm_import(
                contract_id=9,
                session=session,
                items=[{"source_path": "/tmp/a.pdf", "selected": False}],
            )
        assert result["imported_count"] == 0
        assert base["FinalizedMaterial"].objects.create.call_count == 0
        # 未选中项仍会把会话标记为已导入
        update_kwargs = _session_update_kwargs(base)
        assert update_kwargs["status"] == ContractFolderScanStatus.IMPORTED
        assert update_kwargs["progress"] == 100
        assert update_kwargs["current_file"] == ""
        assert update_kwargs["error_message"] == ""

    @pytest.mark.django_db
    def test_missing_source_path_rejected(self):
        pipeline = _make_pipeline()
        session = _make_session(payload={"candidates": [{"source_path": "/tmp/a.pdf"}]})
        with _patched_pipeline(pipeline), pytest.raises(ValidationException, match="候选文件不存在"):
            pipeline.confirm_import(contract_id=9, session=session, items=[{"source_path": ""}])

    @pytest.mark.django_db
    def test_unknown_source_path_rejected(self):
        pipeline = _make_pipeline()
        session = _make_session(payload={"candidates": [{"source_path": "/tmp/a.pdf"}]})
        with _patched_pipeline(pipeline), pytest.raises(ValidationException, match="候选文件不存在"):
            pipeline.confirm_import(
                contract_id=9,
                session=session,
                items=[{"source_path": "/tmp/not-in-candidates.pdf"}],
            )

    @pytest.mark.django_db
    def test_invalid_category_falls_back_to_case_material(self, tmp_path: Path):
        src = tmp_path / "合同.pdf"
        src.write_bytes(b"%PDF-1.4 local")
        pipeline = _make_pipeline()
        session = _make_session(payload={"candidates": [{"source_path": str(src)}]})
        with _patched_pipeline(pipeline) as base:
            result = pipeline.confirm_import(
                contract_id=9,
                session=session,
                items=[{"source_path": str(src), "category": "totally_invalid"}],
            )
        assert result["imported_count"] == 1
        create_kwargs = base["FinalizedMaterial"].objects.create.call_args.kwargs
        assert create_kwargs["category"] == "case_material"
        assert create_kwargs["contract_id"] == 9

    @pytest.mark.django_db
    def test_local_source_file_missing_rejected(self):
        pipeline = _make_pipeline()
        session = _make_session(payload={"candidates": [{"source_path": "/tmp/gone.pdf"}]})
        with _patched_pipeline(pipeline), pytest.raises(ValidationException, match="源文件不存在"):
            pipeline.confirm_import(
                contract_id=9,
                session=session,
                items=[{"source_path": "/tmp/gone.pdf"}],
            )


# ── confirm_import: 本地文件导入 + 归档编号 ────────────────────────


class TestConfirmImportLocalFile:
    @pytest.mark.django_db
    def test_happy_path_import(self, tmp_path: Path):
        src = tmp_path / "委托合同.pdf"
        src.write_bytes(b"%PDF-1.4 content")
        pipeline = _make_pipeline()
        session = _make_session(payload={"candidates": [{"source_path": str(src)}]})
        with _patched_pipeline(pipeline) as base:
            result = pipeline.confirm_import(
                contract_id=9,
                session=session,
                items=[{"source_path": str(src), "category": "contract_original", "archive_item_code": "nl_4"}],
            )
        assert result["imported_count"] == 1
        assert result["work_log_imported"] == 0
        save_args = base["material_service"].save_material_file.call_args.args
        assert save_args[0].name == "委托合同.pdf"
        assert save_args[0].read() == b"%PDF-1.4 content"
        assert save_args[1] == 9
        create_kwargs = base["FinalizedMaterial"].objects.create.call_args.kwargs
        assert create_kwargs["archive_item_code"] == "nl_4"
        assert create_kwargs["file_path"] == "rel/path.pdf"
        assert create_kwargs["original_filename"] == "原文件名.pdf"
        assert create_kwargs["content_hash"] == "a" * 64
        # 会话结果载荷写入导入统计
        update_kwargs = _session_update_kwargs(base)
        import_result = update_kwargs["result_payload"]["import_result"]
        assert import_result["imported_count"] == 1
        assert import_result["skipped_dupes"] == 0
        assert import_result["work_log_imported"] == 0
        assert update_kwargs["result_payload"]["confirmed_work_log_suggestions"] == []

    @pytest.mark.django_db
    def test_empty_archive_item_code_omitted(self, tmp_path: Path):
        src = tmp_path / "发票.pdf"
        src.write_bytes(b"%PDF-1.4 invoice")
        pipeline = _make_pipeline()
        session = _make_session(payload={"candidates": [{"source_path": str(src)}]})
        with _patched_pipeline(pipeline) as base:
            pipeline.confirm_import(
                contract_id=9,
                session=session,
                items=[{"source_path": str(src), "category": "invoice", "archive_item_code": "  "}],
            )
        create_kwargs = base["FinalizedMaterial"].objects.create.call_args.kwargs
        assert "archive_item_code" not in create_kwargs


# ── confirm_import: 云存储 provider 分支 ──────────────────────────


class TestConfirmImportCloudStorage:
    @pytest.mark.django_db
    def test_provider_read_success(self):
        provider = MagicMock()
        provider.read_file.return_value = b"%PDF cloud bytes"
        pipeline = _make_pipeline()
        session = _make_session(payload={"candidates": [{"source_path": "cloud/合同扫描.pdf"}]})
        with _patched_pipeline(pipeline) as base:
            result = pipeline.confirm_import(
                contract_id=9,
                session=session,
                items=[{"source_path": "cloud/合同扫描.pdf", "category": "case_material"}],
                storage_provider=provider,
            )
        provider.read_file.assert_called_once_with("cloud/合同扫描.pdf")
        assert result["imported_count"] == 1
        # 云存储下上传文件名取自 POSIX 路径末段
        save_args = base["material_service"].save_material_file.call_args.args
        assert save_args[0].name == "合同扫描.pdf"
        assert save_args[0].read() == b"%PDF cloud bytes"
        assert save_args[1] == 9

    @pytest.mark.django_db
    def test_provider_cloud_storage_error_reraised(self):
        from apps.cloud_storage.exceptions import CloudStorageError

        provider = MagicMock()
        provider.read_file.side_effect = CloudStorageError("boom", provider="webdav")
        pipeline = _make_pipeline()
        session = _make_session(payload={"candidates": [{"source_path": "cloud/x.pdf"}]})
        with _patched_pipeline(pipeline), pytest.raises(CloudStorageError, match="boom"):
            pipeline.confirm_import(
                contract_id=9,
                session=session,
                items=[{"source_path": "cloud/x.pdf"}],
                storage_provider=provider,
            )

    @pytest.mark.django_db
    def test_provider_generic_error_wrapped(self):
        from apps.cloud_storage.exceptions import CloudStorageError

        provider = MagicMock()
        provider.read_file.side_effect = OSError("disk broken")
        pipeline = _make_pipeline()
        session = _make_session(payload={"candidates": [{"source_path": "cloud/y.pdf"}]})
        with _patched_pipeline(pipeline), pytest.raises(CloudStorageError, match="读取云存储文件失败"):
            pipeline.confirm_import(
                contract_id=9,
                session=session,
                items=[{"source_path": "cloud/y.pdf"}],
                storage_provider=provider,
            )

    @pytest.mark.django_db
    def test_provider_quality_card_uses_tempfile_not_source(self):
        """云存储 + 合同正本 + 监督卡：走 tempfile 分支且标题被替换。"""
        provider = MagicMock()
        provider.read_file.return_value = b"%PDF with card"
        pipeline = _make_pipeline()
        session = _make_session(payload={"candidates": [{"source_path": "cloud/正本.pdf"}]})
        with _patched_pipeline(pipeline, quality_card=True) as base:
            result = pipeline.confirm_import(
                contract_id=9,
                session=session,
                items=[{"source_path": "cloud/正本.pdf", "category": "contract_original"}],
                storage_provider=provider,
            )
        assert result["imported_count"] == 1
        # 监督卡检测读到的是临时文件而非云路径
        card_path = base["card_fn"].call_args.args[0]
        assert card_path.is_absolute()
        assert "cloud" not in card_path.parts
        create_kwargs = base["FinalizedMaterial"].objects.create.call_args.kwargs
        assert create_kwargs["original_filename"] == "合同正本与律师办案服务质量监督卡"


# ── confirm_import: 监督卡检测（本地）─────────────────────────────


class TestConfirmImportQualityCard:
    @pytest.mark.django_db
    def test_quality_card_detected_local(self, tmp_path: Path):
        src = tmp_path / "正本合同.pdf"
        src.write_bytes(b"%PDF has card")
        pipeline = _make_pipeline()
        session = _make_session(payload={"candidates": [{"source_path": str(src)}]})
        with _patched_pipeline(pipeline, quality_card=True) as base:
            result = pipeline.confirm_import(
                contract_id=9,
                session=session,
                items=[{"source_path": str(src), "category": "contract_original"}],
            )
        assert result["imported_count"] == 1
        # 本地路径直接送检
        assert base["card_fn"].call_args.args[0] == src
        create_kwargs = base["FinalizedMaterial"].objects.create.call_args.kwargs
        assert create_kwargs["original_filename"] == "合同正本与律师办案服务质量监督卡"

    @pytest.mark.django_db
    def test_no_quality_card_keeps_display_name(self, tmp_path: Path):
        src = tmp_path / "正本合同2.pdf"
        src.write_bytes(b"%PDF no card")
        pipeline = _make_pipeline()
        session = _make_session(payload={"candidates": [{"source_path": str(src)}]})
        with _patched_pipeline(pipeline, quality_card=False) as base:
            pipeline.confirm_import(
                contract_id=9,
                session=session,
                items=[{"source_path": str(src), "category": "contract_original"}],
            )
        create_kwargs = base["FinalizedMaterial"].objects.create.call_args.kwargs
        # save_material_file 返回的原始名作为展示名
        assert create_kwargs["original_filename"] == "原文件名.pdf"

    @pytest.mark.django_db
    def test_quality_card_not_checked_for_other_category(self, tmp_path: Path):
        src = tmp_path / "发票3.pdf"
        src.write_bytes(b"%PDF invoice")
        pipeline = _make_pipeline()
        session = _make_session(payload={"candidates": [{"source_path": str(src)}]})
        with _patched_pipeline(pipeline, quality_card=True) as base:
            pipeline.confirm_import(
                contract_id=9,
                session=session,
                items=[{"source_path": str(src), "category": "invoice"}],
            )
        base["card_fn"].assert_not_called()


# ── confirm_import: docx 分支 ─────────────────────────────────────


class TestConfirmImportDocx:
    @pytest.mark.django_db
    def test_docx_conversion_failed_skips_item(self, tmp_path: Path):
        src = tmp_path / "修订版合同.docx"
        src.write_bytes(b"PK docx bytes")
        pipeline = _make_pipeline()
        session = _make_session(payload={"candidates": [{"source_path": str(src)}]})
        with (
            _patched_pipeline(pipeline) as base,
            patch.object(pipeline, "_convert_docx_to_temp_pdf_from_bytes", return_value=None) as mock_conv,
        ):
            result = pipeline.confirm_import(
                contract_id=9,
                session=session,
                items=[{"source_path": str(src), "is_docx": True}],
            )
        mock_conv.assert_called_once_with(b"PK docx bytes", "修订版合同.docx")
        assert result["imported_count"] == 0
        assert base["FinalizedMaterial"].objects.create.call_count == 0

    @pytest.mark.django_db
    def test_docx_local_uses_temp_pdf(self, tmp_path: Path):
        src = tmp_path / "修订版合同.docx"
        src.write_bytes(b"PK docx bytes")
        temp_pdf = tmp_path / "converted.pdf"
        temp_pdf.write_bytes(b"%PDF converted")
        pipeline = _make_pipeline()
        session = _make_session(payload={"candidates": [{"source_path": str(src)}]})
        with (
            _patched_pipeline(pipeline) as base,
            patch.object(pipeline, "_convert_docx_to_temp_pdf_from_bytes", return_value=temp_pdf),
        ):
            result = pipeline.confirm_import(
                contract_id=9,
                session=session,
                items=[{"source_path": str(src), "is_docx": True}],
            )
        assert result["imported_count"] == 1
        save_args = base["material_service"].save_material_file.call_args.args
        # 本地 docx: 上传名 = 临时 PDF 文件名, 展示名 = 原 docx 文件名
        assert save_args[0].name == temp_pdf.name
        assert save_args[0].read() == b"%PDF converted"
        create_kwargs = base["FinalizedMaterial"].objects.create.call_args.kwargs
        assert create_kwargs["original_filename"] == "修订版合同.docx"

    @pytest.mark.django_db
    def test_docx_cloud_uses_stem_pdf_name(self, tmp_path: Path):
        provider = MagicMock()
        provider.read_file.return_value = b"PK cloud docx"
        temp_pdf = tmp_path / "fake_docx_convert_result.pdf"
        temp_pdf.write_bytes(b"%PDF converted cloud")
        pipeline = _make_pipeline()
        session = _make_session(payload={"candidates": [{"source_path": "cloud/合同修订版.docx"}]})
        with (
            _patched_pipeline(pipeline) as base,
            patch.object(pipeline, "_convert_docx_to_temp_pdf_from_bytes", return_value=temp_pdf),
        ):
            result = pipeline.confirm_import(
                contract_id=9,
                session=session,
                items=[{"source_path": "cloud/合同修订版.docx", "is_docx": True}],
                storage_provider=provider,
            )
        assert result["imported_count"] == 1
        save_args = base["material_service"].save_material_file.call_args.args
        # 云存储 docx: 上传名 = 原名去扩展 + .pdf
        assert save_args[0].name == "合同修订版.pdf"
        assert save_args[0].read() == b"%PDF converted cloud"
        create_kwargs = base["FinalizedMaterial"].objects.create.call_args.kwargs
        assert create_kwargs["original_filename"] == "合同修订版.docx"

    @pytest.mark.django_db
    def test_docx_temp_file_cleaned_after_import(self, tmp_path: Path):
        src = tmp_path / "批注版.docx"
        src.write_bytes(b"PK docx")
        temp_pdf = tmp_path / "temp_convert_result.pdf"
        temp_pdf.write_bytes(b"%PDF temp")
        pipeline = _make_pipeline()
        session = _make_session(payload={"candidates": [{"source_path": str(src)}]})
        with (
            _patched_pipeline(pipeline),
            patch.object(pipeline, "_convert_docx_to_temp_pdf_from_bytes", return_value=temp_pdf),
        ):
            pipeline.confirm_import(
                contract_id=9,
                session=session,
                items=[{"source_path": str(src), "is_docx": True}],
            )
        # finally 分支删除临时 PDF
        assert not temp_pdf.exists()

    @pytest.mark.django_db
    def test_docx_no_quality_card_check(self, tmp_path: Path):
        """docx + 合同正本：is_docx 分支不做监督卡 OCR 检测。"""
        src = tmp_path / "正本修订.docx"
        src.write_bytes(b"PK docx original")
        temp_pdf = tmp_path / "converted2.pdf"
        temp_pdf.write_bytes(b"%PDF converted2")
        pipeline = _make_pipeline()
        session = _make_session(payload={"candidates": [{"source_path": str(src)}]})
        with (
            _patched_pipeline(pipeline, quality_card=True) as base,
            patch.object(pipeline, "_convert_docx_to_temp_pdf_from_bytes", return_value=temp_pdf),
        ):
            pipeline.confirm_import(
                contract_id=9,
                session=session,
                items=[{"source_path": str(src), "is_docx": True, "category": "contract_original"}],
            )
        base["card_fn"].assert_not_called()
        create_kwargs = base["FinalizedMaterial"].objects.create.call_args.kwargs
        assert create_kwargs["original_filename"] == "正本修订.docx"


# ── confirm_import: 去重分支 ──────────────────────────────────────


class TestConfirmImportDedup:
    @pytest.mark.django_db
    def test_content_hash_duplicate_skipped(self, tmp_path: Path):
        src = tmp_path / "重复文件.pdf"
        src.write_bytes(b"%PDF dup")
        pipeline = _make_pipeline()
        session = _make_session(payload={"candidates": [{"source_path": str(src)}]})
        with _patched_pipeline(pipeline, duplicate=True) as base:
            result = pipeline.confirm_import(
                contract_id=9,
                session=session,
                items=[{"source_path": str(src), "category": "case_material"}],
            )
        assert result["imported_count"] == 0
        update_kwargs = _session_update_kwargs(base)
        assert update_kwargs["result_payload"]["import_result"]["skipped_dupes"] == 1
        base["FinalizedMaterial"].objects.create.assert_not_called()

    @pytest.mark.django_db
    def test_name_duplicate_skipped_when_no_hash(self, tmp_path: Path):
        src = tmp_path / "同名文件.pdf"
        src.write_bytes(b"%PDF no hash")
        pipeline = _make_pipeline()
        session = _make_session(payload={"candidates": [{"source_path": str(src)}]})
        with _patched_pipeline(pipeline, duplicate=True, content_hash="") as base:
            result = pipeline.confirm_import(
                contract_id=9,
                session=session,
                items=[{"source_path": str(src), "category": "case_material"}],
            )
        assert result["imported_count"] == 0
        # 同名查重的过滤键: contract_id + original_filename + category
        filter_args = base["FinalizedMaterial"].objects.filter.call_args.kwargs
        assert filter_args["original_filename"] == "原文件名.pdf"
        assert filter_args["category"] == "case_material"
        base["FinalizedMaterial"].objects.create.assert_not_called()

    @pytest.mark.django_db
    def test_learn_from_correction_called(self, tmp_path: Path):
        src = tmp_path / "学习.pdf"
        src.write_bytes(b"%PDF learn")
        pipeline = _make_pipeline()
        candidate = {"source_path": str(src), "filename": "学习.pdf"}
        session = _make_session(payload={"candidates": [candidate]})
        learn_fn = MagicMock()
        with _patched_pipeline(pipeline):
            pipeline.confirm_import(
                contract_id=9,
                session=session,
                items=[{"source_path": str(src), "archive_item_code": "lt_6"}],
                learn_from_correction_fn=learn_fn,
            )
        learn_fn.assert_called_once_with(candidate=candidate, actual_archive_item_code="lt_6", contract_id=9)


# ── _import_work_log_suggestions ──────────────────────────────────


class TestImportWorkLogSuggestions:
    def test_empty_confirmed_logs_returns_zero(self):
        pipeline = _make_pipeline()
        assert pipeline._import_work_log_suggestions(contract_id=1, confirmed_logs=[]) == 0

    def test_no_related_case_returns_zero(self):
        pipeline = _make_pipeline()
        case_service = MagicMock()
        case_service.get_cases_by_contract.return_value = []
        with patch("apps.core.interfaces.ServiceLocator.get_case_service", return_value=case_service):
            count = pipeline._import_work_log_suggestions(
                contract_id=1,
                confirmed_logs=[{"content": "日志"}],
            )
        assert count == 0

    def test_imports_logs_and_skips_duplicates(self):
        pipeline = _make_pipeline()
        case_service = MagicMock()
        case_service.get_cases_by_contract.return_value = [MagicMock(id=55)]
        with (
            patch("apps.core.interfaces.ServiceLocator.get_case_service", return_value=case_service),
            patch("apps.cases.models.CaseLog") as case_log_model,
        ):
            case_log_model.objects.filter.return_value.values_list.return_value = ["已有日志"]
            count = pipeline._import_work_log_suggestions(
                contract_id=1,
                confirmed_logs=[
                    {"content": "已有日志", "date": "2026-01-02"},
                    {"content": "新日志A", "date": "2026-01-03"},
                    {"content": "  ", "date": ""},
                    {"content": "新日志B", "date": ""},
                ],
                actor_id=7,
            )
        assert count == 2
        assert case_service.create_case_log_internal.call_count == 2
        first_call = case_service.create_case_log_internal.call_args_list[0]
        assert first_call.kwargs == {"case_id": 55, "content": "新日志A", "user_id": 7, "event_date": "2026-01-03"}
        second_call = case_service.create_case_log_internal.call_args_list[1]
        assert second_call.kwargs["content"] == "新日志B"
        assert second_call.kwargs["event_date"] is None

    def test_item_failure_isolated(self):
        pipeline = _make_pipeline()
        case_service = MagicMock()
        case_service.get_cases_by_contract.return_value = [MagicMock(id=66)]

        def _create(**kwargs: Any) -> Any:
            if kwargs["content"] == "坏日志":
                raise RuntimeError("db down")
            return MagicMock()

        case_service.create_case_log_internal.side_effect = _create
        with (
            patch("apps.core.interfaces.ServiceLocator.get_case_service", return_value=case_service),
            patch("apps.cases.models.CaseLog") as case_log_model,
        ):
            case_log_model.objects.filter.return_value.values_list.return_value = []
            count = pipeline._import_work_log_suggestions(
                contract_id=1,
                confirmed_logs=[{"content": "坏日志", "date": ""}, {"content": "好日志", "date": ""}],
            )
        assert count == 1

    @pytest.mark.django_db
    def test_confirmed_logs_persisted_in_payload(self, tmp_path: Path):
        src = tmp_path / "带日志.pdf"
        src.write_bytes(b"%PDF logs")
        pipeline = _make_pipeline()
        session = _make_session(payload={"candidates": [{"source_path": str(src)}]})
        suggestions = [{"content": "签署合同", "date": "2026-01-01"}]
        case_service = MagicMock()
        case_service.get_cases_by_contract.return_value = []
        with (
            _patched_pipeline(pipeline) as base,
            patch("apps.core.interfaces.ServiceLocator.get_case_service", return_value=case_service),
        ):
            result = pipeline.confirm_import(
                contract_id=9,
                session=session,
                items=[{"source_path": str(src)}],
                work_log_suggestions=suggestions,
            )
        update_kwargs = _session_update_kwargs(base)
        assert update_kwargs["result_payload"]["confirmed_work_log_suggestions"] == suggestions
        assert result["work_log_imported"] == 0
        assert result["session_id"] == "12345"
        assert result["status"] == ContractFolderScanStatus.IMPORTED


# ── docx 转换辅助方法 ─────────────────────────────────────────────


class TestConvertDocxHelpers:
    def test_convert_docx_success(self, tmp_path: Path):
        pipeline = _make_pipeline()
        docx = tmp_path / "a.docx"
        docx.write_bytes(b"PK")
        pdf_out = tmp_path / "a.pdf"
        with patch(
            "apps.documents.services.infrastructure.pdf_merge_utils.convert_docx_to_pdf",
            return_value=str(pdf_out),
        ) as mock_conv:
            result = pipeline._convert_docx_to_temp_pdf(docx)
        mock_conv.assert_called_once_with(docx.as_posix())
        assert result == pdf_out

    def test_convert_docx_empty_result(self, tmp_path: Path):
        pipeline = _make_pipeline()
        docx = tmp_path / "a.docx"
        docx.write_bytes(b"PK")
        with patch(
            "apps.documents.services.infrastructure.pdf_merge_utils.convert_docx_to_pdf",
            return_value="",
        ):
            assert pipeline._convert_docx_to_temp_pdf(docx) is None

    def test_convert_docx_oserror_returns_none(self, tmp_path: Path):
        pipeline = _make_pipeline()
        docx = tmp_path / "a.docx"
        docx.write_bytes(b"PK")
        with patch(
            "apps.documents.services.infrastructure.pdf_merge_utils.convert_docx_to_pdf",
            side_effect=OSError("libreoffice missing"),
        ):
            assert pipeline._convert_docx_to_temp_pdf(docx) is None

    def test_convert_from_bytes_success(self, tmp_path: Path):
        pipeline = _make_pipeline()
        pdf_out = tmp_path / "from_bytes.pdf"
        with patch(
            "apps.documents.services.infrastructure.pdf_merge_utils.convert_docx_to_pdf",
            return_value=str(pdf_out),
        ) as mock_conv:
            result = pipeline._convert_docx_to_temp_pdf_from_bytes(b"PK bytes", "x.docx")
        assert result == pdf_out
        # 临时 docx 已被清理
        temp_docx = Path(mock_conv.call_args.args[0])
        assert not temp_docx.exists()
        assert temp_docx.suffix == ".docx"

    def test_convert_from_bytes_empty_result(self):
        pipeline = _make_pipeline()
        with patch(
            "apps.documents.services.infrastructure.pdf_merge_utils.convert_docx_to_pdf",
            return_value=None,
        ):
            assert pipeline._convert_docx_to_temp_pdf_from_bytes(b"PK bytes", "x.docx") is None

    def test_convert_from_bytes_oserror_returns_none(self):
        pipeline = _make_pipeline()
        with patch(
            "apps.documents.services.infrastructure.pdf_merge_utils.convert_docx_to_pdf",
            side_effect=RuntimeError("converter crashed"),
        ):
            assert pipeline._convert_docx_to_temp_pdf_from_bytes(b"PK bytes", "x.docx") is None
