"""跨模块依赖注入 - 隔离 litigation_ai 模块对其他 app 的导入."""

from typing import Any

from apps.core.interfaces import ServiceLocator


def get_ocr_service() -> Any:
    """获取 OCR 服务实例(通过 ServiceLocator)"""
    return ServiceLocator.get_ocr_service()


def get_ocr_recognizer() -> Any:
    """获取 OCR 识别器实例(支持 recognize_bytes 方法)"""
    from apps.automation.services.ocr.ocr_service import OCRService

    return OCRService()


def get_litigation_generation_service() -> Any:
    """获取诉讼文书生成服务实例"""
    from apps.documents.services.generation import LitigationGenerationService

    return LitigationGenerationService()


def get_complaint_output_class() -> type:
    """获取 ComplaintOutput 类"""
    from apps.documents.services.generation.outputs import ComplaintOutput

    return ComplaintOutput


def get_defense_output_class() -> type:
    """获取 DefenseOutput 类"""
    from apps.documents.services.generation.outputs import DefenseOutput

    return DefenseOutput


def get_generated_document_storage() -> Any:
    """获取文档存储服务实例"""
    from apps.documents.services.generation.output_storage import GeneratedDocumentStorage

    return GeneratedDocumentStorage()
