"""东盟十国标准库分册的结构约束。

## 为什么这些断言值得写

标准库是审查的「尺子」。分册里有 50+ 条规则时，最容易出的不是「写得不好」，
而是**四种结构性问题**——每一条都对应一个真实后果：

| 断言 | 不守会怎样 |
|---|---|
| 每个法域都有分册、且东帝汶没有 | 选到东帝汶就悄悄用中国法审（比没有更糟） |
| `rule_key` 前缀 = 国家码且全局唯一 | 驳回理由回流按 `rule_key` 统计，撞号会让 A 国的降权影响 B 国 |
| 不许出现中国法依据 | 泰国分册里混进《民法典》，等于换了个国家继续审错法 |
| 引用形态必须声明档位（`Section N` 或「条号待核」） | 编一个像样的条号，律师核不上就再也不信这个功能 |
| 每条规则都要有 mandatory 与 before 阶段 | 全是「可谈的商业条款」，强制项（能不能持有土地）永远报不出来 |
"""

from __future__ import annotations

import re

import pytest

from apps.doc_workspace.models import Consequence, RuleClass, Severity, Stage
from apps.doc_workspace.services import playbook_asean, playbook_service, review_pipeline

pytestmark = pytest.mark.django_db

#: 有分册的东盟国家（BARLC 有数据）。东帝汶（TL）不在其中，见用例 `test_timor_leste_*`。
ASEAN_WITH_CORPUS = ["TH", "VN", "MY", "SG", "ID", "PH", "KH", "LA", "MM", "BN"]

_SECTION_RE = re.compile(r"(?:Section|Article)\s*[0-9]", re.IGNORECASE)


def test_all_ten_asean_countries_have_a_corpus() -> None:
    assert sorted(playbook_asean.RULES_BY_JURISDICTION) == sorted(ASEAN_WITH_CORPUS)


def test_timor_leste_only_gets_citation_rules() -> None:
    """东帝汶在 BARLC 没有数据：只给引用完整性规则，绝不拿中国法或邻国法冒充。"""
    keys = [r["rule_key"] for r in playbook_service.rules_for(jurisdiction="TL")]
    assert keys == [r["rule_key"] for r in playbook_asean.CITATION_RULES]
    assert "仅引用完整性" in playbook_service.builtin_name("TL")


@pytest.mark.parametrize("code", ASEAN_WITH_CORPUS)
def test_rule_keys_are_prefixed_and_unique(code: str) -> None:
    rules = playbook_asean.RULES_BY_JURISDICTION[code]
    keys = [r["rule_key"] for r in rules]
    assert len(keys) == len(set(keys)), "同一法域内 rule_key 重复"
    assert all(k.startswith(code.lower() + ".") for k in keys), "rule_key 前缀必须是国家码"


def test_rule_keys_are_unique_across_countries() -> None:
    """跨法域也不能撞号：驳回理由回流按 rule_key 统计。"""
    all_keys = [r["rule_key"] for rules in playbook_asean.RULES_BY_JURISDICTION.values() for r in rules]
    assert len(all_keys) == len(set(all_keys))


@pytest.mark.parametrize("code", ASEAN_WITH_CORPUS)
def test_citation_grade_is_explicit(code: str) -> None:
    """每条规则的引用必须声明档位：要么写到条号，要么明确标「条号待核」。"""
    for rule in playbook_asean.RULES_BY_JURISDICTION[code]:
        basis = str(rule["legal_basis"])
        assert basis, f"{rule['rule_key']} 没有法律依据"
        assert playbook_asean.PENDING in basis or _SECTION_RE.search(basis), (
            f"{rule['rule_key']} 的引用既没有条号也没标「条号待核」：{basis}"
        )


@pytest.mark.parametrize("code", ASEAN_WITH_CORPUS)
def test_no_chinese_domestic_statutes_in_foreign_corpus(code: str) -> None:
    for rule in playbook_asean.RULES_BY_JURISDICTION[code]:
        basis = str(rule["legal_basis"])
        for domestic in ("民法典", "城市房地产管理法", "劳动合同法", "公司法"):
            assert domestic not in basis, f"{rule['rule_key']} 引用了中国法：{basis}"


