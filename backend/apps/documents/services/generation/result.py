"""
生成结果数据类

定义文书生成操作的结果数据结构.
"""

from dataclasses import dataclass


@dataclass
class GenerationResult:
    """
    文书生成结果

    包含生成操作的成功状态、文件信息、错误信息和性能指标.
    """

    success: bool
    """生成是否成功"""

    file_path: str | None = None
    """生成文件的完整路径"""

    file_name: str | None = None
    """生成文件的文件名"""

    error_message: str | None = None
    """错误信息(失败时)"""

    duration_ms: int = 0
    """生成耗时(毫秒)"""

    def __post_init__(self) -> None:
        """数据验证"""
        if self.success and not self.file_path:
            raise ValueError("成功的生成结果必须包含文件路径")

        if not self.success and not self.error_message:
            raise ValueError("失败的生成结果必须包含错误信息")

        if self.duration_ms < 0:
            raise ValueError("生成耗时不能为负数")
