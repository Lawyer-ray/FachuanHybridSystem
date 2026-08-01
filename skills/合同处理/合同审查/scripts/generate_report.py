"""
合同修订版生成脚本

基于用户确认后的审查结果，在原合同上添加修订模式（Track Changes）和批注（Comments）。
输出文件名：{原文件名}[修订版]V1_{YYYYMMDD}.docx

所有修订和批注以 "Lawyer" 身份标注。

依赖：python-docx（已在 backend/pyproject.toml 中声明）

注意：Track Changes 的 OOXML 实现较为复杂，当前版本为基础骨架，
      完整的 Track Changes 支持需要直接操作 OOXML XML。
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

logger = logging.getLogger(__name__)

# 修订作者
AUTHOR = "Lawyer"


def build_output_filename(original_path: Path, version: str = "V1", date_str: str | None = None) -> str:
    """
    生成输出文件名

    Args:
        original_path: 原合同文件路径
        version: 版本号，默认 V1
        date_str: 日期字符串，默认当天

    Returns:
        输出文件名，如：买卖合同[修订版]V1_20260801.docx
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")
    stem = original_path.stem
    return f"{stem}[修订版]{version}_{date_str}.docx"


def add_comment(paragraph, comment_text: str, author: str = AUTHOR) -> None:
    """
    给段落添加批注

    Args:
        paragraph: docx 段落对象
        comment_text: 批注内容
        author: 批注作者
    """
    # 获取或创建 comments part
    # 注意：python-docx 不原生支持批注，需要操作 OOXML
    # 这是基础实现，完整版本需要更复杂的 OOXML 操作
    logger.debug("添加批注到段落: %s (作者: %s)", paragraph.text[:30], author)


def apply_review(
    original_path: Path,
    findings: list[dict],
    output_dir: Path,
    version: str = "V1",
) -> Path:
    """
    应用审查结果到原合同，生成修订版

    Args:
        original_path: 原合同 .docx 文件路径
        findings: 用户确认的审查结果列表，结构如下：
            [
                {
                    "id": 1,
                    "clause": "第3条 付款条件",
                    "risk_level": "critical",
                    "action": "revise",       # "revise" = 修订模式, "comment" = 批注
                    "original_text": "甲方应在合同签订后支付全部款项",
                    "revised_text": "甲方应在验收合格后30日内支付款项",
                    "comment": "原条款要求预付全款，对我方不利"
                }
            ]
        output_dir: 输出目录
        version: 版本号

    Returns:
        输出文件路径
    """
    doc = Document(str(original_path))

    # 遍历文档段落，匹配并应用修改
    for finding in findings:
        action = finding.get("action", "comment")
        original_text = finding.get("original_text", "")
        revised_text = finding.get("revised_text", "")
        comment_text = finding.get("comment", "")

        # 查找匹配的段落
        matched = False
        for para in doc.paragraphs:
            if original_text and original_text in para.text:
                matched = True
                if action == "revise" and revised_text:
                    # 修订模式：标记原文为删除，新文为插入
                    _apply_track_change(para, original_text, revised_text)
                elif action == "comment" and comment_text:
                    # 批注模式：保留原文，添加批注
                    add_comment(para, comment_text)
                break

        if not matched:
            logger.warning("未找到匹配段落: %s", original_text[:30])

    # 保存输出文件
    output_filename = build_output_filename(original_path, version)
    output_path = output_dir / output_filename
    doc.save(str(output_path))
    return output_path


def _apply_track_change(paragraph, old_text: str, new_text: str) -> None:
    """
    在段落中应用修订模式（Track Changes）

    将 old_text 标记为删除（红色删除线），new_text 标记为插入（红色下划线）。
    修订作者为 AUTHOR。

    注意：python-docx 不原生支持 Track Changes，
    完整实现需要直接操作 OOXML 的 w:del 和 w:ins 元素。
    当前为基础占位实现。
    """
    # 后续需实现完整的 OOXML Track Changes
    # 参考：http://officeopenxml.com/WPcontentTracking.php
    # 需要在 paragraph._element 中插入：
    #   <w:del w:id="..." w:author="Lawyer" w:date="...">
    #     <w:r><w:delText>原文</w:delText></w:r>
    #   </w:del>
    #   <w:ins w:id="..." w:author="Lawyer" w:date="...">
    #     <w:r><w:t>新文</w:t></w:r>
    #   </w:ins>
    logger.debug("Track Changes: [%s] → [%s]", old_text[:20], new_text[:20])


def main():
    """命令行入口

    用法：
        python generate_report.py <original.docx> <findings.json> <output_dir> [--version V1]

    findings.json 结构参见 apply_review 的 docstring。
    """
    if len(sys.argv) < 4:
        logger.error("用法: python generate_report.py <original.docx> <findings.json> <output_dir> [--version V1]")
        sys.exit(1)

    original_path = Path(sys.argv[1])
    findings_path = Path(sys.argv[2])
    output_dir = Path(sys.argv[3])
    output_dir.mkdir(parents=True, exist_ok=True)

    version = "V1"
    if "--version" in sys.argv:
        idx = sys.argv.index("--version")
        if idx + 1 < len(sys.argv):
            version = sys.argv[idx + 1]

    with open(findings_path, encoding="utf-8") as f:
        findings = json.load(f)

    output_path = apply_review(original_path, findings, output_dir, version)
    logger.info("✅ 修订版已生成: %s", output_path)


if __name__ == "__main__":
    main()
