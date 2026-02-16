"""API schemas and serializers."""

from __future__ import annotations

"""文书送达自动下载 Schemas"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class DocumentDeliveryRecord:
    """文书送达记录"""

    case_number: str  # 案号
    send_time: datetime  # 发送时间
    element_index: int  # 页面元素索引(用于定位下载按钮)
    document_name: str = ""  # 文书名称(可选)
    court_name: str = ""  # 法院名称(可选)

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典"""
        return {
            "case_number": self.case_number,
            "send_time": self.send_time.isoformat() if self.send_time else None,
            "element_index": self.element_index,
            "document_name": self.document_name,
            "court_name": self.court_name,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DocumentDeliveryRecord:
        """从字典反序列化"""
        send_time = None
        if data.get("send_time"):
            if isinstance(data["send_time"], str):
                send_time = datetime.fromisoformat(data["send_time"].replace("Z", "+00:00"))
            elif isinstance(data["send_time"], datetime):
                send_time = data["send_time"]

        # 如果 send_time 仍然是 None，使用当前时间作为默认值
        if send_time is None:
            send_time = datetime.now()

        # 确保字符串字段的类型安全
        document_name = data.get("document_name", "")
        if not isinstance(document_name, str):
            document_name = str(document_name) if document_name is not None else ""

        court_name = data.get("court_name", "")
        if not isinstance(court_name, str):
            court_name = str(court_name) if court_name is not None else ""

        case_number = data["case_number"]
        if not isinstance(case_number, str):
            case_number = str(case_number) if case_number is not None else ""

        element_index = data["element_index"]
        if not isinstance(element_index, int):
            element_index = int(element_index) if element_index is not None else 0

        return cls(
            case_number=case_number,
            send_time=send_time,
            element_index=element_index,
            document_name=document_name,
            court_name=court_name,
        )


@dataclass
class DocumentQueryResult:
    """文书查询结果"""

    total_found: int  # 发现的文书总数
    processed_count: int  # 处理的文书数
    skipped_count: int  # 跳过的文书数(时间过滤或已处理)
    failed_count: int  # 处理失败数
    case_log_ids: list[int]  # 创建的案件日志 ID 列表
    errors: list[str]  # 错误信息列表


@dataclass
class DocumentProcessResult:
    """单个文书处理结果"""

    success: bool  # 是否成功
    case_id: int | None  # 匹配的案件ID
    case_log_id: int | None  # 创建的案件日志ID
    renamed_path: str | None  # 重命名后的文件路径
    notification_sent: bool  # 是否发送了通知
    error_message: str | None  # 错误信息
