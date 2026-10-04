from __future__ import annotations

import logging
import uuid
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import UploadedFile
from docx import Document
from docx.document import Document as DocumentType

from apps.contract_review.models.review_task import ProcessStep, ReviewTask, TaskStatus
from apps.contract_review.repositories.review_task_repository import ReviewTaskRepository
from apps.core.exceptions import ValidationException
from apps.core.filesystem.upload_paths import MediaEntity
from apps.core.llm.service import LLMService, get_llm_service
from apps.core.services.storage_service import sanitize_upload_filename, to_media_abs

from ..exceptions import ContractReviewError, ExtractionError
from ..extraction.content_extractor import ContentExtractor
from ..extraction.heading_numbering import HeadingNumbering
from ..extraction.title_extractor import TitleExtractor
from ..formatting.docx_formatter import DocxFormatter
from ..formatting.docx_revision_tool import DocxRevisionTool
from ..formatting.page_numbering import PageNumbering
from .contract_reviewer import ContractReviewer, ReviewResult
from .party_identifier import PartyIdentifier
from .typo_checker import TypoChecker

logger = logging.getLogger(__name__)


def _resolve_task_file(file_path: str, error_message: str) -> Path:  # pragma: no cover
    """把落库路径解析为 MEDIA_ROOT 下的绝对路径（兼容存量绝对路径数据）。"""
    try:
        return to_media_abs(file_path)
    except ValidationException as e:
        raise ContractReviewError(error_message) from e


class ReviewService:  # pragma: no cover
    """合同审查主编排服务"""

    def __init__(self) -> None:  # pragma: no cover
        self._repository = ReviewTaskRepository()

    def upload_contract(  # pragma: no cover
        self,
        file: UploadedFile,
        user: object,
        model_name: str = "",
    ) -> ReviewTask:
        """上传合同：验证 → 保存 → 提取内容 → 识别甲乙方 → 创建任务"""
        filename = file.name or "unknown.docx"
        if not filename.lower().endswith(".docx"):
            raise ContractReviewError("仅支持 .docx 格式文件")

        # 保存文件（落库协议：media 相对路径）
        task_id = uuid.uuid4()
        safe_name = sanitize_upload_filename(filename)
        rel_path = f"{MediaEntity.CONTRACT_REVIEW_UPLOADS}/{task_id}_{safe_name}"
        saved_name = default_storage.save(rel_path, file)
        save_path = to_media_abs(saved_name)

        # 提取内容 + 识别甲乙方
        extractor = ContentExtractor()
        identifier = PartyIdentifier()
        try:
            paragraphs = extractor.extract_paragraphs(save_path)
            parties = identifier.identify_parties(paragraphs)
        except ExtractionError as e:
            task = self._repository.create(
                id=task_id,
                user=user,
                original_file=saved_name,
                status=TaskStatus.EXTRACTION_FAILED,
                error_message=str(e),
                model_name=model_name,
            )
            return task

        # 提取标题
        title_extractor = TitleExtractor()
        doc = Document(str(save_path))
        title = title_extractor.extract_title(doc)

        task = self._repository.create(
            id=task_id,
            user=user,
            original_file=saved_name,
            contract_title=title or filename.rsplit(".", 1)[0],
            party_a=parties.get("party_a", ""),
            party_b=parties.get("party_b", ""),
            party_c=parties.get("party_c", ""),
            party_d=parties.get("party_d", ""),
            status=TaskStatus.PARTIES_IDENTIFIED,
            model_name=model_name,
        )
        return task

    def confirm_party(  # pragma: no cover
        self,
        task_id: uuid.UUID,
        represented_party: str,
        user: object,
        reviewer_name: str = "",
        selected_steps: list[str] | None = None,
        party_overrides: dict[str, str] | None = None,
    ) -> ReviewTask:
        """确认代表方，提交异步审查任务"""
        task = self._repository.get_by_id_required(task_id)
        if task.status not in (
            TaskStatus.PARTIES_IDENTIFIED,
            TaskStatus.EXTRACTION_FAILED,
        ):
            raise ContractReviewError(f"当前状态 {task.status} 不允许确认代表方")

        # 默认全选
        default_steps = ["typo_check", "format_document", "contract_review", "review_report"]
        steps = selected_steps if selected_steps else default_steps

        reviewer_name = reviewer_name.strip() or "法穿SI"

        # 构建更新字段
        update_fields: dict[str, object] = {
            "represented_party": represented_party,
            "reviewer_name": reviewer_name,
            "status": TaskStatus.CONFIRMED,
            "selected_steps": steps,
        }
        # 允许用户手动修正识别错误的当事人名称
        if party_overrides:
            for key in ("party_a", "party_b", "party_c", "party_d"):
                if key in party_overrides:
                    update_fields[key] = party_overrides[key]

        self._repository.update(task_id, **update_fields)

        # 提交异步任务
        from apps.core.tasking import submit_task

        submit_task(
            "apps.contract_review.services.review.review_service.process_review",
            str(task_id),
            timeout=1800,
        )
        logger.info("已提交审查任务: %s", task_id)
        return self._repository.get_by_id(task_id)  # type: ignore[return-value]

    def get_task_status(self, task_id: uuid.UUID) -> ReviewTask:  # pragma: no cover
        """查询任务状态"""
        return self._repository.get_by_id_required(task_id)

    def get_result_file(self, task_id: uuid.UUID) -> Path:  # pragma: no cover
        """获取结果文件路径"""
        task = self._repository.get_by_id_required(task_id)
        if task.status != TaskStatus.COMPLETED:
            raise ContractReviewError("任务尚未完成")
        path = _resolve_task_file(task.output_file, "结果文件不存在")
        if not path.exists():
            raise ContractReviewError("结果文件不存在")
        return path

    def get_original_file(self, task_id: uuid.UUID) -> Path:  # pragma: no cover
        """获取原始上传文件路径"""
        task = self._repository.get_by_id_required(task_id)
        path = _resolve_task_file(task.original_file, "原始文件不存在")
        if not path.exists():
            raise ContractReviewError("原始文件不存在")
        return path


