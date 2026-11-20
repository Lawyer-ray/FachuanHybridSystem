"""草案区 → 冲突检测 → 单点应用的端到端（三栏并答写同一份 docx 的护栏）。

这一组用例守的是 B1 的核心承诺：**三栏并答期间任何一栏都不落盘**，律师裁决后
只有一次写盘，且写之前还要再过两道闸（互斥冲突、mtime 二次校验）。

三条硬断言（对应任务书的 DoD）：

1. 三栏对同一段原文产出交叠 patch → 3 份**都在**、`conflicts` 恰好 1 条、
   文件字节**没有被任何人写**（无静默覆盖）；
2. 互补的两条 → 一次写盘同时落下两处修订（不是写两次）；
3. 提案后文件被改过（mtime 不符）→ 409 且文件不变。
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from docx import Document

from apps.contract_review.services.patch import service as patch_service
from apps.contract_review.services.patch.models import ContractWritePatch, PatchStatus
from apps.contract_review.services.patch.service import apply_patches, collect_patch, docx_full_text
from apps.contracts.services.contract.integrations.folder_browse_service import ContractFolderBrowseService
from apps.core.exceptions import ConflictError, ValidationException
from tests.ci.unit.contract_review.services.patch.docx_fixtures import (
    CLAUSE_COURT,
    CLAUSE_PAYMENT,
    CLAUSE_PENALTY,
    SUBPATH,
)

PAYMENT_A = "甲方应于十五日内支付货款。"
PAYMENT_B = "甲方应于十日内支付货款。"
PAYMENT_C = "甲方应于五日内支付货款。"
COURT_NEW = "因本合同产生的争议，由甲方所在地人民法院管辖。"


def _collect(contract: Any, original: str, replacement: str, **kwargs: Any) -> str:
    patch = collect_patch(
        owner_kind="contract",
        owner_id=contract.id,
        subpath=SUBPATH,
        original=original,
        replacement=replacement,
        **kwargs,
    )
    return patch.patch_id


def _doc_text(file_path: Path) -> str:
    return docx_full_text(Document(BytesIO(file_path.read_bytes())))


class TestCollectPatch:
    @pytest.mark.django_db(transaction=True)
    def test_collect_persists_proposal_without_touching_disk(
        self, bound: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`collect_patch` 只落库：**不碰**绑定文件夹（连 browse 都不该实例化）。"""
        _lawyer, contract, file_path = bound()
        before = file_path.read_bytes()

        def _boom(*_args: Any, **_kwargs: Any) -> Any:  # pragma: no cover - 被调即失败
            raise AssertionError("collect_patch 不该访问磁盘/绑定文件夹")

        monkeypatch.setattr(patch_service, "_browse", _boom)
        patch_id = _collect(contract, CLAUSE_PAYMENT, PAYMENT_A, base_mtime=123.0, turn=7)

        row = ContractWritePatch.objects.get(patch_id=patch_id)
        assert row.status == PatchStatus.PROPOSED
        assert row.original == CLAUSE_PAYMENT  # 逐字入库，不做归一化
        assert row.replacement == PAYMENT_A
        assert (row.owner_kind, row.owner_id, row.subpath) == ("contract", contract.id, SUBPATH)
        assert row.turn == 7
        assert file_path.read_bytes() == before

    @pytest.mark.django_db(transaction=True)
    def test_rejects_empty_original_or_replacement(self, bound: Any) -> None:
        _lawyer, contract, _path = bound()
        with pytest.raises(ValidationException):
            _collect(contract, "   ", PAYMENT_A)
        with pytest.raises(ValidationException):
            _collect(contract, CLAUSE_PAYMENT, "  ")

    @pytest.mark.django_db(transaction=True)
    def test_rejects_bad_owner_kind(self) -> None:
        with pytest.raises(ValidationException):
            collect_patch(owner_kind="invoice", owner_id=1, subpath=SUBPATH, original="x", replacement="y")


class TestThreeLanesOverlap:
    @pytest.mark.django_db(transaction=True)
    def test_three_overlapping_patches_are_kept_and_apply_is_refused(self, bound: Any) -> None:
        lawyer, contract, file_path = bound()
        before = file_path.read_bytes()
        ids = [
            _collect(contract, CLAUSE_PAYMENT, PAYMENT_A),
            _collect(contract, CLAUSE_PAYMENT, PAYMENT_B),
            _collect(contract, CLAUSE_PAYMENT, PAYMENT_C),
        ]

        with pytest.raises(ConflictError) as excinfo:
            apply_patches(patch_ids=ids, note="三栏都改了付款期限", user=lawyer)

        # ① 3 份都在（没有谁被悄悄丢掉）——SQL 直查，避免缓存/默认排序掩盖
        assert ContractWritePatch.objects.filter(patch_id__in=ids).count() == 3
        # ② conflicts 恰好 1 条（同一段原文被三种改法命中，律师一次裁决完）
        conflicts = excinfo.value.to_dict()["errors"]["conflicts"]
        assert len(conflicts) == 1
        assert "互斥" in conflicts[0]
        # ③ 无静默覆盖：文件字节一个都没变，也没有任何一条被标成已应用
        assert file_path.read_bytes() == before
        assert not ContractWritePatch.objects.filter(patch_id__in=ids, status=PatchStatus.APPLIED).exists()
        text = _doc_text(file_path)
        assert PAYMENT_A not in text and PAYMENT_B not in text and PAYMENT_C not in text


