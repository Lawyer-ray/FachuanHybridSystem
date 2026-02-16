"""
法院文书智能识别主服务

协调各子服务完成文书识别流程。

Requirements: 4.5, 4.6, 4.7, 6.2, 7.1, 7.2, 7.3, 8.1, 8.2, 8.3, 8.4
"""
import logging
from datetime import date
from typing import Any, Optional

from apps.core.exceptions import (
    ValidationException,
    ServiceUnavailableError,
    RecognitionTimeoutError,
)

from .data_classes import (
    DocumentType,
    RecognitionResult,
    RecognitionResponse,
    BindingResult,
)

logger = logging.getLogger("apps.automation")


class CourtDocumentRecognitionService:
    """
    法院文书智能识别服务（协调器）
    
    协调文本提取、文书分类、信息提取、案件绑定等子服务，
    完成完整的文书识别流程。
    
    Requirements: 4.5, 4.6, 4.7, 6.2, 7.1, 7.2, 7.3, 8.1, 8.2, 8.3, 8.4
    """
    
    def __init__(
        self,
        text_extraction=None,
        classifier=None,
        extractor=None,
        binding_service=None,
        document_renamer=None,
    ):
        """
        初始化服务
        
        Args:
            text_extraction: 文本提取服务（可选，用于依赖注入）
            classifier: 文书分类器（可选，用于依赖注入）
            extractor: 信息提取器（可选，用于依赖注入）
            binding_service: 案件绑定服务（可选，用于依赖注入）
            document_renamer: 文书重命名服务（可选，用于依赖注入）
        """
        self._text_extraction = text_extraction
        self._classifier = classifier
        self._extractor = extractor
        self._binding_service = binding_service
        self._document_renamer = document_renamer
    
    @property
    def text_extraction(self):
        """延迟加载文本提取服务"""
        if self._text_extraction is None:
            from .text_extraction_service import TextExtractionService
            self._text_extraction = TextExtractionService()
        return self._text_extraction
    
    @property
    def classifier(self):
        """延迟加载文书分类器"""
        if self._classifier is None:
            from .document_classifier import DocumentClassifier
            self._classifier = DocumentClassifier()
        return self._classifier
    
    @property
    def extractor(self):
        """延迟加载信息提取器"""
        if self._extractor is None:
            from .info_extractor import InfoExtractor
            self._extractor = InfoExtractor()
        return self._extractor
    
    @property
    def binding_service(self):
        """延迟加载案件绑定服务"""
        if self._binding_service is None:
            from .case_binding_service import CaseBindingService
            self._binding_service = CaseBindingService()
        return self._binding_service
    
    @property
    def document_renamer(self):
        """延迟加载文书重命名服务"""
        if self._document_renamer is None:
            from apps.automation.services.sms.document_renamer import DocumentRenamer
            self._document_renamer = DocumentRenamer()
        return self._document_renamer
    
    def recognize_document(
        self,
        file_path: str,
        user: Optional[Any] = None
    ) -> RecognitionResponse:
        """
        识别文书并绑定案件
        
        完整流程：
        1. 提取文本
        2. 分类文书类型
        3. 提取关键信息
        4. 匹配案件并创建日志
        
        Args:
            file_path: 文书文件路径
            user: 当前用户
            
        Returns:
            RecognitionResponse 对象
            
        Raises:
            ValidationException: 文件格式不支持或文本提取失败
            ServiceUnavailableError: AI 服务不可用
            RecognitionTimeoutError: 识别超时
            
        Requirements: 4.5, 4.6, 4.7, 6.2, 8.1, 8.2, 8.3, 8.4
        """
        logger.info(
            f"开始识别文书",
            extra={
                "action": "recognize_document",
                "file_path": file_path,
                "user_id": getattr(user, 'id', None) if user else None
            }
        )
        
        try:
            # 1. 提取文本
            extraction_result = self.text_extraction.extract_text(file_path)
            
            if not extraction_result.success or not extraction_result.text.strip():
                logger.warning(
                    f"文本提取失败或内容为空",
                    extra={
                        "action": "recognize_document",
                        "file_path": file_path,
                        "extraction_method": extraction_result.extraction_method
                    }
                )
                # 返回空结果
                return RecognitionResponse(
                    recognition=RecognitionResult(
                        document_type=DocumentType.OTHER,
                        case_number=None,
                        key_time=None,
                        raw_text="",
                        confidence=0.0,
                        extraction_method=extraction_result.extraction_method
                    ),
                    binding=BindingResult.failure_result(
                        message="无法从文书中提取文字",
                        error_code="TEXT_EXTRACTION_FAILED"
                    ),
                    file_path=file_path
                )
            
            # 2. 分类文书类型
            doc_type, confidence = self.classifier.classify(extraction_result.text)
            
            # 3. 提取关键信息
            case_number = None
            key_time = None
            
            if doc_type == DocumentType.SUMMONS:
                info = self.extractor.extract_summons_info(extraction_result.text)
                case_number = info.get("case_number")
                key_time = info.get("court_time")
            elif doc_type == DocumentType.EXECUTION_RULING:
                info = self.extractor.extract_execution_info(extraction_result.text)
                case_number = info.get("case_number")
                key_time = info.get("preservation_deadline")
            
            # 构建识别结果
            recognition = RecognitionResult(
                document_type=doc_type,
                case_number=case_number,
                key_time=key_time,
                raw_text=extraction_result.text,
                confidence=confidence,
                extraction_method=extraction_result.extraction_method
            )
            
            # 4. 绑定案件（仅支持传票）
            binding = None
            renamed_file_path = file_path  # 默认使用原路径
            
            if doc_type == DocumentType.SUMMONS and case_number:
                # 4.1 先查找案件获取案件名称
                case_id = self.binding_service.find_case_by_number(case_number)
                case_name = None
                
                if case_id:
                    case_dto = self.binding_service.case_service.get_case_by_id_internal(case_id)
                    if case_dto:
                        case_name = case_dto.name
                
                # 4.2 如果找到案件，先重命名文件
                if case_name:
                    renamed_file_path = self._rename_document(
                        file_path=file_path,
                        document_type=doc_type,
                        case_name=case_name
                    )
                
                # 4.3 格式化日志内容
                log_content = self.binding_service.format_log_content(
                    document_type=doc_type,
                    case_number=case_number,
                    key_time=key_time,
                    raw_text=extraction_result.text
                )
                
                # 4.4 绑定案件（使用重命名后的文件路径）
                binding = self.binding_service.bind_document_to_case(
                    case_number=case_number,
                    document_type=doc_type,
                    content=log_content,
                    key_time=key_time,
                    file_path=renamed_file_path,
                    user=user
                )
            elif doc_type == DocumentType.OTHER:
                # 非支持文书类型
                binding = BindingResult.failure_result(
                    message="暂时只支持传票识别，其他文书类型敬请期待",
                    error_code="UNSUPPORTED_DOCUMENT_TYPE"
                )
            elif doc_type == DocumentType.EXECUTION_RULING:
                # 执行裁定书暂不支持绑定
                binding = BindingResult.failure_result(
                    message="执行裁定书绑定功能开发中，敬请期待",
                    error_code="FEATURE_NOT_IMPLEMENTED"
                )
            elif not case_number:
                # 未识别到案号
                binding = BindingResult.failure_result(
                    message="未识别到案号，无法绑定案件",
                    error_code="CASE_NUMBER_NOT_FOUND"
                )
            
            logger.info(
                f"文书识别完成",
                extra={
                    "action": "recognize_document",
                    "file_path": file_path,
                    "renamed_file_path": renamed_file_path,
                    "document_type": doc_type.value,
                    "case_number": case_number,
                    "binding_success": binding.success if binding else None
                }
            )
            
            return RecognitionResponse(
                recognition=recognition,
                binding=binding,
                file_path=renamed_file_path  # 返回重命名后的路径
            )
            
        except (ValidationException, ServiceUnavailableError, RecognitionTimeoutError):
            # 这些异常直接向上抛出，由全局异常处理器处理
            raise
        except Exception as e:
            logger.error(
                f"文书识别失败: {e}",
                extra={
                    "action": "recognize_document",
                    "file_path": file_path,
                    "error_type": type(e).__name__,
                    "error": str(e)
                },
                exc_info=True
            )
            raise
    
    def recognize_document_from_text(
        self,
        text: str
    ) -> RecognitionResult:
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
            logger.warning(
                "文本内容为空",
                extra={"action": "recognize_document_from_text", "result": "empty_text"}
            )
            raise ValidationException(
                message="文本内容不能为空",
                code="EMPTY_TEXT",
                errors={"text": "请提供有效的文书文本"}
            )
        
        logger.info(
            f"开始从文本识别文书",
            extra={
                "action": "recognize_document_from_text",
                "text_length": len(text)
            }
        )
        
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
                extraction_method="text_input"
            )
            
            logger.info(
                f"文本识别完成",
                extra={
                    "action": "recognize_document_from_text",
                    "document_type": doc_type.value,
                    "case_number": case_number,
                    "confidence": confidence
                }
            )
            
            return result
            
        except (ValidationException, ServiceUnavailableError, RecognitionTimeoutError):
            raise
        except Exception as e:
            logger.error(
                f"文本识别失败: {e}",
                extra={
                    "action": "recognize_document_from_text",
                    "error_type": type(e).__name__,
                    "error": str(e)
                },
                exc_info=True
            )
            raise
    
    def _rename_document(
        self,
        file_path: str,
        document_type: DocumentType,
        case_name: str
    ) -> str:
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
                title=title,
                case_name=case_name,
                received_date=date.today()
            )
            
            # 构建新文件路径
            from pathlib import Path
            original_path = Path(file_path)
            new_path = original_path.parent / new_filename
            
            # 如果新文件名已存在，添加数字后缀
            counter = 1
            while new_path.exists():
                base_filename = new_filename.replace('收.pdf', f'收{counter}.pdf')
                new_path = original_path.parent / base_filename
                counter += 1
                if counter > 100:
                    break
            
            # 重命名文件
            original_path.rename(new_path)
            
            logger.info(
                f"文书重命名成功",
                extra={
                    "action": "rename_document",
                    "original_path": file_path,
                    "new_path": str(new_path),
                    "document_type": document_type.value,
                    "case_name": case_name
                }
            )
            return str(new_path)
            
        except Exception as e:
            logger.warning(
                f"文书重命名失败，保留原文件名",
                extra={
                    "action": "rename_document",
                    "file_path": file_path,
                    "error": str(e)
                }
            )
            return file_path