def process_review(task_id_str: str) -> None:  # pragma: no cover
    """异步执行审查流水线（由 Django-Q2 调用）"""
    task_id = uuid.UUID(task_id_str)
    repository = ReviewTaskRepository()
    task = repository.get_by_id(task_id)
    if task is None:
        logger.warning("任务不存在，跳过: %s", task_id)
        return
    # 防止重复执行：已完成/已失败的任务直接跳过
    if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
        logger.warning("任务已终态 (%s)，跳过: %s", task.status, task_id)
        return
    repository.update(task_id, status=TaskStatus.PROCESSING)

    try:
        original_path = to_media_abs(task.original_file)
        doc = Document(str(original_path))
        extractor = ContentExtractor()
        extraction = extractor.extract_with_mapping(original_path)
        paragraphs = extraction.paragraphs

        llm: LLMService = get_llm_service()
        revision_tool = DocxRevisionTool()

        # 启用修订模式（Track Changes）
        revision_tool.enable_track_changes(doc)

        steps = getattr(task, "selected_steps", None) or [
            "typo_check",
            "format_document",
            "contract_review",
            "review_report",
        ]

        # Step 1: 标题提取（始终执行）
        _update_step(repository, task, ProcessStep.TITLE_EXTRACTION)
        title_extractor = TitleExtractor()
        title = title_extractor.extract_title(doc)
        if title:
            repository.update(task.id, contract_title=title)

        # Step 2: 错别字检测
        if "typo_check" in steps:
            _update_step(repository, task, ProcessStep.TYPO_CHECK)
            typo_checker = TypoChecker(llm)
            typos = typo_checker.check_typos(paragraphs, model_name=task.model_name)
            typo_applied = 0
            for typo in typos:
                applied = _apply_to_any_paragraph(
                    doc, revision_tool, typo.original, typo.corrected, author=task.reviewer_name
                )
                if applied:
                    typo_applied += 1
            logger.info("错别字修订: %d/%d 处成功", typo_applied, len(typos))

        # Step 3: 合同审查 + 评估报告（并行执行，两者互不依赖）
        need_review = "contract_review" in steps
        need_report = "review_report" in steps
        reviewer = ContractReviewer(llm)

        if need_review and need_report:
            _update_step(repository, task, ProcessStep.CONTRACT_REVIEW)
            reviews: list[ReviewResult] = []
            report = ""
            # 并行子任务失败不能只打日志就吞掉：全失败要标 FAILED，部分失败要留痕
            failed_kinds: list[str] = []
            failure_detail: list[str] = []

            def _run_review() -> list[ReviewResult]:  # pragma: no cover
                return reviewer.review_contract(
                    paragraphs,
                    task.represented_party,
                    task.party_a,
                    task.party_b,
                    model_name=task.model_name,
                )

            def _run_report() -> str:  # pragma: no cover
                return reviewer.generate_report(
                    paragraphs,
                    task.represented_party,
                    task.party_a,
                    task.party_b,
                    model_name=task.model_name,
                )

            with ThreadPoolExecutor(max_workers=2) as pool:
                futures: dict[Future[object], str] = {
                    pool.submit(_run_review): "review",
                    pool.submit(_run_report): "report",
                }
                for future in as_completed(futures):
                    kind = futures[future]
                    try:
                        if kind == "review":
                            reviews = future.result()  # type: ignore[assignment]
                        else:
                            report = future.result()
                    except Exception as e:
                        failed_kinds.append(kind)
                        failure_detail.append(f"{kind}: {e}")
                        logger.exception("并行任务 %s 失败", kind)

            # reviews 与 report 全为空说明并行任务毫无产出：抛错走外层 FAILED 分支，
            # 禁止继续往下产出空文档并虚报 COMPLETED
            if failed_kinds and not reviews and not report:
                raise ContractReviewError("合同审查与评估报告并行任务均失败: " + "; ".join(failure_detail))

            # 部分失败：任务仍可完成，但把失败明细写进 error_message 留痕（不覆盖成功产物）
            if failed_kinds:
                repository.update(
                    task.id,
                    error_message=f"{len(failed_kinds)} 项并行子任务失败: " + "; ".join(failure_detail),
                )

            review_applied = 0
            for rev in reviews:
                applied = _apply_to_any_paragraph(
                    doc, revision_tool, rev.original, rev.suggested, author=task.reviewer_name
                )
                if applied:
                    review_applied += 1
            logger.info("合同审查修订: %d/%d 处成功", review_applied, len(reviews))

            if report:
                repository.update(task.id, review_report=report)
                logger.info("评估报告已生成 (%d 字)", len(str(report)))

        elif need_review:
            _update_step(repository, task, ProcessStep.CONTRACT_REVIEW)
            reviews_only = reviewer.review_contract(
                paragraphs,
                task.represented_party,
                task.party_a,
                task.party_b,
                model_name=task.model_name,
            )
            review_applied = 0
            for rev in reviews_only:
                applied = _apply_to_any_paragraph(
                    doc, revision_tool, rev.original, rev.suggested, author=task.reviewer_name
                )
                if applied:
                    review_applied += 1
            logger.info("合同审查修订: %d/%d 处成功", review_applied, len(reviews_only))

        elif need_report:
            report_only = reviewer.generate_report(
                paragraphs,
                task.represented_party,
                task.party_a,
                task.party_b,
                model_name=task.model_name,
            )
            if report_only:
                repository.update(task.id, review_report=report_only)
                logger.info("评估报告已生成 (%d 字)", len(report_only))

        # Step 4: 格式标准化
        if "format_document" in steps:
            _update_step(repository, task, ProcessStep.FORMAT_DOCUMENT)
            DocxFormatter().format_document(doc)

            _update_step(repository, task, ProcessStep.PAGE_NUMBERING)
            PageNumbering().standardize(doc)

            _update_step(repository, task, ProcessStep.HEADING_NUMBERING)
            HeadingNumbering(llm).apply_numbering(doc, model_name=task.model_name)

        # 保存输出文件（经 default_storage 落盘，落库存相对路径）
        output_name = title_extractor.generate_output_filename(
            task.contract_title,
            task_id=str(task.id),
        )
        output_rel = f"{MediaEntity.CONTRACT_REVIEW_OUTPUT}/{sanitize_upload_filename(output_name)}"
        buffer = BytesIO()
        doc.save(buffer)
        saved_name = default_storage.save(output_rel, ContentFile(buffer.getvalue()))

        repository.update(
            task.id,
            output_file=saved_name,
            status=TaskStatus.COMPLETED,
            current_step="",
        )
        logger.info("审查完成: %s -> %s", task_id, saved_name)

    except Exception as e:
        logger.exception("审查任务失败: %s", task_id)
        repository.update(
            task_id,
            status=TaskStatus.FAILED,
            error_message=str(e),
        )


def _update_step(repository: ReviewTaskRepository, task: ReviewTask, step: str) -> None:  # pragma: no cover
    repository.update(task.id, current_step=step)


def _apply_to_any_paragraph(  # pragma: no cover
    doc: DocumentType, tool: DocxRevisionTool, original: str, replacement: str, author: str = ""
) -> bool:
    """遍历所有段落查找原文并应用修订，不依赖 LLM 返回的段落索引"""
    for para in doc.paragraphs:
        if original in para.text:
            if tool.apply_revision(para, original, replacement, author=author or None):
                return True
    return False
