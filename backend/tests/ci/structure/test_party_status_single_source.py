"""Structure guard: 当事人诉讼地位常量必须有唯一来源。

背景（2026-11 代码质量审查实证）
--------------------------------
生产库 ``cases_caseparty.legal_status`` 是**中英文混存**的（英文枚举 + 早期录入的中文：
``defendant 73 / plaintiff 45 / 被告 3`` 实测）。这套「哪一方」的判定曾在**四处各写一份**：

1. ``plugins/court_automation/filing/schemas.py``    —— 含中文，已修
2. ``plugins/court_automation/guarantee/schemas.py`` —— **仅英文**，未修
3. ``apps/cases/services/case_readiness_service.py`` —— 含中文但**少了「原审原告」**
4. ``plugins/court_automation/guarantee/helpers.py`` —— 又一份仅英文的局部副本

只认英文的后果不是崩溃，而是**静默判错**：``our_party_is_plaintiff_side`` 对
``legal_status="原告"`` 的我方案件返回 ``false``，前端据此提示「我方不是原告方」，
律师被误导。这类「复制一份常量」的债必须靠结构守卫拦住。

本测试守三件事：
- A. 权威模块本身必须中英文齐备（防有人删中文项）
- B. 各消费方必须**引用同一个对象**（防再复制一份）
- C. 源码里不得出现新的自建诉讼地位字面量集合
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[3]

AUTHORITY_MODULE = "apps/cases/domain/party_status.py"

#: 必须引用权威常量的消费方（新增消费方时加到这里）。
CONSUMERS: list[str] = [
    "apps/cases/services/case_readiness_service.py",
    "plugins/court_automation/filing/schemas.py",
    "plugins/court_automation/guarantee/schemas.py",
]

#: 允许出现诉讼地位字面量的文件（权威模块本身，以及历史存量）。
#: 只减不增：清理一处就从这里删一行。
ALLOWED_LITERAL_FILES: set[str] = {
    # 权威模块：字面量本来就写在这里
    AUTHORITY_MODULE,
    # 提示词/示例文案里的「原告」「申请人」是自然语言，不是判定集合
    "apps/documents/services/placeholders/litigation/execution_request_parser.py",
    "apps/automation/services/scraper/sites/guarantee/dialog_field_filling.py",
}

#: 判定诉讼地位的典型字面量特征（出现这些组合说明有人在自建集合）。
_SIDE_LITERAL_MARKERS: tuple[str, ...] = (
    "orig_plaintiff",
    "orig_defendant",
    "criminal_defendant",
    "appellant",
)


@pytest.mark.unit
class TestPartyStatusSingleSource:
    """诉讼地位常量唯一来源守卫。"""

    def test_authority_module_covers_chinese_and_english(self) -> None:
        """A. 权威模块必须同时含英文枚举与早期录入的中文。"""
        from apps.cases.domain.party_status import DEFENDANT_SIDE_STATUSES, PLAINTIFF_SIDE_STATUSES, THIRD_SIDE_STATUSES

        # 英文枚举
        assert {"plaintiff", "applicant", "appellant", "orig_plaintiff"} <= PLAINTIFF_SIDE_STATUSES
        assert {"defendant", "respondent", "appellee", "orig_defendant"} <= DEFENDANT_SIDE_STATUSES

        # 早期录入的中文——删掉这些就是回归历史缺陷
        assert {"原告", "申请人", "上诉人", "原审原告"} <= PLAINTIFF_SIDE_STATUSES
        assert {"被告", "被申请人", "被上诉人"} <= DEFENDANT_SIDE_STATUSES

        # 第三人一侧也必须有中文
        assert {"第三人"} <= THIRD_SIDE_STATUSES

    @pytest.mark.skipif(
        not (BACKEND_DIR / "plugins/court_automation/filing/schemas.py").exists(),
        reason="plugins 子模块未拉取（CI 无跨仓权限），跳过插件侧同一性校验",
    )
    def test_consumers_share_the_same_object(self) -> None:
        """B. 消费方必须引用同一对象，而不是各建一份等价副本。

        本条要 import 插件模块验证「是否同一个对象」，plugins 未拉取时无从校验；
        但 A（权威模块中英文齐备）与 C（不新人自建字面量）仍完整生效。
        """
        from apps.cases.domain.party_status import DEFENDANT_SIDE_STATUSES, PLAINTIFF_SIDE_STATUSES

        # plugins 侧：schemas 用 `_` 前缀别名 re-export，须与权威同一对象
        from plugins.court_automation.filing.schemas import _DEFENDANT_SIDE_STATUSES as filing_defendant
        from plugins.court_automation.filing.schemas import _PLAINTIFF_SIDE_STATUSES as filing_plaintiff
        from plugins.court_automation.guarantee.schemas import _PLAINTIFF_SIDE_STATUSES as guarantee_plaintiff
        from plugins.court_automation.guarantee.schemas import _RESPONDENT_SIDE_STATUSES as guarantee_respondent

        assert filing_plaintiff is PLAINTIFF_SIDE_STATUSES
        assert guarantee_plaintiff is PLAINTIFF_SIDE_STATUSES
        assert filing_defendant is DEFENDANT_SIDE_STATUSES
        assert guarantee_respondent is DEFENDANT_SIDE_STATUSES

    def test_consumers_do_not_define_own_literal_sets(self) -> None:
        """C. 消费方源码里不得再出现自建的诉讼地位字面量集合。"""
        offenders: list[str] = []

        for consumer in CONSUMERS:
            path = BACKEND_DIR / consumer
            if not path.exists():
                continue
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)

            for node in ast.walk(tree):
                if not isinstance(node, ast.Set):
                    continue
                literals = {elm.value for elm in node.elts if isinstance(elm, ast.Constant)}
                if not literals:
                    continue
                hits = sum(1 for marker in _SIDE_LITERAL_MARKERS if marker in literals)
                # 同时出现 2 个以上特征值，基本可判定是自建的诉讼地位集合
                if hits >= 2:
                    offenders.append(f"{consumer}:{node.lineno} -> {sorted(literals)}")

        assert offenders == [], "检测到自建诉讼地位字面量集合，请改为引用 apps.cases.domain.party_status：\n" + "\n".join(
            offenders
        )

    def test_no_new_literal_files_outside_allowlist(self) -> None:
        """C'. 全仓扫描：出现诉讼地位字面量的文件必须在白名单内。"""
        offenders: list[str] = []

        for root_name in ("apps", "plugins", "mcp_server"):
            root = BACKEND_DIR / root_name
            if not root.exists():
                continue
            for path in root.rglob("*.py"):
                rel = path.relative_to(BACKEND_DIR).as_posix()
                if "__pycache__" in rel or "/migrations/" in rel or rel.startswith("tests/"):
                    continue
                if rel in ALLOWED_LITERAL_FILES:
                    continue
                try:
                    tree = ast.parse(path.read_text(encoding="utf-8"))
                except SyntaxError:  # pragma: no cover - 语法错误由 ruff/编译期拦
                    continue

                for node in ast.walk(tree):
                    if not isinstance(node, ast.Set):
                        continue
                    literals = {elm.value for elm in node.elts if isinstance(elm, ast.Constant)}
                    if sum(1 for marker in _SIDE_LITERAL_MARKERS if marker in literals) >= 2:
                        offenders.append(f"{rel}:{node.lineno}")
                        break

        assert offenders == [], (
            "下列文件自建了诉讼地位集合，请改为引用 apps.cases.domain.party_status"
            "（确实属于历史存量的，加入本测试的 ALLOWED_LITERAL_FILES 并注明原因）：\n" + "\n".join(offenders)
        )
