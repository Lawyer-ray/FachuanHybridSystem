"""
法院文书智能识别数据类

定义文书识别相关的数据传输对象（DTO）

Requirements: 4.5, 7.4
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class DocumentType(str, Enum):
    """
    文书类型枚举
    
    Requirements: 4.2
    """
    SUMMONS = "summons"              # 传票
    EXECUTION_RULING = "execution"   # 执行裁定书
    OTHER = "other"                  # 其他


@dataclass
class RecognitionResult:
    """
    识别结果 DTO
    
    包含文书类型识别和关键信息提取的结果。
    
    Requirements: 4.5, 7.4
    
    Attributes:
        document_type: 文书类型（传票/执行裁定书/其他）
        case_number: 识别出的案号，可能为空
        key_time: 关键时间（开庭时间/保全到期时间），可能为空
        raw_text: 从文书中提取的原始文字
        confidence: 识别置信度，范围 0-1
        extraction_method: 文本提取方式（"pdf_direct" 或 "ocr"）
    """
    document_type: DocumentType
    case_number: Optional[str]
    key_time: Optional[datetime]
    raw_text: str
    confidence: float
    extraction_method: str
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "document_type": self.document_type.value,
            "case_number": self.case_number,
            "key_time": self.key_time.isoformat() if self.key_time else None,
            "raw_text": self.raw_text,
            "confidence": self.confidence,
            "extraction_method": self.extraction_method,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RecognitionResult":
        """从字典反序列化"""
        key_time = None
        if data.get("key_time"):
            if isinstance(data["key_time"], str):
                key_time = datetime.fromisoformat(data["key_time"])
            else:
                key_time = data["key_time"]
        
        return cls(
            document_type=DocumentType(data["document_type"]),
            case_number=data.get("case_number"),
            key_time=key_time,
            raw_text=data.get("raw_text", ""),
            confidence=data.get("confidence", 0.0),
            extraction_method=data.get("extraction_method", ""),
        )


@dataclass
class BindingResult:
    """
    绑定结果 DTO
    
    包含文书与案件绑定的结果信息。
    
    Requirements: 5.7, 5.8
    
    Attributes:
        success: 绑定是否成功
        case_id: 匹配到的案件 ID，绑定失败时为空
        case_name: 匹配到的案件名称，绑定失败时为空
        case_log_id: 创建的案件日志 ID，绑定失败时为空
        message: 结果消息（成功或失败原因）
        error_code: 错误代码，成功时为空
    """
    success: bool
    case_id: Optional[int]
    case_name: Optional[str]
    case_log_id: Optional[int]
    message: str
    error_code: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "success": self.success,
            "case_id": self.case_id,
            "case_name": self.case_name,
            "case_log_id": self.case_log_id,
            "message": self.message,
            "error_code": self.error_code,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BindingResult":
        """从字典反序列化"""
        return cls(
            success=data.get("success", False),
            case_id=data.get("case_id"),
            case_name=data.get("case_name"),
            case_log_id=data.get("case_log_id"),
            message=data.get("message", ""),
            error_code=data.get("error_code"),
        )
    
    @classmethod
    def success_result(
        cls,
        case_id: int,
        case_name: str,
        case_log_id: int,
    ) -> "BindingResult":
        """创建成功的绑定结果"""
        return cls(
            success=True,
            case_id=case_id,
            case_name=case_name,
            case_log_id=case_log_id,
            message=f"文书已绑定到案件 {case_name}",
        )
    
    @classmethod
    def failure_result(
        cls,
        message: str,
        error_code: str,
    ) -> "BindingResult":
        """创建失败的绑定结果"""
        return cls(
            success=False,
            case_id=None,
            case_name=None,
            case_log_id=None,
            message=message,
            error_code=error_code,
        )


@dataclass
class NotificationResult:
    """
    通知发送结果 DTO
    
    包含飞书群通知发送的结果信息。
    
    Requirements: 5.1, 5.2
    
    Attributes:
        success: 通知是否发送成功
        message: 结果消息（成功或失败原因）
        error_code: 错误代码，成功时为空
        sent_at: 通知发送时间，失败时为空
        file_sent: 文件是否发送成功
    """
    success: bool
    message: Optional[str] = None
    error_code: Optional[str] = None
    sent_at: Optional[datetime] = None
    file_sent: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "success": self.success,
            "message": self.message,
            "error_code": self.error_code,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "file_sent": self.file_sent,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NotificationResult":
        """从字典反序列化"""
        sent_at = None
        if data.get("sent_at"):
            if isinstance(data["sent_at"], str):
                sent_at = datetime.fromisoformat(data["sent_at"])
            else:
                sent_at = data["sent_at"]
        
        return cls(
            success=data.get("success", False),
            message=data.get("message"),
            error_code=data.get("error_code"),
            sent_at=sent_at,
            file_sent=data.get("file_sent", False),
        )
    
    @classmethod
    def success_result(
        cls,
        sent_at: datetime,
        file_sent: bool = False,
    ) -> "NotificationResult":
        """
        创建成功的通知结果
        
        Args:
            sent_at: 通知发送时间
            file_sent: 文件是否发送成功
            
        Returns:
            NotificationResult: 成功的通知结果
        """
        return cls(
            success=True,
            message="通知发送成功",
            sent_at=sent_at,
            file_sent=file_sent,
        )
    
    @classmethod
    def failure_result(
        cls,
        message: str,
        error_code: str,
    ) -> "NotificationResult":
        """
        创建失败的通知结果
        
        Args:
            message: 失败原因描述
            error_code: 错误代码
            
        Returns:
            NotificationResult: 失败的通知结果
        """
        return cls(
            success=False,
            message=message,
            error_code=error_code,
        )


@dataclass
class RecognitionResponse:
    """
    完整响应 DTO
    
    包含识别结果、绑定结果和文件路径的完整响应。
    
    Requirements: 4.5, 7.4
    
    Attributes:
        recognition: 识别结果
        binding: 绑定结果，非支持文书类型时为空
        file_path: 上传文件的保存路径
    """
    recognition: RecognitionResult
    binding: Optional[BindingResult]
    file_path: str
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "recognition": self.recognition.to_dict(),
            "binding": self.binding.to_dict() if self.binding else None,
            "file_path": self.file_path,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RecognitionResponse":
        """从字典反序列化"""
        binding = None
        if data.get("binding"):
            binding = BindingResult.from_dict(data["binding"])
        
        return cls(
            recognition=RecognitionResult.from_dict(data["recognition"]),
            binding=binding,
            file_path=data.get("file_path", ""),
        )
