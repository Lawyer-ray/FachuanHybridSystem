#!/usr/bin/env python3
"""手动为特定Django Model添加id属性注解"""

from __future__ import annotations

import logging
from pathlib import Path

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


# 需要添加id注解的Model类及其文件路径
MODELS_TO_FIX = {
    "apps/automation/models/court_sms.py": ["CourtSMS"],
    "apps/cases/models/case.py": ["Case", "CaseNumber", "SupervisingAuthority"],
    "apps/cases/models/party.py": ["CaseParty", "CaseAssignment", "CaseAccessGrant"],
    "apps/cases/models/log.py": ["CaseLog", "CaseLogAttachment", "CaseLogVersion"],
    "apps/cases/models/chat.py": ["CaseChat", "ChatAuditLog"],
    "apps/contracts/models/contract.py": ["Contract"],
    "apps/contracts/models/party.py": ["ContractParty", "ContractAssignment"],
    "apps/contracts/models/payment.py": ["ContractPayment"],
    "apps/contracts/models/supplementary.py": ["SupplementaryAgreement"],
    "apps/client/models/client.py": ["Client"],
    "apps/client/models/identity_doc.py": ["ClientIdentityDoc"],
    "apps/client/models/property_clue.py": ["PropertyClue"],
    "apps/organization/models/lawyer.py": ["Lawyer"],
    "apps/organization/models/law_firm.py": ["LawFirm"],
    "apps/organization/models/team.py": ["Team"],
    "apps/automation/models/scraper.py": ["ScraperTask"],
    "apps/automation/models/token.py": ["CourtToken"],
}


def add_id_to_class(lines: list[str], class_name: str) -> tuple[list[str], bool]:
    """
    为指定的类添加id注解

    Returns:
        (修改后的行列表, 是否修改)
    """
    new_lines = []
    modified = False
    i = 0

    while i < len(lines):
        line = lines[i]

        # 查找类定义
        if f"class {class_name}(" in line and "models.Model" in line:
            new_lines.append(line)
            i += 1

            # 跳过docstring
            if i < len(lines) and ('"""' in lines[i] or "'''" in lines[i]):
                new_lines.append(lines[i])
                quote = '"""' if '"""' in lines[i] else "'''"

                # 如果docstring在同一行结束
                if lines[i].count(quote) >= 2:
                    i += 1
                else:
                    # 多行docstring
                    i += 1
                    while i < len(lines) and quote not in lines[i]:
                        new_lines.append(lines[i])
                        i += 1
                    if i < len(lines):
                        new_lines.append(lines[i])
                        i += 1

            # 跳过空行和注释
            while i < len(lines) and (lines[i].strip() == "" or lines[i].strip().startswith("#")):
                new_lines.append(lines[i])
                i += 1

            # 检查是否已有id注解
            if i < len(lines) and "id:" in lines[i]:
                logger.info(f"  类 {class_name} 已有id注解，跳过")
                new_lines.append(lines[i])
                i += 1
                continue

            # 添加id注解
            indent = "    "
            new_lines.append(f"{indent}id: int\n")
            logger.info(f"  为类 {class_name} 添加id注解")
            modified = True
            continue

        new_lines.append(line)
        i += 1

    return new_lines, modified


def process_file(file_path: Path, class_names: list[str]) -> bool:
    """
    处理单个文件

    Returns:
        是否修改了文件
    """
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    modified = False
    for class_name in class_names:
        lines, class_modified = add_id_to_class(lines, class_name)
        if class_modified:
            modified = True

    if modified:
        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

    return modified


def main() -> None:
    """主函数"""
    backend_path = Path(__file__).parent.parent

    logger.info("=" * 80)
    logger.info("开始为Django Model添加id属性注解")
    logger.info("=" * 80)

    total_files = len(MODELS_TO_FIX)
    modified_count = 0

    for rel_path, class_names in MODELS_TO_FIX.items():
        file_path = backend_path / rel_path

        if not file_path.exists():
            logger.warning(f"文件不存在: {rel_path}")
            continue

        logger.info(f"\n处理: {rel_path}")

        if process_file(file_path, class_names):
            modified_count += 1

    logger.info("\n" + "=" * 80)
    logger.info(f"完成！修改了 {modified_count}/{total_files} 个文件")
    logger.info("=" * 80)


if __name__ == "__main__":
    main()
