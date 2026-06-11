"""文档解析相关异常"""

from apps.core.exceptions import ExternalServiceError


class DocumentParsingError(ExternalServiceError):
    """文档解析基础异常"""

    pass


class MineruAPIError(DocumentParsingError):
    """MinerU API 调用异常"""

    def __init__(self, message: str, status_code: int = None):
        super().__init__(message)
        self.status_code = status_code


class FileFormatNotSupportedError(DocumentParsingError):
    """不支持的文件格式"""

    pass


class ParsingTimeoutError(DocumentParsingError):
    """解析超时"""

    pass
