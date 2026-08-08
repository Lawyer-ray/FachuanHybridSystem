"""文档解析相关异常"""

from apps.core.exceptions import ExternalServiceError


class DocumentParsingError(ExternalServiceError):
    """文档解析基础异常"""

    pass


class MineruAPIError(DocumentParsingError):
    """MinerU API 调用异常"""

    pass


class TextinAPIError(DocumentParsingError):
    """TextinParse API 调用异常"""

    pass


class FileFormatNotSupportedError(DocumentParsingError):
    """不支持的文件格式"""

    pass


class ParsingTimeoutError(DocumentParsingError):
    """解析超时"""

    pass
