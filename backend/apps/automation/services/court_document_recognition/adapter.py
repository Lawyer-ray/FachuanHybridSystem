"""
法院文书智能识别服务适配器

实现 ICourtDocumentRecognitionService 接口，供 ServiceLocator 使用。

Requirements: 7.5
"""

from typing import Any, cast

from .data_classes import RecognitionResponse, RecognitionResult


class CourtDocumentRecognitionServiceAdapter:
    """
    法院文书智能识别服务适配器

    实现 ICourtDocumentRecognitionService 接口，
    作为 ServiceLocator 的注册入口。

    实际实现委托给 CourtDocumentRecognitionService。
    """

    def __init__(self) -> None:
        self._service = None

    @property
    def service(self) -> Any:
        """延迟加载实际服务"""
        if self._service is None:
            from .recognition_service import CourtDocumentRecognitionService

            self._service = CourtDocumentRecognitionService()  # type: ignore[assignment]
        return self._service

    def recognize_document(self, file_path: str, user: Any | None = None) -> RecognitionResponse:
        """
        识别文书并绑定案件

        Args:
            file_path: 文书文件路径
            user: 当前用户

        Returns:
            RecognitionResponse 对象
        """
        return cast(RecognitionResponse, self.service.recognize_document(file_path, user))

    def recognize_document_from_text(self, text: str) -> RecognitionResult:
        """
        从已提取的文本识别文书

        Args:
            text: 文书文本内容

        Returns:
            RecognitionResult 对象
        """
        return cast(RecognitionResult, self.service.recognize_document_from_text(text))