@pytest.mark.parametrize("code", ASEAN_WITH_CORPUS)
def test_every_country_has_mandatory_and_predicate_rules(code: str) -> None:
    """每个法域都要有「能不能干这件事」的强制项，否则强制风险一条都报不出来。"""
    rules = playbook_asean.RULES_BY_JURISDICTION[code]
    assert len(rules) >= 4
    assert any(r["rule_class"] == RuleClass.MANDATORY for r in rules)
    assert any(r["stage"] == Stage.BEFORE for r in rules)
    assert any(r["rule_class"] == RuleClass.MANDATORY and r["stage"] == Stage.BEFORE for r in rules)


@pytest.mark.parametrize("code", ASEAN_WITH_CORPUS)
def test_enum_fields_are_valid(code: str) -> None:
    for rule in playbook_asean.RULES_BY_JURISDICTION[code]:
        assert rule["severity_if_missing"] in Severity.values
        assert rule["rule_class"] in RuleClass.values
        assert rule["stage"] in Stage.values
        assert rule["consequence"] in Consequence.values
        assert str(rule["standard_text"]).strip()


@pytest.mark.parametrize("code", ASEAN_WITH_CORPUS)
def test_rules_for_appends_citation_rules(code: str) -> None:
    keys = [r["rule_key"] for r in playbook_service.rules_for(jurisdiction=code)]
    assert "foreign_law.citation_invalid" in keys
    assert keys[0].startswith(code.lower() + ".")


def test_each_jurisdiction_gets_its_own_playbook() -> None:
    th = playbook_service.resolve(jurisdiction="TH")
    vn = playbook_service.resolve(jurisdiction="VN")
    assert th.pk != vn.pk
    assert "泰国" in th.name
    assert "越南" in vn.name
    th_keys = set(th.rules.values_list("rule_key", flat=True))
    vn_keys = set(vn.rules.values_list("rule_key", flat=True))
    assert th_keys & vn_keys, "两国的库应共享引用完整性规则"
    assert "th.lease_term_limit" in th_keys
    assert "vn.labour_severance" in vn_keys
    assert "th.lease_term_limit" not in vn_keys


@pytest.mark.parametrize("code", ASEAN_WITH_CORPUS)
def test_prompt_carries_the_country_rules_and_persona(code: str) -> None:
    rules = playbook_service.rules_for(jurisdiction=code)
    messages = review_pipeline.build_prompt(
        rules=rules,
        contract_text="示例合同",
        stance="neutral",
        contract_type="",
        jurisdiction=code,
    )
    system = messages[0]["content"]
    assert "不许凭记忆引用外国法条文" in system
    for rule in rules:
        assert rule["rule_key"] in system
    assert playbook_asean.JURISDICTION_LABEL[code] + "法" in system


def test_builtin_rules_drop_machine_fields_before_insert() -> None:
    """标准库带的 `verify_law` / `verify_section` 是给核验命令用的，不是数据库列。

    不按模型字段表过滤的话，`PlaybookRule.objects.create(**rule)` 会直接 TypeError，
    而这条路径只在「首次建内置库」时走到——单测不覆盖就会在生产首次审查时炸。
    """
    book = playbook_service.resolve(jurisdiction="ID")
    rule = book.rules.get(rule_key="id.land_ownership_foreign")
    assert rule.rule_class == RuleClass.MANDATORY
    assert "Article 21" in rule.legal_basis
    assert not hasattr(rule, "verify_law")


def test_verify_index_points_at_barlc_titles() -> None:
    """核验目标必须是 BARLC 的标题，不是展示串（否则会误报「引用了不存在的法」）。"""
    for code, rules in playbook_asean.RULES_BY_JURISDICTION.items():
        for rule in rules:
            if str(rule.get("verify_law") or "").startswith("（"):
                continue
            assert "（" not in str(rule["verify_law"]), f"{code}/{rule['rule_key']} 的核验法名混入了中文括注"
            assert "Section" not in str(rule["verify_law"]), f"{code}/{rule['rule_key']} 的核验法名混入了条号"
