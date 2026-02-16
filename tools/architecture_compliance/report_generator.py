"""
违规报告生成器

按类型和严重程度统计违规，生成JSON和Markdown格式报告。
包含文件路径、行号、代码片段等详细信息。
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional

from .logging_config import get_logger
from .models import Violation, ViolationReport

logger = get_logger("report_generator")


class ReportGenerator:
    """违规报告生成器，支持JSON和Markdown格式输出。"""

    def build_report(self, violations: list[Violation]) -> ViolationReport:
        """
        从违规列表构建 ViolationReport，统计按类型和严重程度的计数。

        Args:
            violations: 违规对象列表

        Returns:
            包含统计信息和详细违规的 ViolationReport
        """
        type_counter: Counter[str] = Counter()
        severity_counter: Counter[str] = Counter()

        for v in violations:
            type_counter[v.violation_type] += 1
            severity_counter[v.severity] += 1

        report = ViolationReport(
            total_violations=len(violations),
            violations_by_type=dict(type_counter),
            violations_by_severity=dict(severity_counter),
            detailed_violations=list(violations),
            scan_timestamp=datetime.now(),
        )
        logger.info(
            "报告已构建: 共 %d 个违规, 类型分布 %s, 严重程度分布 %s",
            report.total_violations,
            report.violations_by_type,
            report.violations_by_severity,
        )
        return report

    def generate_json(self, report: ViolationReport) -> str:
        """
        生成JSON格式报告字符串。

        Args:
            report: ViolationReport 实例

        Returns:
            JSON字符串
        """
        return report.to_json()

    def generate_markdown(self, report: ViolationReport) -> str:
        """
        生成Markdown格式报告字符串。

        包含摘要表格（按类型和严重程度统计）以及按类型分组的详细违规列表。

        Args:
            report: ViolationReport 实例

        Returns:
            Markdown字符串
        """
        lines: list[str] = []

        # 标题
        lines.append("# 架构违规报告")
        lines.append("")
        lines.append(f"扫描时间: {report.scan_timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # 总览
        lines.append("## 总览")
        lines.append("")
        lines.append(f"违规总数: **{report.total_violations}**")
        lines.append("")

        # 按类型统计表
        if report.violations_by_type:
            lines.append("### 按类型统计")
            lines.append("")
            lines.append("| 类型 | 数量 |")
            lines.append("| --- | --- |")
            for vtype, count in sorted(report.violations_by_type.items()):
                lines.append(f"| {vtype} | {count} |")
            lines.append("")

        # 按严重程度统计表
        if report.violations_by_severity:
            lines.append("### 按严重程度统计")
            lines.append("")
            lines.append("| 严重程度 | 数量 |")
            lines.append("| --- | --- |")
            severity_order = ["high", "medium", "low"]
            for sev in severity_order:
                if sev in report.violations_by_severity:
                    lines.append(f"| {sev} | {report.violations_by_severity[sev]} |")
            # 包含不在预定义顺序中的严重程度
            for sev, count in sorted(report.violations_by_severity.items()):
                if sev not in severity_order:
                    lines.append(f"| {sev} | {count} |")
            lines.append("")

        # 详细违规列表（按类型分组）
        if report.detailed_violations:
            lines.append("## 详细违规列表")
            lines.append("")

            grouped: dict[str, list[Violation]] = {}
            for v in report.detailed_violations:
                grouped.setdefault(v.violation_type, []).append(v)

            for vtype in sorted(grouped):
                group = grouped[vtype]
                lines.append(f"### {vtype} ({len(group)}个)")
                lines.append("")
                for v in group:
                    lines.append(f"- **{v.file_path}** (行 {v.line_number})")
                    lines.append(f"  - 严重程度: {v.severity}")
                    lines.append(f"  - 描述: {v.description}")
                    lines.append(f"  - 代码片段:")
                    lines.append(f"    ```python")
                    lines.append(f"    {v.code_snippet}")
                    lines.append(f"    ```")
                    lines.append("")

        return "\n".join(lines)

    def write_json(
        self, report: ViolationReport, output_path: Path
    ) -> Path:
        """
        将JSON报告写入文件。

        Args:
            report: ViolationReport 实例
            output_path: 输出文件路径

        Returns:
            写入的文件路径
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        content = self.generate_json(report)
        output_path.write_text(content, encoding="utf-8")
        logger.info("JSON报告已写入: %s", output_path)
        return output_path

    def write_markdown(
        self, report: ViolationReport, output_path: Path
    ) -> Path:
        """
        将Markdown报告写入文件。

        Args:
            report: ViolationReport 实例
            output_path: 输出文件路径

        Returns:
            写入的文件路径
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        content = self.generate_markdown(report)
        output_path.write_text(content, encoding="utf-8")
        logger.info("Markdown报告已写入: %s", output_path)
        return output_path

    def write_reports(
        self,
        report: ViolationReport,
        output_dir: Path,
        base_name: str = "violation_report",
    ) -> tuple[Path, Path]:
        """
        同时写入JSON和Markdown报告到指定目录。

        Args:
            report: ViolationReport 实例
            output_dir: 输出目录
            base_name: 文件基础名称（不含扩展名）

        Returns:
            (JSON文件路径, Markdown文件路径) 元组
        """
        output_dir = Path(output_dir)
        json_path = self.write_json(report, output_dir / f"{base_name}.json")
        md_path = self.write_markdown(report, output_dir / f"{base_name}.md")
        logger.info("报告已写入目录: %s", output_dir)
        return json_path, md_path
