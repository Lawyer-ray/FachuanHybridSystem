"""模拟庭审报告导出服务."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path as StdPath
from typing import Any

from apps.documents.services.placeholders.fallback import build_docx_render_context
from apps.documents.storage import get_docx_templates_root
from apps.litigation_ai.placeholders.mock_trial_report import MockTrialReportPlaceholderService

logger = logging.getLogger("apps.litigation_ai")


class MockTrialExportService:
    """模拟庭审报告导出服务."""

    def export_to_docx(
        self,
        session_id: str,
        report_data: dict[str, Any],
        case_info: dict[str, str],
    ) -> StdPath:
        """
        导出模拟庭审报告为Word文档.

        Args:
            session_id: 会话ID
            report_data: 报告数据
            case_info: 案件信息

        Returns:
            生成的文件路径
        """
        from docxtpl import DocxTemplate

        # 准备上下文数据
        context = {
            "report_data": report_data,
            "case_info": case_info,
        }

        # 生成占位符值
        placeholder_service = MockTrialReportPlaceholderService()
        placeholder_values = placeholder_service.generate(context)

        # 加载模板
        template_path = get_docx_templates_root() / "2-案件材料" / "5-模拟庭审报告" / "模拟庭审报告.docx"

        if not template_path.exists():
            raise FileNotFoundError(f"模板文件不存在: {template_path}")

        doc = DocxTemplate(str(template_path))

        # 渲染模板
        doc.render(build_docx_render_context(doc=doc, context=placeholder_values))

        # 保存到临时文件
        output_dir = StdPath(tempfile.gettempdir()) / "mock_trial_reports"
        output_dir.mkdir(parents=True, exist_ok=True)

        safe_case_name = "".join(c for c in case_info.get("case_name", "未命名") if c.isalnum() or c in "_- ")
        output_path = output_dir / f"模拟庭审报告_{safe_case_name}_{session_id[:8]}.docx"

        doc.save(str(output_path))
        logger.info(f"模拟庭审报告已导出: {output_path}")

        return output_path
