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
        3. 检查关键词是否有歧义（同一关键词被映射到不同 code → 跳过）
        4. 将 (archive_category, keyword, archive_item_code) 写入规则表

        Returns:
            {"learned": 新增规则数, "updated": 更新规则数, "skipped": 跳过数,
             "ambiguous": 歧义跳过数}
        """
        materials = FinalizedMaterial.objects.filter(
            archive_item_code__gt="",
        ).select_related("contract")

        learned = 0
        updated = 0
        skipped = 0
        ambiguous = 0

        # 先扫描一遍，统计每个 (archive_category, keyword) → Set[code] 的映射
        # 用于检测歧义关键词
        keyword_code_map: dict[tuple[str, str], set[str]] = {}
        material_keywords: dict[int, list[str]] = {}  # material_id → [keywords]

        for material in materials:
            case_type = getattr(material.contract, "case_type", "")
            archive_category = get_archive_category(case_type)
            if not archive_category:
                continue

            keywords = self._extract_keywords(material.original_filename)
            material_keywords[material.id] = keywords

            for kw in keywords:
                key = (archive_category, kw)
                if key not in keyword_code_map:
                    keyword_code_map[key] = set()
                keyword_code_map[key].add(material.archive_item_code)

        # 找出歧义关键词（同一关键词映射到 >1 个不同 code）
        ambiguous_keys: set[tuple[str, str]] = {key for key, codes in keyword_code_map.items() if len(codes) > 1}

        if ambiguous_keys:
            logger.info(
                "ambiguous_keywords_detected",
                extra={"count": len(ambiguous_keys), "keywords": [f"{k[0]}::{k[1]}" for k in ambiguous_keys]},
            )

        # 第二遍：实际写入规则（跳过歧义关键词）
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
            keywords = material_keywords.get(material.id, [])
            if not keywords:
                skipped += 1
                continue

            has_ambiguous = False
            for kw in keywords:
                if (archive_category, kw) in ambiguous_keys:
                    ambiguous += 1
                    has_ambiguous = True
                    continue

                rule, created = ArchiveClassificationRule.objects.get_or_create(
                    archive_category=archive_category,
                    filename_keyword=kw,
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
                            "keyword": kw,
                            "archive_item_code": material.archive_item_code,
                        },
                    )
                else:
                    # 已有规则，如果目标一致则累加命中次数，否则不覆盖
                    if rule.archive_item_code == material.archive_item_code:
                        rule.hit_count += 1
                        rule.save(update_fields=["hit_count", "updated_at"])
                        updated += 1

            if has_ambiguous and not any((archive_category, kw) not in ambiguous_keys for kw in keywords):
                skipped += 1

        logger.info(
            "archive_learning_completed",
            extra={"learned": learned, "updated": updated, "skipped": skipped, "ambiguous": ambiguous},
        )

        return {"learned": learned, "updated": updated, "skipped": skipped, "ambiguous": ambiguous}

    def export_rules_to_code(self) -> dict[str, Any]:
        """将 DB 中的学习规则导出为 _learned_rules.py 代码文件。

        导出格式与 _FILENAME_KEYWORD_TO_ARCHIVE_CODE 字典格式一致，
        commit + push 后其他用户 pull 即可享用学习成果。

        导出时会合并代码文件中的已有规则，避免丢失之前导出的规则。

        Returns:
            {"path": 文件路径, "rule_count": 规则数, "category_count": 分类数}
        """
        db_rules = ArchiveClassificationRule.objects.all().order_by(
            "archive_category", "archive_item_code", "filename_keyword"
        )

        # 按 archive_category → archive_item_code 分组 DB 规则
        grouped: dict[str, dict[str, list[str]]] = {}
        for rule in db_rules:
            cat = rule.archive_category
            code = rule.archive_item_code
            kw = rule.filename_keyword

            if cat not in grouped:
                grouped[cat] = {}
            if code not in grouped[cat]:
                grouped[cat][code] = []
            grouped[cat][code].append(kw)

        # 合并代码文件中已有的规则（避免丢失之前导出的规则）
        try:
            from apps.contracts.services.contract.integrations._learned_rules import (
                LEARNED_FILENAME_KEYWORD_TO_ARCHIVE_CODE as code_rules,
            )

            for cat, code_map in code_rules.items():
                if cat not in grouped:
                    grouped[cat] = {}
                for code, keywords in code_map.items():
                    if code not in grouped[cat]:
                        grouped[cat][code] = []
                    # 只追加 DB 中没有的关键词
                    existing = set(grouped[cat][code])
                    for kw in keywords:
                        if kw not in existing:
                            grouped[cat][code].append(kw)
                            existing.add(kw)
        except ImportError:
            pass

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
        2. 去掉括号及括号内容（如案卷封面（某某案）→ 案卷封面）
        3. 去掉案号模式（如 (2024)粤0101民初1001号）
        4. 去掉页码模式（如 第6页）
        5. 去掉纯数字/字母
        6. 按分隔符拆分（含中文分隔符）
        7. 保留含文书类型关键词的片段（白名单机制）
        """
        # 去掉扩展名
        name = Path(filename).stem

        # 去掉括号及括号内容（中文和英文括号）
        name = re.sub(r"[（(][^）)]*[）)]", "", name)

        # 去掉案号模式
        name = re.sub(r"[(\（]\d{4}[)）][^\s]*?\d+号", "", name)

        # 去掉页码模式
        name = re.sub(r"第\d+页", "", name)

        # 去掉纯数字/字母编号
        name = re.sub(r"\d+", "", name)
        name = re.sub(r"[A-Za-z]+", "", name)

        # 按分隔符拆分
        parts = re.split(r"[\s\-_·.、,，【】\[\]{}]+", name)

        # 白名单过滤：只保留含文书类型关键词的片段
        keywords = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            chinese_chars = re.findall(r"[\u4e00-\u9fff]", part)
            if len(chinese_chars) < 2:
                continue

            # 白名单：含以下文书类型关键词的才视为有效学习关键词
            if _contains_document_keyword(part):
                # 脱壳：只保留文书关键词部分，剔除前后粘着的非文书内容
                # 如 "张三起诉状" → "起诉状"，"佛山市某某公司起诉状" → "起诉状"
                stripped_kw = _strip_non_keyword_parts(part)
                if stripped_kw:
                    keywords.append(stripped_kw)

        return keywords

    def _generate_code_file(self, grouped: dict[str, dict[str, list[str]]]) -> str:
        """生成 _learned_rules.py 代码文件内容。"""
        lines = [
            '"""自动生成的归档分类学习规则。',
            "",
            '此文件由"学习分类规则"功能自动生成，请勿手动编辑。',
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


# ============================================================
# 模块级辅助函数
# ============================================================

# 文书类型关键词白名单（模块级常量，避免每次调用重复创建）
_DOCUMENT_KEYWORDS: tuple[str, ...] = (
    # 诉讼/刑事文书
    "起诉状",
    "起诉书",
    "答辩状",
    "上诉状",
    "申请书",
    "申诉书",
    "代理词",
    "辩护词",
    "辩护意见",
    "代理意见",
    "判决书",
    "裁定书",
    "调解书",
    "决定书",
    "传票",
    "通知",
    "受理",
    "保全",
    "查封",
    "执行",
    "续封",
    "授权委托",
    "委托书",
    "所函",
    # 证据/调查
    "证据",
    "调查",
    "取证",
    "阅卷",
    # 笔录
    "笔录",
    "庭审",
    "开庭",
    "审理",
    "会见",
    "谈话",
    "询问",
    # 案卷/归档
    "案卷",
    "封面",
    "目录",
    "归档",
    "登记",
    "小结",
    "工作日记",
    "办案",
    "监督卡",
    "服务质量",
    "合同正本",
    # 非诉文书
    "律师函",
    "法律意见",
    # 通用
    "清单",
    "明细",
    "报告",
    "意见",
)


def _contains_document_keyword(text: str) -> bool:
    """判断文本是否包含文书类型关键词（白名单机制）。

    只有含文书类型关键词的片段才有通用分类价值。
    例如："案卷封面" ✓（含"封面"），"张福裕案件" ✗（不含文书关键词）
    """
    return any(kw in text for kw in _DOCUMENT_KEYWORDS)


def _strip_non_keyword_parts(text: str) -> str:
    """脱壳：从关键词中剥离前后粘着的非文书内容，只保留文书关键词部分。

    防止当事人姓名、公司名等隐私内容混入学习规则。

    策略：
    1. 精确匹配白名单 → 直接返回
    2. 找到最长匹配文书关键词
    3. 检查关键词前后是否粘着 2-4 个非文书中文字符（疑似人名/公司名）
    4. 如有，只保留文书关键词部分
    5. 如无（复合文书名），保留原文

    示例：
    - "张三起诉状" → "起诉状"（前面2字"张三"不属文书词）
    - "佛山市某某公司起诉状" → "起诉状"（前面7字不属文书词）
    - "案卷封面" → "案卷封面"（本身就是完整文书词）
    - "缴纳保全费通知书" → "缴纳保全费通知书"（复合文书词，无粘着）
    """
    # 精确匹配白名单关键词 → 直接返回
    if text in _DOCUMENT_KEYWORDS:
        return text

    # 找到文本中最长的匹配文书关键词
    best_match = ""
    for kw in _DOCUMENT_KEYWORDS:
        if kw in text and len(kw) > len(best_match):
            best_match = kw

    if not best_match:
        return text

    # 如果文本 = 匹配关键词 → 无需剥离
    if text == best_match:
        return text

    # 检查文书关键词前面/后面粘着的内容
    idx = text.index(best_match)
    prefix = text[:idx]
    suffix = text[idx + len(best_match):]

    # 判断前缀/后缀是否属于"非文书粘着内容"
    # 规则：如果前缀/后缀中所有中文字符都不属于任何文书关键词 → 疑似人名/公司名
    has_non_keyword_prefix = _is_non_keyword_attachment(prefix)
    has_non_keyword_suffix = _is_non_keyword_attachment(suffix)

    if has_non_keyword_prefix or has_non_keyword_suffix:
        # 有粘着 → 只保留文书关键词
        return best_match

    # 无粘着 → 保留原文（合法复合文书名）
    return text


def _is_non_keyword_attachment(text: str) -> bool:
    """判断文本是否为非文书关键词的粘着内容（疑似人名/公司名）。

    如果文本中所有中文字符都不属于任何文书关键词，则视为粘着内容。
    """
    if not text:
        return False

    # 提取中文字符
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
    if not chinese_chars:
        return False  # 纯符号/空格，不算粘着

    # 检查文本中的每个中文字符是否出现在任何文书关键词中
    # 更高效的做法：检查整个文本是否与任何文书关键词有交集
    text_has_keyword_overlap = any(kw in text for kw in _DOCUMENT_KEYWORDS)

    # 如果文本与任何文书关键词无交集 → 疑似人名/公司名
    return not text_has_keyword_overlap
