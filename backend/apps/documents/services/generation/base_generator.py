"""
文书生成器基类

定义所有文书生成器的统一接口和通用方法.
"""

from django.utils.translation import gettext_lazy as _
import logging
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Optional

from apps.core.exceptions import ValidationException
from apps.core.path import Path

from .result import GenerationResult

if TYPE_CHECKING:
    from .context_builder import ContextBuilder

logger = logging.getLogger(__name__)


class BaseGenerator(ABC):
    """
    文书生成器基类

    所有具体生成器必须继承此类并实现抽象方法.
    提供统一的生成接口和通用的模板渲染功能.
    """

    # 生成器元信息(子类必须定义)
    name: str = ""  # 生成器名称(唯一标识)
    display_name: str = ""  # 显示名称
    description: str = ""  # 描述
    category: str = "general"  # 分类:litigation, non_litigation, general
    template_type: str = "contract"  # 模板类型:contract, case, authorization

    def __init__(self, context_builder: "ContextBuilder" | None = None) -> None:
        """
        初始化生成器

        Args:
            context_builder: 上下文构建器,支持依赖注入
        """
        self._context_builder = context_builder

    @property
    def context_builder(self) -> "ContextBuilder":
        """获取上下文构建器,支持延迟加载"""
        if self._context_builder is None:
            from .context_builder import ContextBuilder

            self._context_builder = ContextBuilder()
        return self._context_builder

    @abstractmethod
    def get_required_placeholders(self) -> list[str]:
        """
        返回此生成器需要的占位符列表

        Returns:
            占位符名称列表
        """
        pass

    @abstractmethod
    def generate(self, context: dict[str, Any], template_path: str, output_dir: str) -> GenerationResult:
        """
        执行文书生成

        Args:
            context: 替换词上下文字典
            template_path: 模板文件路径
            output_dir: 输出目录

        Returns:
            GenerationResult 生成结果
        """
        pass

    def validate_context(self, context: dict[str, Any]) -> tuple[bool, list[str]]:
        """
        验证上下文是否包含所有必需的占位符

        Args:
            context: 替换词上下文字典

        Returns:
            (是否有效, 缺失的占位符列表)
        """
        missing: list[Any] = []
        required_placeholders = self.get_required_placeholders()

        for key in required_placeholders:
            if key not in context or context[key] is None:
                missing.append(key)

        is_valid = len(missing) == 0
        return is_valid, missing

    def render_template(self, template_path: str, context: dict[str, Any]) -> bytes:
        """
        使用 docxtpl 渲染模板

        Args:
            template_path: 模板文件路径
            context: 替换词上下文字典

        Returns:
            渲染后的文档内容(字节)

        Raises:
            ValidationException: 模板文件不存在或渲染失败
        """
        try:
            import io
            from datetime import date

            from docxtpl import DocxTemplate

            # 验证模板文件存在
            if not Path(template_path).exists():
                raise ValidationException(
                    message=f"模板文件不存在: {template_path}",
                    code="TEMPLATE_NOT_FOUND",
                    errors={"template_path": f"文件不存在: {template_path}"},
                )

            # 加载并渲染模板
            doc = DocxTemplate(template_path)
            if "年份" not in context:
                context["年份"] = str(date.today().year)
            doc.render(context)

            # 保存到内存缓冲区
            buffer = io.BytesIO()
            doc.save(buffer)
            return buffer.getvalue()

        except ImportError as e:
            raise ValidationException(
                message=_("docxtpl 库未安装"),
                code="DOCXTPL_NOT_INSTALLED",
                errors={"dependency": "请安装 docxtpl 库: uv add docxtpl"},
            ) from e
        except Exception as e:
            raise ValidationException(
                message=f"模板渲染失败: {e!s}",
                code="TEMPLATE_RENDER_ERROR",
                errors={"template_path": template_path, "error": str(e)},
            ) from e

    def get_output_filename(self, context: dict[str, Any], template_name: str) -> str:
        """
        生成输出文件名

        Args:
            context: 替换词上下文字典
            template_name: 模板名称(不含扩展名)

        Returns:
            输出文件名
        """
        # 尝试从上下文获取合同名称,否则使用默认名称
        contract_name = context.get("contract_name", "未命名合同")

        # 清理文件名中的非法字符
        safe_contract_name = self._sanitize_filename(contract_name)
        safe_template_name = self._sanitize_filename(template_name)

        return f"{safe_contract_name}_{safe_template_name}.docx"

    def _sanitize_filename(self, filename: str) -> str:
        """
        清理文件名中的非法字符

        Args:
            filename: 原始文件名

        Returns:
            清理后的安全文件名
        """
        # 移除或替换非法字符
        illegal_chars = ["<", ">", ":", '"', "/", "\\", "|", "?", "*"]
        safe_name = filename

        for char in illegal_chars:
            safe_name = safe_name.replace(char, "_")

        # 移除首尾空格和点号
        safe_name = safe_name.strip(" .")

        # 如果文件名为空,使用默认名称
        if not safe_name:
            safe_name = "document"

        return safe_name

    def _record_metrics(self, start_time: float, success: bool, error_message: str | None = None) -> int:
        """
        记录生成指标

        Args:
            start_time: 开始时间戳
            success: 是否成功
            error_message: 错误信息(可选)

        Returns:
            生成耗时(毫秒)
        """
        duration_ms = int((time.time() - start_time) * 1000)

        if success:
            logger.info("文书生成成功 - 生成器: %s, 耗时: %sms", self.name, duration_ms)
        else:
            logger.error("文书生成失败 - 生成器: %s, 耗时: %sms, 错误: %s", self.name, duration_ms, error_message)

        return duration_ms

    def __str__(self) -> str:
        """字符串表示"""
        return f"{self.display_name or self.name} ({self.category})"

    def __repr__(self) -> str:
        """调试表示"""
        return f"<{self.__class__.__name__}: {self.name}>"
