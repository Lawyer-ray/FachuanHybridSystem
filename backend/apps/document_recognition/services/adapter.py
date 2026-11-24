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

    def recognize_document(
        self,
        file_path: str,
        user: Any | None = None,
        *,
        prebound_case_id: int | None = None,
        prebound_case_log_id: int | None = None,
        llm_model: str | None = None,
        known_case_number: str | None = None,
        known_party_names: list[str] | None = None,
        known_document_type: str | None = None,
        received_at: Any | None = None,
        sibling_documents: list[str] | None = None,
    ) -> RecognitionResponse:
        """
        识别文书并绑定案件

        Args:
            file_path: 文书文件路径
            user: 当前用户
            prebound_case_id: 管线预绑定的案件 ID（法院短信入口，可选）
            prebound_case_log_id: 管线预绑定的案件日志 ID（提醒锚点，可选）
            llm_model: 指定识别模型（可选，None 走统一 LLM 层默认）
            known_case_number: 来源管线（法院短信）已解析出的案号（可选，可信度高于本文书）
            known_party_names: 来源管线已解析出的当事人（可选）
            known_document_type: 来源管线判定的文书类型（可选，仅在分类器认不出时兑底）
            received_at: 文书送达/收到时间（法院短信 ``CourtSMS.received_at``，
                「送达之日起 N 日」类期限的起算锚点）
            sibling_documents: 同一条短信里其他文书的显示名（判定「期限归属别份文书」用）。
                手工上传场景传 None。**注意：本参数必须一路透传到识别服务**，
                漏传会让管线只能把「锚点在别份文书」判成"未知"（同样丢弃，但原因说不清）。

        Returns:
            RecognitionResponse 对象
        """
        return cast(
            RecognitionResponse,
            _build_service().recognize_document(
                file_path,
                user,
                prebound_case_id=prebound_case_id,
                prebound_case_log_id=prebound_case_log_id,
                llm_model=llm_model,
                known_case_number=known_case_number,
                known_party_names=known_party_names,
                known_document_type=known_document_type,
                received_at=received_at,
                sibling_documents=sibling_documents,
            ),
        )

    def recognize_document_from_text(self, text: str, *, llm_model: str | None = None) -> RecognitionResult:
        """
        从已提取的文本识别文书

        Args:
            text: 文书文本内容
            llm_model: 指定识别模型（可选，None 走统一 LLM 层默认）

        Returns:
            RecognitionResult 对象
        """
        return cast(RecognitionResult, _build_service().recognize_document_from_text(text, llm_model=llm_model))


# ↓↓ 由 CourtDocumentRecognitionServiceAdapter 下沉的模块级纯函数（四层架构静态方法棘轮）
def _build_service() -> Any:
    from .recognition_service import CourtDocumentRecognitionService

    return CourtDocumentRecognitionService()
