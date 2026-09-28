"""
法院文书智能识别服务适配器

实现 ICourtDocumentRecognitionService 接口，供 ServiceLocator 使用。

适配器本身经 ServiceLocator 单例缓存，但每次调用都新建
CourtDocumentRecognitionService——识别服务持有 per-run 的共享分析
缓存（按原文 memoize），复用实例会造成跨任务状态串扰与内存累积。

Requirements: 7.5
"""

from typing import Any, cast

from .data_classes import RecognitionResponse, RecognitionResult


class CourtDocumentRecognitionServiceAdapter:
    """
    法院文书智能识别服务适配器

    实现 ICourtDocumentRecognitionService 接口，
    作为 ServiceLocator 的注册入口。

    实际实现委托给 CourtDocumentRecognitionService（每次调用新建，
    构造成本为零：全部协作者均为惰性加载）。
    """

    @staticmethod
    def _build_service() -> Any:
        from .recognition_service import CourtDocumentRecognitionService

        return CourtDocumentRecognitionService()

    def recognize_document(
        self,
        file_path: str,
        user: Any | None = None,
        *,
        prebound_case_id: int | None = None,
        prebound_case_log_id: int | None = None,
    ) -> RecognitionResponse:
        """
        识别文书并绑定案件

        Args:
            file_path: 文书文件路径
            user: 当前用户
            prebound_case_id: 管线预绑定的案件 ID（法院短信入口，可选）
            prebound_case_log_id: 管线预绑定的案件日志 ID（提醒锚点，可选）

        Returns:
            RecognitionResponse 对象
        """
        return cast(
            RecognitionResponse,
            self._build_service().recognize_document(
                file_path,
                user,
                prebound_case_id=prebound_case_id,
                prebound_case_log_id=prebound_case_log_id,
            ),
        )

    def recognize_document_from_text(self, text: str) -> RecognitionResult:
        """
        从已提取的文本识别文书

        Args:
            text: 文书文本内容

        Returns:
            RecognitionResult 对象
        """
        return cast(RecognitionResult, self._build_service().recognize_document_from_text(text))