class TestComplementary:
    @pytest.mark.django_db(transaction=True)
    def test_two_disjoint_patches_apply_in_one_write(
        self, bound: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        lawyer, contract, file_path = bound()
        first = _collect(contract, CLAUSE_PAYMENT, PAYMENT_A)
        second = _collect(contract, CLAUSE_COURT, COURT_NEW)

        writes: list[int] = []
        original_save = ContractFolderBrowseService.save_file_content

        def _counting_save(self: Any, **kwargs: Any) -> Any:
            writes.append(len(kwargs.get("data") or b""))
            return original_save(self, **kwargs)

        monkeypatch.setattr(ContractFolderBrowseService, "save_file_content", _counting_save)

        result = apply_patches(patch_ids=[first, second], note="两处都采纳", user=lawyer)

        assert result["applied"] == [first, second]
        assert len(writes) == 1, "同一份文件必须一次写盘（逐条写会把文档改到一半）"
        text = _doc_text(file_path)
        assert PAYMENT_A in text and COURT_NEW in text
        # 未改的那段原样保留（互补 ≠ 只应用第一条）
        assert CLAUSE_PENALTY in text
        rows = ContractWritePatch.objects.filter(patch_id__in=[first, second])
        assert {row.status for row in rows} == {PatchStatus.APPLIED}
        assert {row.note for row in rows} == {"两处都采纳"}


class TestMtime:
    @pytest.mark.django_db(transaction=True)
    def test_stale_base_mtime_is_refused_with_409(self, bound: Any) -> None:
        lawyer, contract, file_path = bound()
        before = file_path.read_bytes()
        stale = file_path.stat().st_mtime - 3600
        patch_id = _collect(contract, CLAUSE_PAYMENT, PAYMENT_A, base_mtime=stale)

        with pytest.raises(ConflictError) as excinfo:
            apply_patches(patch_ids=[patch_id], user=lawyer)

        assert excinfo.value.code == "FILE_MODIFIED"
        assert file_path.read_bytes() == before
        assert ContractWritePatch.objects.get(patch_id=patch_id).status == PatchStatus.PROPOSED

    @pytest.mark.django_db(transaction=True)
    def test_two_different_base_mtimes_are_refused(self, bound: Any) -> None:
        """同一份文件上出现两个基准 mtime = 期间有人动过文件。"""
        lawyer, contract, file_path = bound()
        current = file_path.stat().st_mtime
        first = _collect(contract, CLAUSE_PAYMENT, PAYMENT_A, base_mtime=current)
        second = _collect(contract, CLAUSE_COURT, COURT_NEW, base_mtime=current - 3600)

        with pytest.raises(ConflictError) as excinfo:
            apply_patches(patch_ids=[first, second], user=lawyer)

        assert excinfo.value.code == "FILE_MODIFIED"


class TestApplyGuards:
    @pytest.mark.django_db(transaction=True)
    def test_cross_file_patch_ids_are_refused(self, bound: Any) -> None:
        lawyer, contract, _path = bound()
        patch_id = _collect(contract, CLAUSE_PAYMENT, PAYMENT_A)
        other = collect_patch(
            owner_kind="contract",
            owner_id=contract.id,
            subpath="1-合同/b.docx",
            original=CLAUSE_PAYMENT,
            replacement=PAYMENT_A,
        )

        with pytest.raises(ValidationException):
            apply_patches(patch_ids=[patch_id, other.patch_id], user=lawyer)

    @pytest.mark.django_db(transaction=True)
    def test_applied_patch_cannot_be_applied_again(self, bound: Any) -> None:
        lawyer, contract, _path = bound()
        patch_id = _collect(contract, CLAUSE_PAYMENT, PAYMENT_A)
        apply_patches(patch_ids=[patch_id], user=lawyer)

        with pytest.raises(ValidationException):
            apply_patches(patch_ids=[patch_id], user=lawyer)

    @pytest.mark.django_db(transaction=True)
    def test_missing_patch_id_is_refused_before_touching_disk(self, bound: Any) -> None:
        lawyer, _contract, file_path = bound()
        before = file_path.read_bytes()
        with pytest.raises(ValidationException):
            apply_patches(patch_ids=["不存在"], user=lawyer)
        assert file_path.read_bytes() == before

    @pytest.mark.django_db(transaction=True)
    def test_patch_whose_anchor_is_gone_refuses_whole_batch(self, bound: Any) -> None:
        """一条锚点找不到 → 整批不写（半批应用会让律师看到"改了一半"的文档）。"""
        lawyer, contract, file_path = bound()
        alive = _collect(contract, CLAUSE_PAYMENT, PAYMENT_A)
        gone = _collect(contract, "文档里没有这句话。", "新话。")
        before = file_path.read_bytes()

        with pytest.raises(ConflictError) as excinfo:
            apply_patches(patch_ids=[alive, gone], user=lawyer)

        assert excinfo.value.code == "PATCH_ANCHOR_MISSING"
        assert file_path.read_bytes() == before
        assert ContractWritePatch.objects.get(patch_id=alive).status == PatchStatus.PROPOSED


class TestDuplicate:
    @pytest.mark.django_db(transaction=True)
    def test_duplicate_patches_are_merged_not_written_twice(self, bound: Any) -> None:
        lawyer, contract, file_path = bound()
        first = _collect(contract, CLAUSE_PAYMENT, PAYMENT_A)
        second = _collect(contract, CLAUSE_PAYMENT, PAYMENT_A)

        result = apply_patches(patch_ids=[first, second], note="两栏撞了同一句", user=lawyer)

        kept, dropped = sorted([first, second])
        assert result["applied"] == [kept]
        assert result["merged"] == [dropped]
        assert ContractWritePatch.objects.get(patch_id=dropped).status == PatchStatus.MERGED
        # 文档里只出现一次（不是两份相同的修订叠在一起）
        assert _doc_text(file_path).count(PAYMENT_A) == 1
