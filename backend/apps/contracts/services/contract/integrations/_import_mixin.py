"""确认导入与学习（``ContractFolderScanService`` 的 确认导入 / 监督卡检测 / 作废票标记 / 导入纠错学习）。

从 ``folder_scan_service.py`` 按子域拆出的 mixin，**方法体仍定义在宿主模块的语义下**：
本模块不持有任何业务名引用，一律经 ``self._host`` 回查 ``folder_scan_service`` 的模块 globals。

.. important::
   在本文件里**禁止**直接写 ``Contract`` / ``Path`` / ``ContractFolderScanSession`` 等裸名——
   它们在本模块 globals 里不存在，会 ``NameError``；且测试 patch 的是**宿主模块的绑定位置**
   （``folder_scan_service.Contract`` 等 53 处），只有经 ``self._host`` 回查才能命中。
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from ._scan_service_contract import _ScanServiceContract

logger = logging.getLogger(__name__)


class _ImportMixin(_ScanServiceContract):
    """子域 mixin：具体方法见 ``folder_scan_service.ContractFolderScanService``。"""

    def confirm_import(
        self,
        *,
        contract_id: int,
        session_id: UUID,
        items: list[dict[str, Any]],
        work_log_suggestions: list[dict[str, str]] | None = None,
        storage_provider: Any | None = None,
    ) -> dict[str, Any]:  # pragma: no cover
        session = self.get_session(contract_id=contract_id, session_id=session_id)
        if storage_provider is None:
            storage_provider = self._resolve_session_storage_provider(session)
        result = self._import_pipeline.confirm_import(
            contract_id=contract_id,
            session=session,
            items=items,
            work_log_suggestions=work_log_suggestions,
            storage_provider=storage_provider,
            learn_from_correction_fn=self._learn_from_import_correction,
        )

        # 同步→案件信息回填：裁判文书提取结果按选中项追加写入关联案件
        # （案号/法院去重新增、空字段回填，多阶段共存；失败不影响导入）
        try:
            extractions = list((session.result_payload or {}).get("case_info_extractions") or [])
            selected_paths = {str(i.get("source_path") or "") for i in items if i.get("selected")}
            if extractions:
                contract = self._host.Contract.objects.get(pk=contract_id)
                result["case_info_apply"] = self._host.apply_case_info_to_contract(
                    contract, extractions, selected_paths=selected_paths
                )
        except Exception:
            logger.exception("case_info_apply_failed", extra={"contract_id": contract_id})

        # 同步→检测监督卡 串联：导入完成后立即检测合同 PDF 末页监督卡
        # OCR 失败不影响导入结果（异常被吞，导入数据随外层事务正常提交）
        supervision_result = self._auto_detect_supervision_card(contract_id)
        result["supervision_card_detection"] = supervision_result
        return result

    def _auto_detect_supervision_card(self, contract_id: int) -> dict[str, Any]:
        """导入完成后自动检测监督卡，失败返回未触发状态。"""
        try:
            from apps.contracts.services.archive.supervision_card_extractor import SupervisionCardExtractor

            contract = self._host.Contract.objects.get(pk=contract_id)
            detect_result = SupervisionCardExtractor().detect_and_extract(contract)
            found = bool(detect_result.get("found"))
            if found:
                logger.info(
                    "supervision_card_auto_detected",
                    extra={"contract_id": contract_id, "page_number": detect_result.get("page_number")},
                )
            return {
                "triggered": True,
                "found": found,
                "extracted_count": 1 if found else 0,
                "detail": detect_result,
            }
        except Exception:
            logger.exception("supervision_card_auto_detect_failed", extra={"contract_id": contract_id})
            return {"triggered": False, "found": False, "extracted_count": 0, "error": "检测失败"}

    def _mark_voided_candidates(self, candidates: list[dict[str, Any]]) -> int:
        """闸 2：把作废红票候选标为不可导入，返回命中数。

        目录级的 `已冲红/` 已由 ``_ALWAYS_EXCLUDE_DIR_KEYWORDS`` 挡在扫描外，这里是第二道：
        历史扫描会话、手工传参、或有人在发票目录根下丢了一份红票副本时，候选里仍可能
        混进作废票。判据只能是**命名事实**（文件名含「红字开具」）——扫描阶段手里没有
        ``Invoice`` 记录可查，而这张文件的归属恰恰是本步骤要定的。

        只改候选字典，不删候选：人要能在弹窗里看到“这张被跳过了”，而不是它凭空消失。
        """
        skipped = 0
        for candidate in candidates:
            if not self._host._looks_voided_filename(str(candidate.get("filename") or "")):
                continue
            candidate["selected"] = False
            candidate["archive_item_code"] = ""
            candidate["voided_skipped"] = True
            skipped += 1
        return skipped

    def _learn_from_import_correction(
        self,
        *,
        candidate: dict[str, Any],
        actual_archive_item_code: str,
        contract_id: int,
    ) -> None:
        """导入确认时自动学习：如果用户修改了 archive_item_code，记录为学习规则。"""
        if not actual_archive_item_code:
            return

        # 获取扫描时分类器预测的 archive_item_code
        predicted_code = str(candidate.get("archive_item_code") or "").strip()
        if predicted_code == actual_archive_item_code:
            return  # 用户没修改，无需学习

        # 只对案件材料学习
        if str(candidate.get("suggested_category") or "") != "case_material":
            return

        filename = str(candidate.get("filename") or "")
        if not filename:
            return

        try:
            from apps.contracts.models import ArchiveClassificationRule
            from apps.contracts.services.archive.category_mapping import get_archive_category
            from apps.contracts.services.archive.learning_service import extract_keywords
            from apps.contracts.services.contract.integrations.archive_classifier import invalidate_db_rules_cache

            contract = self._host.Contract.objects.filter(id=contract_id).values_list("case_type", flat=True).first()
            if not contract:
                return
            archive_category = self._host.get_archive_category(contract)
            if not archive_category:
                return

            keywords = extract_keywords(filename)
            learned_any = False
            for kw in keywords:
                # 跳过歧义关键词：如果已有规则映射到不同 code，不覆盖
                existing = (
                    ArchiveClassificationRule.objects.filter(
                        archive_category=archive_category,
                        filename_keyword=kw,
                    )
                    .exclude(archive_item_code=actual_archive_item_code)
                    .first()
                )
                if existing:
                    continue

                _, created = ArchiveClassificationRule.objects.get_or_create(
                    archive_category=archive_category,
                    filename_keyword=kw,
                    defaults={
                        "archive_item_code": actual_archive_item_code,
                        "source": "manual",
                        "hit_count": 1,
                    },
                )
                if created:
                    learned_any = True

            # 学习完成后刷新缓存，确保新规则立即生效
            if learned_any:
                invalidate_db_rules_cache()
        except (OSError, RuntimeError, ValueError):
            logger.exception("learn_from_import_correction_failed")
