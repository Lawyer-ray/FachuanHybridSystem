class ContractReviewError(Exception):
    """合同审查基础异常"""


class ExtractionError(ContractReviewError):
    """内容提取失败"""


class ParsingError(ContractReviewError):
    """LLM 结果解析失败"""
