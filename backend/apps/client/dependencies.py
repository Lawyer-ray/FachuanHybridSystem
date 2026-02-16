"""跨模块依赖注入 - 隔离 client 模块对其他 app 的导入."""

from typing import Any


def get_ocr_engine(use_v5: bool = True) -> Any:
    """获取 OCR 引擎实例"""
    from apps.automation.services.ocr import get_ocr_engine as _get

    return _get(use_v5=use_v5)
