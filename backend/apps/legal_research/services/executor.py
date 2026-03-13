from __future__ import annotations

import inspect
import logging
import re
from typing import Any

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.legal_research.models import LegalResearchResult, LegalResearchTask, LegalResearchTaskStatus
from apps.legal_research.services.similarity_service import CaseSimilarityService
from apps.legal_research.services.sources import CaseDetail, get_case_source_client

logger = logging.getLogger(__name__)


class LegalResearchExecutor:
    CANDIDATE_BATCH_SIZE = 100
    PAGE_SIZE_HINT = 20
    MAX_PAGE_WINDOW = 2000

    def run(self, *, task_id: str) -> dict[str, Any]:
        task, early_result = self._acquire_task(task_id=task_id)
        if early_result is not None:
            return early_result
        if task is None:
            logger.error("案例检索任务获取失败", extra={"task_id": task_id})
            return {"task_id": task_id, "status": "failed", "error": "任务不存在"}

        similarity = CaseSimilarityService()

        session = None
        try:
            source_client = get_case_source_client(task.source)
            session = source_client.open_session(
                username=task.credential.account,
                password=task.credential.password,
                login_url=task.credential.url or None,
            )

            scanned = 0
            matched = 0
            fetched = 0

            while fetched < task.max_candidates and matched < task.target_count:
                batch_size = min(self.CANDIDATE_BATCH_SIZE, task.max_candidates - fetched)
                items = self._fetch_candidate_batch(
                    source_client=source_client,
                    session=session,
                    keyword=task.keyword,
                    offset=fetched,
                    batch_size=batch_size,
                )

                if not items:
                    if fetched == 0:
                        self._mark_completed(task, message="未检索到候选案例")
                        return {"task_id": str(task.id), "status": task.status}
                    break

                fetched += len(items)
                task.candidate_count = fetched
                task.message = f"已获取候选案例 {fetched}/{task.max_candidates} 篇（本批 {len(items)} 篇）"
                task.save(update_fields=["candidate_count", "message", "updated_at"])

                for item in items:
                    if matched >= task.target_count:
                        break

                    scanned += 1

                    detail = source_client.fetch_case_detail(session=session, item=item)
                    sim = similarity.score_case(
                        keyword=task.keyword,
                        case_summary=task.case_summary,
                        title=detail.title,
                        case_digest=detail.case_digest,
                        content_text=detail.content_text,
                        model=task.llm_model or None,
                    )

                    if not task.llm_model and sim.model:
                        task.llm_model = sim.model

                    if sim.score >= task.min_similarity_score:
                        pdf = source_client.download_pdf(session=session, detail=detail)
                        if pdf is None:
                            logger.info(
                                "案例命中但PDF下载失败，跳过",
                                extra={"task_id": str(task.id), "doc_id": detail.doc_id_raw},
                            )
                        else:
                            matched += 1
                            self._save_result(task=task, detail=detail, similarity=sim, rank=matched, pdf=pdf)

                    self._update_progress(task=task, scanned=scanned, matched=matched)

            if matched >= task.target_count:
                self._mark_completed(task, message=f"达到目标，命中 {matched}/{task.target_count} 篇相似案例")
            elif scanned >= task.max_candidates:
                self._mark_completed(
                    task,
                    message=(
                        f"达到最大扫描上限 {task.max_candidates}，"
                        f"命中 {matched}/{task.target_count}，未达到目标"
                    ),
                )
            else:
                self._mark_completed(
                    task,
                    message=(
                        f"候选案例已扫描完毕（共 {task.candidate_count} 篇），"
                        f"命中 {matched}/{task.target_count}，未达到目标"
                    ),
                )

            return {
                "task_id": str(task.id),
                "status": task.status,
                "scanned_count": task.scanned_count,
                "matched_count": task.matched_count,
            }
        except Exception as e:
            logger.exception("案例检索任务失败", extra={"task_id": str(task.id)})
            self._mark_failed(task, str(e))
            return {
                "task_id": str(task.id),
                "status": "failed",
                "error": str(e),
            }
        finally:
            if session is not None:
                session.close()

    @staticmethod
    def _acquire_task(task_id: str) -> tuple[LegalResearchTask | None, dict[str, Any] | None]:
        now = timezone.now()
        updated = LegalResearchTask.objects.filter(
            id=task_id,
            status__in=[LegalResearchTaskStatus.PENDING, LegalResearchTaskStatus.QUEUED],
        ).update(
            status=LegalResearchTaskStatus.RUNNING,
            progress=0,
            error="",
            message="任务已启动",
            started_at=now,
            finished_at=None,
            updated_at=now,
        )

        task = (
            LegalResearchTask.objects.select_related("created_by", "credential", "credential__lawyer")
            .filter(id=task_id)
            .first()
        )
        if task is None:
            logger.error("案例检索任务不存在", extra={"task_id": task_id})
            return None, {"task_id": task_id, "status": "failed", "error": "任务不存在"}

        if updated == 1:
            return task, None

        if task.status in (
            LegalResearchTaskStatus.COMPLETED,
            LegalResearchTaskStatus.FAILED,
            LegalResearchTaskStatus.CANCELLED,
        ):
            return None, {"task_id": str(task.id), "status": task.status}

        if task.status == LegalResearchTaskStatus.RUNNING:
            return None, {"task_id": str(task.id), "status": task.status, "message": "任务已在执行中"}

        if task.status == LegalResearchTaskStatus.QUEUED:
            return None, {"task_id": str(task.id), "status": task.status, "message": "任务仍在排队中"}

        return None, {"task_id": str(task.id), "status": task.status, "message": "任务状态已变更，跳过本次执行"}

    @staticmethod
    def _mark_completed(task: LegalResearchTask, *, message: str) -> None:
        task.status = LegalResearchTaskStatus.COMPLETED
        task.progress = 100
        task.message = message
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "progress", "message", "finished_at", "updated_at"])

    @staticmethod
    def _mark_failed(task: LegalResearchTask, error_message: str) -> None:
        task.status = LegalResearchTaskStatus.FAILED
        task.message = "任务执行失败"
        task.error = error_message
        task.finished_at = timezone.now()
        task.save(update_fields=["status", "message", "error", "finished_at", "updated_at"])

    @classmethod
    def _update_progress(cls, *, task: LegalResearchTask, scanned: int, matched: int) -> None:
        total = max(task.max_candidates, 1)
        progress = min(95, int(scanned * 100 / total))
        task.scanned_count = scanned
        task.matched_count = matched
        task.progress = progress
        task.message = f"扫描 {scanned}/{task.max_candidates}，已获取候选 {task.candidate_count}，命中 {matched}/{task.target_count}"
        task.save(update_fields=["scanned_count", "matched_count", "progress", "message", "updated_at", "llm_model"])

    @classmethod
    def _fetch_candidate_batch(
        cls,
        *,
        source_client: Any,
        session: Any,
        keyword: str,
        offset: int,
        batch_size: int,
    ) -> list[Any]:
        search_cases = source_client.search_cases
        max_pages = cls._estimate_max_pages(offset=offset, batch_size=batch_size)
        signature = inspect.signature(search_cases)
        if "offset" in signature.parameters:
            return search_cases(
                session=session,
                keyword=keyword,
                max_candidates=batch_size,
                max_pages=max_pages,
                offset=offset,
            )

        # 兼容尚未实现 offset 的旧检索源：扩大上限后截取窗口。
        window = search_cases(
            session=session,
            keyword=keyword,
            max_candidates=offset + batch_size,
            max_pages=max_pages,
        )
        return window[offset : offset + batch_size]

    @classmethod
    def _estimate_max_pages(cls, *, offset: int, batch_size: int) -> int:
        required = ((offset + batch_size - 1) // cls.PAGE_SIZE_HINT) + 1
        return max(10, min(cls.MAX_PAGE_WINDOW, required + 2))

    @staticmethod
    @transaction.atomic
    def _save_result(
        *,
        task: LegalResearchTask,
        detail: CaseDetail,
        similarity: Any,
        rank: int,
        pdf: tuple[bytes, str],
    ) -> None:
        pdf_bytes, filename = pdf
        result, _ = LegalResearchResult.objects.get_or_create(
            task=task,
            source_doc_id=detail.doc_id_unquoted,
            defaults={
                "rank": rank,
                "source_url": detail.detail_url,
                "title": detail.title,
                "court_text": detail.court_text,
                "document_number": detail.document_number,
                "judgment_date": detail.judgment_date,
                "case_digest": detail.case_digest,
                "similarity_score": similarity.score,
                "match_reason": similarity.reason,
                "metadata": {
                    "search_id": detail.search_id,
                    "module": detail.module,
                    "source_doc_id_raw": detail.doc_id_raw,
                },
            },
        )

        if not result.pdf_file:
            safe_filename = LegalResearchExecutor._sanitize_pdf_filename(filename, fallback=detail.doc_id_unquoted)
            result.pdf_file.save(safe_filename, ContentFile(pdf_bytes), save=False)

        result.rank = rank
        result.source_url = detail.detail_url
        result.title = detail.title
        result.court_text = detail.court_text
        result.document_number = detail.document_number
        result.judgment_date = detail.judgment_date
        result.case_digest = detail.case_digest
        result.similarity_score = similarity.score
        result.match_reason = similarity.reason
        result.updated_at = timezone.now()
        result.save()

    @staticmethod
    def _sanitize_pdf_filename(filename: str, *, fallback: str) -> str:
        name = (filename or "").replace("\\", "/").split("/")[-1].strip()
        if not name.lower().endswith(".pdf"):
            name = f"{name}.pdf"

        stem = name[:-4]
        stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._")
        if not stem:
            stem = re.sub(r"[^A-Za-z0-9._-]+", "_", fallback or "case").strip("._") or "case"

        # 上传路径里已包含 task_id/result_id，文件名需要显著收敛以避免超长。
        return f"{stem[:120]}.pdf"
