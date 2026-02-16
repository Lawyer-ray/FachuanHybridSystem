"""
合同文书生成器

生成合同相关的法律文书,包括委托代理合同、授权委托书等.
"""

import logging
import time

from apps.core.path import Path

from apps.documents.services.generation.base_generator import BaseGenerator
from apps.documents.services.generation.registry import GeneratorRegistry
from apps.documents.services.generation.result import GenerationResult
from typing import ClassVar, Any

logger = logging.getLogger(__name__)


@GeneratorRegistry.register
class ContractGenerator(BaseGenerator):
    """合同文书生成器"""

    name : str = "contract_generator"
    display_name : str = "合同文书生成器"
    description : str = "生成合同相关的法律文书"
    category : str = "general"
    template_type : str = "contract"

    # 必需的占位符
    REQUIRED_PLACEHOLDERS: ClassVar = [
        "contract_name",
        "principal_name",
    ]

    def get_required_placeholders(self) -> list[str]:
        return self.REQUIRED_PLACEHOLDERS

    def generate(self, context: dict[str, Any], template_path: str, output_dir: str) -> GenerationResult:
        """
        生成合同文书

        Args:
            context: 替换词上下文
            template_path: 模板文件路径
            output_dir: 输出目录

        Returns:
            GenerationResult 生成结果
        """
        start_time = time.time()

        # 验证模板文件存在
        if not Path(template_path).exists():
            return GenerationResult(
                success=False,
                error_message=f"模板文件不存在: {template_path}",
                duration_ms=int((time.time() - start_time) * 1000),
            )

        # 验证上下文
        is_valid, missing = self.validate_context(context)
        if not is_valid:
            logger.warning(f"上下文缺少必需占位符: {missing}")
            # 继续生成,缺失的占位符使用空字符串
            for key in missing:
                context[key] = ""

        try:
            # 渲染模板
            content = self.render_template(template_path, context)

            # 生成输出文件名
            template_name = Path(template_path).stem
            output_filename = self.get_output_filename(context, template_name)
            output_path = Path(output_dir) / output_filename

            # 确保输出目录存在
            Path(output_dir).makedirs_p()

            # 写入文件
            with open(output_path, "wb") as f:
                f.write(content)

            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(f"生成文书成功: {output_path}, 耗时: {duration_ms}ms")

            return GenerationResult(
                success=True,
                file_path=output_path,
                file_name=output_filename,
                duration_ms=duration_ms,
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            error_msg = f"生成文书失败: {e!s}"
            logger.error(error_msg, exc_info=True)

            return GenerationResult(
                success=False,
                error_message=error_msg,
                duration_ms=duration_ms,
            )

    def generate_for_contract(self, contract_id: int, template_path: str, output_dir: str) -> GenerationResult:
        """
        为指定合同生成文书

        便捷方法,自动构建上下文.

        Args:
            contract_id: 合同 ID
            template_path: 模板文件路径
            output_dir: 输出目录

        Returns:
            GenerationResult 生成结果
        """
        context = self.context_builder.build_contract_context(contract_id)
        if not context:
            return GenerationResult(success=False, error_message=f"无法构建合同上下文: contract_id={contract_id}")

        return self.generate(context, template_path, output_dir)
