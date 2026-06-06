"""
合同格式化服务
整合Java的poi-service
"""
from pathlib import Path
from typing import Optional, Tuple
from django.conf import settings
import logging

from apps.core.services.poi_client import get_poi_client
from apps.contract_review.models import ReviewTask

logger = logging.getLogger(__name__)


class ContractFormatService:
    """合同格式化服务"""

    def __init__(self):
        self.poi_client = get_poi_client()

    def format_contract(
        self,
        task: ReviewTask,
        config: Optional[dict] = None,
        force_method: Optional[str] = None
    ) -> Tuple[Path, str]:
        """
        格式化合同文档

        Args:
            task: 审查任务
            config: 格式配置（可选）
            force_method: 强制使用的方法（可选）

        Returns:
            (文件路径, 使用的方法)
        """
        # 1. 读取原始文件
        original_file_path = Path(settings.MEDIA_ROOT) / task.original_file
        if not original_file_path.exists():
            raise ValueError(f"原始文件不存在: {original_file_path}")

        docx_bytes = original_file_path.read_bytes()

        # 2. 确定使用的方法
        method = self._determine_method(force_method)

        # 3. 执行格式化
        if method == 'poi':
            formatted_bytes, used_method = self._format_with_poi(
                docx_bytes, config
            )
        else:
            formatted_bytes, used_method = self._format_with_python(
                docx_bytes, config
            )

        # 4. 保存格式化后的文件
        output_filename = f"{task.contract_title}_formatted.docx"
        output_path = original_file_path.parent / output_filename
        output_path.write_bytes(formatted_bytes)

        # 更新任务的输出文件（相对于MEDIA_ROOT）
        task.output_file = str(output_path.relative_to(settings.MEDIA_ROOT))
        task.save(update_fields=["output_file"])

        logger.info(
            f"合同格式化完成：任务 {task.id}, "
            f"方法 {used_method}, "
            f"文件 {output_filename}"
        )

        return output_path, used_method

    def _determine_method(self, force_method: Optional[str]) -> str:
        """确定使用的方法"""
        if force_method and force_method != 'auto':
            return force_method

        # 检查POI服务是否可用
        if self.poi_client.health_check():
            return 'poi'
        else:
            logger.warning("POI服务不可用，降级到Python")
            return 'python'

    def _format_with_poi(
        self,
        docx_bytes: bytes,
        config: Optional[dict]
    ) -> Tuple[bytes, str]:
        """使用POI格式化"""
        try:
            formatted_bytes = self.poi_client.format_contract(
                docx_bytes=docx_bytes,
                config=config
            )
            return formatted_bytes, 'poi'
        except Exception as e:
            logger.error(f"POI格式化失败: {e}")
            raise

    def _format_with_python(
        self,
        docx_bytes: bytes,
        config: Optional[dict]
    ) -> Tuple[bytes, str]:
        """使用Python格式化（降级方案）"""
        from docx import Document
        from docx.shared import Pt
        import io

        # 加载文档
        doc = Document(io.BytesIO(docx_bytes))

        # 简化的格式化逻辑
        for para in doc.paragraphs:
            # 设置行距
            para.paragraph_format.line_spacing = 1.5

            # 设置字体
            for run in para.runs:
                run.font.name = '宋体'
                run.font.size = Pt(12)

        # 保存
        output = io.BytesIO()
        doc.save(output)
        output.seek(0)

        return output.getvalue(), 'python'
