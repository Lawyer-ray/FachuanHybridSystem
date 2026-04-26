"""归档分类学习服务 - 从已归档材料中学习分类规则，并导出为代码文件共享给其他用户。"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from apps.contracts.models import ArchiveClassificationRule, FinalizedMaterial
from apps.contracts.services.archive.category_mapping import get_archive_category
from apps.contracts.services.contract.integrations.archive_classifier import (
    classify_archive_material,
    reload_learned_code_rules,
)

logger = logging.getLogger(__name__)

# 学习规则代码文件路径（与 archive_classifier.py 同目录）
_LEARNED_RULES_PATH = Path(__file__).parent.parent / "contract" / "integrations" / "_learned_rules.py"


class ArchiveLearningService:
    """归档分类学习服务。

    从已确认归档材料中提取"文件名关键词→归档清单项"映射规则，
    存入 DB 用于增量学习，并可导出为 Python 代码文件供其他用户共享。
    """

    def learn_from_archived_materials(self) -> dict[str, int]:
        """从所有已归档材料中学习分类规则。

        对每个有 archive_item_code 的 FinalizedMaterial：
        1. 用当前规则测试是否能正确分类
        2. 如果不能正确分类，说明用户手动修正过，从文件名提取关键词
        3. 将 (archive_category, keyword, archive_item_code) 写入规则表

        Returns:
            {"learned": 新增规则数, "updated": 更新规则数, "skipped": 跳过数}
        """
        materials = FinalizedMaterial.objects.filter(
            archive_item_code__gt="",
        ).select_related("contract")

        learned = 0
        updated = 0
        skipped = 0

        for material in materials:
            case_type = getattr(material.contract, "case_type", "")
            archive_category = get_archive_category(case_type)
            if not archive_category:
                skipped += 1
                continue

            # 用当前规则测试分类
            # 注意：material.file_path 是存储路径（非原始源路径），不含文件夹路径信息，
            # 因此文件夹路径关键词匹配不会命中。这是合理的——学习规则基于文件名关键词，
            # 只需验证文件名匹配是否能正确分类。
            current_result = classify_archive_material(
                filename=material.original_filename,
                source_path=material.file_path,
                archive_category=archive_category,
            )

            # 当前规则已能正确分类，无需学习
            if current_result.get("archive_item_code") == material.archive_item_code:
                skipped += 1
                continue

            # 需要学习：提取关键词
            keywords = self._extract_keywords(material.original_filename)
            if not keywords:
                skipped += 1
                continue

            for keyword in keywords:
                rule, created = ArchiveClassificationRule.objects.get_or_create(
                    archive_category=archive_category,
                    filename_keyword=keyword,
                    defaults={
                        "archive_item_code": material.archive_item_code,
                        "source": "learned",
                        "hit_count": 1,
                    },
                )

                if created:
                    learned += 1
                    logger.info(
                        "archive_rule_learned",
                        extra={
                            "archive_category": archive_category,
                            "keyword": keyword,
                            "archive_item_code": material.archive_item_code,
                        },
                    )
                else:
                    # 已有规则，如果目标一致则累加命中次数，否则不覆盖
                    if rule.archive_item_code == material.archive_item_code:
                        rule.hit_count += 1
                        rule.save(update_fields=["hit_count", "updated_at"])
                        updated += 1
                    # 目标不一致，保留命中次数更多的规则（不覆盖）

        logger.info(
            "archive_learning_completed",
            extra={"learned": learned, "updated": updated, "skipped": skipped},
        )

        return {"learned": learned, "updated": updated, "skipped": skipped}

    def export_rules_to_code(self) -> dict[str, Any]:
        """将 DB 中的学习规则导出为 _learned_rules.py 代码文件。

        导出格式与 _FILENAME_KEYWORD_TO_ARCHIVE_CODE 字典格式一致，
        commit + push 后其他用户 pull 即可享用学习成果。

        Returns:
            {"path": 文件路径, "rule_count": 规则数, "category_count": 分类数}
        """
        rules = ArchiveClassificationRule.objects.all().order_by(
            "archive_category", "archive_item_code", "filename_keyword"
        )

        # 按 archive_category → archive_item_code 分组
        grouped: dict[str, dict[str, list[str]]] = {}
        for rule in rules:
            cat = rule.archive_category
            code = rule.archive_item_code
            kw = rule.filename_keyword

            if cat not in grouped:
                grouped[cat] = {}
            if code not in grouped[cat]:
                grouped[cat][code] = []
            grouped[cat][code].append(kw)

        # 生成代码
        code_content = self._generate_code_file(grouped)

        # 写入文件
        _LEARNED_RULES_PATH.write_text(code_content, encoding="utf-8")

        # 重新加载代码规则到内存（使当前进程立即生效）
        reload_learned_code_rules()

        rule_count = sum(len(kws) for kws_dict in grouped.values() for kws in kws_dict.values())
        category_count = len(grouped)

        logger.info(
            "archive_rules_exported",
            extra={
                "path": str(_LEARNED_RULES_PATH),
                "rule_count": rule_count,
                "category_count": category_count,
            },
        )

        return {
            "path": str(_LEARNED_RULES_PATH),
            "rule_count": rule_count,
            "category_count": category_count,
        }

    def _extract_keywords(self, filename: str) -> list[str]:
        """从文件名中提取关键词。

        策略：
        1. 去掉扩展名
        2. 去掉案号模式（如 (2024)粤0605民初3356号）
        3. 去掉纯数字/字母
        4. 按分隔符拆分（空格、横线、下划线、点）
        5. 保留 >= 2 个中文字符的片段
        """
        # 去掉扩展名
        name = Path(filename).stem

        # 去掉案号模式
        name = re.sub(r"[(\（]\d{4}[)）][^\s]*?\d+号", "", name)

        # 去掉纯数字/字母编号
        name = re.sub(r"\b\d+\b", "", name)
        name = re.sub(r"\b[A-Za-z]+\b", "", name)

        # 按分隔符拆分
        parts = re.split(r"[\s\-_·.、,，]+", name)

        # 保留 >= 2 个中文字符的片段
        keywords = []
        for part in parts:
            part = part.strip()
            chinese_chars = re.findall(r"[\u4e00-\u9fff]", part)
            if len(chinese_chars) >= 2:
                keywords.append(part)

        return keywords

    def _generate_code_file(self, grouped: dict[str, dict[str, list[str]]]) -> str:
        """生成 _learned_rules.py 代码文件内容。"""
        lines = [
            '"""自动生成的归档分类学习规则。',
            "",
            "此文件由\"学习分类规则\"功能自动生成，请勿手动编辑。",
            "如需调整规则，请在 Admin 后台修改 ArchiveClassificationRule 后重新导出。",
            "",
            "学习规则格式与 archive_classifier.py 中 _FILENAME_KEYWORD_TO_ARCHIVE_CODE 一致，",
            "分类时优先使用学习规则，硬编码规则作为兜底。",
            '"""',
            "from __future__ import annotations",
            "",
        ]

        if not grouped:
            lines.append("# 从已归档材料中学习到的文件名关键词 → archive_item_code 映射")
            lines.append("LEARNED_FILENAME_KEYWORD_TO_ARCHIVE_CODE: dict[str, dict[str, list[str]]] = {}")
            lines.append("")
            return "\n".join(lines)

        lines.append("# 从已归档材料中学习到的文件名关键词 → archive_item_code 映射")
        lines.append("LEARNED_FILENAME_KEYWORD_TO_ARCHIVE_CODE: dict[str, dict[str, list[str]]] = {")

        for cat in sorted(grouped.keys()):
            lines.append(f'    "{cat}": {{')
            for code in sorted(grouped[cat].keys()):
                keywords = grouped[cat][code]
                kw_str = ", ".join(f'"{kw}"' for kw in keywords)
                lines.append(f'        "{code}": [{kw_str}],')
            lines.append("    },")

        lines.append("}")
        lines.append("")
        return "\n".join(lines)
