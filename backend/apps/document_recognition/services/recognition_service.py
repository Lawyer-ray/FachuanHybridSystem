"""
法院文书智能识别主服务

协调各子服务完成文书识别流程。

Requirements: 4.5, 4.6, 4.7, 6.2, 7.1, 7.2, 7.3, 8.1, 8.2, 8.3, 8.4
"""

import logging
from datetime import date, datetime
from typing import Any

from apps.core.exceptions import RecognitionTimeoutError, ServiceUnavailableError, ValidationException
from apps.core.exceptions.error_codes import TEXT_EXTRACTION_FAILED
from apps.core.services.filename_template_service import FilenameTemplateService

from .data_classes import BindingResult, DocumentType, RecognitionResponse, RecognitionResult

logger = logging.getLogger("apps.document_recognition")


class CourtDocumentRecognitionService:
    """
    法院文书智能识别服务（协调器）

    协调文本提取、文书分类、信息提取、案件绑定等子服务，
    完成完整的文书识别流程。

    Requirements: 4.5, 4.6, 4.7, 6.2, 7.1, 7.2, 7.3, 8.1, 8.2, 8.3, 8.4
    """

    def __init__(
        self,
        text_extraction: Any = None,
        classifier: Any = None,
        extractor: Any = None,
        binding_service: Any = None,
        document_renamer: Any = None,
        matching_service: Any = None,
    ) -> None:
        """
        初始化服务

        Args:
            text_extraction: 文本提取服务（可选，用于依赖注入）
            classifier: 文书分类器（可选，用于依赖注入）
            extractor: 信息提取器（可选，用于依赖注入）
            binding_service: 案件绑定服务（可选，用于依赖注入）
            document_renamer: 文书重命名服务（可选，用于依赖注入）
            matching_service: 案件严格匹配服务（可选，用于依赖注入）
        """
        self._text_extraction = text_extraction
        self._classifier = classifier
        self._extractor = extractor
        self._binding_service = binding_service
        self._document_renamer = document_renamer
        self._matching_service = matching_service
        # per-run 共享 LLM 分析：分类与信息提取共用同一次结构化调用。
        # 仅当协作者真正消费 lookup 时才发起 LLM 请求（协作者被 mock 的单测不会触发）。
        # 注意：本服务若被复用（如旧单例装配），run 状态会在 recognize_document* 入口复位，
        # 观测性取「最近一次」outcome 而非缓存首个，避免跨任务串扰。
        self._analysis_cache: dict[str, Any] = {}
        self._last_outcome: Any = None
        # 本次 run 指定的模型（用户上传时选择；None 走统一 LLM 层默认）
        self._run_llm_model: str | None = None

    def _reset_run_state(self) -> None:
        """每次识别入口复位观测性游标。

        只复位 ``_last_outcome``、不清空 ``_analysis_cache``：缓存是 run 内
        memoize（分类/提取/候选共享同一次 LLM 调用），入口清空会把协作者已
        写入/测试预置的分析作废。实例复用的跨任务隔离由 adapter 的
        per-call 构造保证（见 adapter.py）。
        """
        self._last_outcome = None
        self._run_llm_model = None

    def _analysis_lookup(self, text: str) -> Any:
        """按原文 memoize 的共享结构化分析（document_analyzer）。"""
        if text in self._analysis_cache:
            return self._analysis_cache[text]
        from .document_analyzer import analyze_document

        outcome = analyze_document(text, model=self._run_llm_model)
        self._analysis_cache[text] = outcome
        self._last_outcome = outcome
        return outcome

    def _analysis_observability(self) -> dict[str, Any]:
        """汇总本次识别的 LLM 可观测性信息（未触发分析时全为默认值）。"""
        from .document_analyzer import DocumentAnalysisOutcome

        outcome = self._last_outcome
        if not isinstance(outcome, DocumentAnalysisOutcome):
            return {"llm_model": None, "llm_backend": None, "llm_latency_ms": None, "degraded": False}
        return {
            "llm_model": outcome.model,
            "llm_backend": outcome.backend,
            "llm_latency_ms": outcome.latency_ms,
            "degraded": not outcome.ok,
        }

    @property
    def text_extraction(self) -> Any:
        """延迟加载文本提取服务"""
        if self._text_extraction is None:
            from .text_extraction_service import TextExtractionService

            self._text_extraction = TextExtractionService()
        return self._text_extraction

    @property
    def classifier(self) -> Any:
        """延迟加载文书分类器（注入共享分析，分类与提取共用一次 LLM 调用）"""
        if self._classifier is None:
            from .document_classifier import DocumentClassifier

            self._classifier = DocumentClassifier(analysis_lookup=self._analysis_lookup)
        return self._classifier

    @property
    def extractor(self) -> Any:
        """延迟加载信息提取器（注入共享分析，分类与提取共用一次 LLM 调用）"""
        if self._extractor is None:
            from .info_extractor import InfoExtractor

            self._extractor = InfoExtractor(analysis_lookup=self._analysis_lookup)
        return self._extractor

    @property
    def binding_service(self) -> Any:
        """延迟加载案件绑定服务"""
        if self._binding_service is None:
            from .case_binding_service import CaseBindingService

            self._binding_service = CaseBindingService()
        return self._binding_service

    @property
    def document_renamer(self) -> Any:
        """延迟加载文书重命名服务"""
        if self._document_renamer is None:
            from apps.automation.services.sms.document_renamer import DocumentRenamer

            self._document_renamer = DocumentRenamer()
        return self._document_renamer

    @property
    def matching_service(self) -> Any:
        """延迟加载案件严格匹配服务"""
        if self._matching_service is None:
            from .case_matching_service import DocumentCaseMatchingService

            self._matching_service = DocumentCaseMatchingService()
        return self._matching_service

    def _cached_analysis(self, text: str) -> Any:
        """读取已缓存的分析结果；不触发新的 LLM 调用（协作者被 mock 时无缓存）。"""
        outcome = self._analysis_cache.get(text)
        return outcome.analysis if outcome is not None else None

    def _build_date_candidates(self, text: str, doc_type: Any) -> list[dict[str, Any]]:
        """构建多日期候选（LLM key_events + 正则候选合并去重），序列化为 dict 列表。"""
        from .date_candidate_service import build_date_candidates

        drafts = build_date_candidates(text, self._cached_analysis(text), doc_type)
        return [draft.to_dict() for draft in drafts]

    def _extract_doc_info(self, doc_type: Any, text: str) -> tuple[Any, Any]:
        """根据文书类型提取案号和关键时间"""
        case_number = None
        key_time = None
        if doc_type == DocumentType.SUMMONS:
            info = self.extractor.extract_summons_info(text)
            case_number = info.get("case_number")
            key_time = info.get("court_time")
        elif doc_type == DocumentType.EXECUTION_RULING:
            info = self.extractor.extract_execution_info(text)
            case_number = info.get("case_number")
            key_time = info.get("preservation_deadline")
        return case_number, key_time

    def _build_binding(
        self,
        doc_type: Any,
        case_number: Any,
        file_path: str,
        extraction_text: str,
        user: Any,
        date_count: int = 0,
        *,
        prebound_case_id: int | None = None,
        prebound_case_log_id: int | None = None,
    ) -> tuple[Any, str]:
        """绑定案件，返回 (binding_result, renamed_file_path)

        三种路径：
        1. 管线预绑定（法院短信等入口已建好 case/case_log）：跳过匹配/重命名/
           新建日志/通知，直接返回成功结果（提醒锚定短信管线已建的日志）。
        2. 有案号：严格匹配（规范化精确 + 在办 + 唯一）命中 → 重命名 + 建日志绑定；
           未命中 → PENDING_MANUAL_BINDING，由前端推荐卡片 + 搜索转人工。
        3. 无案号：CASE_NUMBER_NOT_FOUND，转人工选择案件。
        提醒一律不在绑定期写入（只走日期候选人工确认接口）。
        """
        renamed_file_path = file_path

        if prebound_case_log_id:
            case_name = ""
            if prebound_case_id:
                case_dto = self.binding_service.case_service.get_case_by_id_internal(prebound_case_id)
                if case_dto:
                    case_name = case_dto.name
            binding = BindingResult.success_result(
                case_id=prebound_case_id, case_name=case_name, case_log_id=prebound_case_log_id
            )
            binding.message = "案件已由来源管线（法院短信）绑定"
            return binding, renamed_file_path

        if not case_number:
            return (
                BindingResult.failure_result(
                    message="未识别到案号，请在识别结果中手动选择案件绑定",
                    error_code="CASE_NUMBER_NOT_FOUND",
                ),
                renamed_file_path,
            )

        match = self.matching_service.auto_match(str(case_number))
        if match is None:
            return (
                BindingResult.failure_result(
                    message="未匹配到唯一的在办案件，请在识别结果中手动选择案件绑定",
                    error_code="PENDING_MANUAL_BINDING",
                ),
                renamed_file_path,
            )

        case_id, case_name = match
        renamed_file_path = self._rename_document(file_path=file_path, document_type=doc_type, case_name=case_name)
        log_content = self.binding_service.format_log_content(
            document_type=doc_type, case_number=case_number, raw_text=extraction_text, date_count=date_count
        )
        binding = self.binding_service.bind_document_to_case(
            case_id=case_id,
            document_type=doc_type,
            content=log_content,
            file_path=renamed_file_path,
            user=user,
        )
        return binding, renamed_file_path

    def recognize_document(
        self,
        file_path: str,
        user: Any | None = None,
        *,
        prebound_case_id: int | None = None,
        prebound_case_log_id: int | None = None,
        llm_model: str | None = None,
    ) -> RecognitionResponse:
        """识别文书并绑定案件

        Args:
            file_path: 文书文件路径
            user: 当前用户
            prebound_case_id: 管线预绑定的案件 ID（法院短信入口，可选）
            prebound_case_log_id: 管线预绑定的案件日志 ID（提醒锚点，可选）
            llm_model: 指定识别模型（可选，None 走统一 LLM 层默认）

        Requirements: 4.5, 4.6, 4.7, 6.2, 8.1, 8.2, 8.3, 8.4
        """
        logger.info(
            "开始识别文书",
            extra={
                "action": "recognize_document",
                "file_path": file_path,
                "user_id": getattr(user, "id", None) if user else None,
                "prebound": prebound_case_log_id is not None,
                "llm_model": llm_model,
            },
        )
        self._reset_run_state()
        self._run_llm_model = llm_model

        try:
            extraction_result = self.text_extraction.extract_text(file_path)

            if not extraction_result.success or not extraction_result.text.strip():
                logger.warning("文本提取失败或内容为空", extra={"action": "recognize_document", "file_path": file_path})
                return RecognitionResponse(
                    recognition=RecognitionResult(
                        document_type=DocumentType.OTHER,
                        case_number=None,
                        key_time=None,
                        raw_text="",
                        confidence=0.0,
                        extraction_method=extraction_result.extraction_method,
                    ),
                    binding=BindingResult.failure_result(
                        message="无法从文书中提取文字",
                        error_code=TEXT_EXTRACTION_FAILED,
                    ),
                    file_path=file_path,
                )

            doc_type, confidence = self.classifier.classify(extraction_result.text)
            case_number, key_time = self._extract_doc_info(doc_type, extraction_result.text)
            date_candidates = self._build_date_candidates(extraction_result.text, doc_type)
            if key_time is None and date_candidates:
                # 候选落库时按本地时区 make_aware；key_time 兜底取首选候选，同样补时区
                key_time = datetime.fromisoformat(date_candidates[0]["due_at"])
                if key_time.tzinfo is None:
                    from django.utils.timezone import make_aware

                    key_time = make_aware(key_time)
            cached_analysis = self._cached_analysis(extraction_result.text)
            party_names = [
                str(p).strip() for p in (getattr(cached_analysis, "party_names", None) or []) if str(p).strip()
            ]

            recognition = RecognitionResult(
                document_type=doc_type,
                case_number=case_number,
                key_time=key_time,
                raw_text=extraction_result.text,
                confidence=confidence,
                extraction_method=extraction_result.extraction_method,
                **self._analysis_observability(),
            )

            binding, renamed_file_path = self._build_binding(
                doc_type,
                case_number,
                file_path,
                extraction_result.text,
                user,
                date_count=len(date_candidates),
                prebound_case_id=prebound_case_id,
                prebound_case_log_id=prebound_case_log_id,
            )

            logger.info(
                "文书识别完成",
                extra={
                    "action": "recognize_document",
                    "file_path": file_path,
                    "renamed_file_path": renamed_file_path,
                    "document_type": doc_type.value,
                    "case_number": case_number,
                    "date_candidate_count": len(date_candidates),
                    "binding_success": binding.success if binding else None,
                },
            )

            return RecognitionResponse(
                recognition=recognition,
                binding=binding,
                file_path=renamed_file_path,
                date_candidates=date_candidates,
                party_names=party_names,
            )

        except (ValidationException, ServiceUnavailableError, RecognitionTimeoutError):
            raise
        except Exception as e:
            logger.error(
                "文书识别失败: %s",
                e,
                extra={
                    "action": "recognize_document",
                    "file_path": file_path,
                    "error_type": type(e).__name__,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise

    def recognize_document_from_text(self, text: str, *, llm_model: str | None = None) -> RecognitionResult:
        """
        从已提取的文本识别文书

        Args:
            text: 文书文本内容

        Returns:
            RecognitionResult 对象

        Raises:
            ValidationException: 文本内容为空
            ServiceUnavailableError: AI 服务不可用
            RecognitionTimeoutError: 识别超时

        Requirements: 7.2, 7.3
        """
        if not text or not text.strip():
            logger.warning("文本内容为空", extra={"action": "recognize_document_from_text", "result": "empty_text"})
            raise ValidationException(
                message="文本内容不能为空", code="EMPTY_TEXT", errors={"text": "请提供有效的文书文本"}
            )

        logger.info("文本识别开始", extra={"action": "recognize_document_from_text", "text_length": len(text)})
        self._run_llm_model = llm_model
        self._reset_run_state()

        try:
            # 1. 分类文书类型
            doc_type, confidence = self.classifier.classify(text)

            # 2. 提取关键信息
            case_number = None
            key_time = None

            if doc_type == DocumentType.SUMMONS:
                info = self.extractor.extract_summons_info(text)
                case_number = info.get("case_number")
                key_time = info.get("court_time")
            elif doc_type == DocumentType.EXECUTION_RULING:
                info = self.extractor.extract_execution_info(text)
                case_number = info.get("case_number")
                key_time = info.get("preservation_deadline")

            result = RecognitionResult(
                document_type=doc_type,
                case_number=case_number,
                key_time=key_time,
                raw_text=text,
                confidence=confidence,
                extraction_method="text_input",
                **self._analysis_observability(),
            )

            logger.info(
                "文本识别完成",
                extra={
                    "action": "recognize_document_from_text",
                    "document_type": doc_type.value,
                    "case_number": case_number,
                    "confidence": confidence,
                },
            )

            return result

        except (ValidationException, ServiceUnavailableError, RecognitionTimeoutError):
            raise
        except Exception as e:
            logger.error(
                "文本识别失败: %s",
                e,
                extra={"action": "recognize_document_from_text", "error_type": type(e).__name__, "error": str(e)},
                exc_info=True,
            )
            raise

    def _rename_document(self, file_path: str, document_type: DocumentType, case_name: str) -> str:  # pragma: no cover
        """
        重命名文书文件

        格式：{主标题}（{案件名称}）_{YYYYMMDD}收.pdf

        Args:
            file_path: 原始文件路径
            document_type: 文书类型
            case_name: 案件名称

        Returns:
            重命名后的文件路径，失败时返回原路径
        """
        try:
            # 根据文书类型确定标题
            title_map = {
                DocumentType.SUMMONS: "传票",
                DocumentType.EXECUTION_RULING: "执行裁定书",
                DocumentType.OTHER: "司法文书",
            }
            title = title_map.get(document_type, "司法文书")

            # 生成新文件名
            new_filename = self.document_renamer.generate_filename(
                title=title, case_name=case_name, received_date=date.today()
            )

            # 构建新文件路径（通用碰撞处理）
            from pathlib import Path

            original_path = Path(file_path)
            new_path, _ = FilenameTemplateService.get_unique_filepath(original_path.parent, new_filename)

            # 重命名文件
            original_path.rename(new_path)

            logger.info(
                "文书重命名成功",
                extra={
                    "action": "rename_document",
                    "original_path": file_path,
                    "new_path": str(new_path),
                    "document_type": document_type.value,
                    "case_name": case_name,
                },
            )
            return str(new_path)

        except Exception as e:
            logger.warning(
                "文书重命名失败，保留原文件名",
                extra={"action": "rename_document", "file_path": file_path, "error": str(e)},
            )
            return file_path
