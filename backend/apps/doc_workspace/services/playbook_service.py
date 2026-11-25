"""标准库的解析、快照与版本化。

## 「按合同类型路由」的优先级

```
(org, contract_type, stance)  →  (org, contract_type, neutral)
  →  (org, "", stance)         →  (org, "", neutral)
  →  内置默认库（org=None）
```

先窄后宽：越具体的标准越优先。用「通用库」兜底而不是报错——律师手上这份合同
恰好没有专用标准时，也要能审，只是结论会粗一些。

## 版本快照为什么必须落进 run

标准会改。半年后客户问「当时为什么说这条没问题」，唯一能回答的是
`ReviewRun.playbook_snapshot` 里那一刻的 `standard_text` / `acceptable_range`。
把快照存在 run 上（而不是靠 playbook 外键回查）意味着**改标准不会篡改历史**。
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction

from ..models import Beneficiary, Playbook, PlaybookRule, PlaybookStatus, Severity, Stance

logger = logging.getLogger(__name__)

BUILTIN_NAME = "内置通用审查标准"
BUILTIN_VERSION = 1

#: 内置默认检查项（通用合同）。
#:
#: 只放**有明确法律依据、且缺失会造成可量化损失**的条款类型——「建议措辞更严谨」
#: 这类不进库，它们是过度审查的主要来源。
BUILTIN_RULES: list[dict[str, Any]] = [
    {
        "rule_key": "subject.identity",
        "clause_type": "合同主体",
        "standard_text": "各方应载明全称、统一社会信用代码/身份证号、住所与法定代表人（或负责人）。",
        "acceptable_range": "简称可以出现在正文，但首次出现必须与全称对应。",
        "legal_basis": "《民法典》第470条",
        "beneficiary": Beneficiary.NEUTRAL,
        "severity_if_missing": Severity.HIGH,
        "required": True,
    },
    {
        "rule_key": "subject.capacity",
        "clause_type": "合同主体",
        "standard_text": "签约主体应具备相应民事权利能力与行为能力；分支机构签约应取得授权。",
        "acceptable_range": "",
        "legal_basis": "《民法典》第143条、第171条",
        "beneficiary": Beneficiary.NEUTRAL,
        "severity_if_missing": Severity.HIGH,
        "required": True,
    },
    {
        "rule_key": "subject.amount_consistency",
        "clause_type": "价款",
        "standard_text": "金额应同时以大写与小写表述，且两者一致；币种明确。",
        "acceptable_range": "",
        "legal_basis": "《民法典》第470条",
        "beneficiary": Beneficiary.NEUTRAL,
        "severity_if_missing": Severity.HIGH,
        "required": True,
    },
    {
        "rule_key": "performance.deadline",
        "clause_type": "履约期限",
        "standard_text": "履行期限应给出确定日期或可算出的期间（如「自验收合格之日起 15 日内」）。",
        "acceptable_range": "「合理期限」「尽快」不可接受。",
        "legal_basis": "《民法典》第511条",
        "beneficiary": Beneficiary.NEUTRAL,
        "severity_if_missing": Severity.HIGH,
        "required": True,
    },
    {
        "rule_key": "breach.liquidated_damages_cap",
        "clause_type": "违约责任",
        "standard_text": "违约金应有上限或计算基数、比例上限（如不超过合同总价款的 20%）。",
        "acceptable_range": "略高于实际损失的约定可接受；无上限不可接受。",
        "legal_basis": "《民法典》第585条",
        "beneficiary": Beneficiary.NEUTRAL,
        "severity_if_missing": Severity.HIGH,
        "required": True,
    },
    {
        "rule_key": "dispute.jurisdiction",
        "clause_type": "争议解决",
        "standard_text": "诉讼管辖应约定在与本方便利的法院；仲裁应与诉讼二选一，且机构名称确定。",
        "acceptable_range": "「或裁或审」不可接受；机构名称不确定不可接受。",
        "legal_basis": "《民事诉讼法》第35条；《仲裁法》第16条",
        "beneficiary": Beneficiary.NEUTRAL,
        "severity_if_missing": Severity.HIGH,
        "required": True,
    },
    {
        "rule_key": "termination.unilateral",
        "clause_type": "合同解除",
        "standard_text": "应明确约定解除条件与解除后的结算、返还、赔偿安排。",
        "acceptable_range": "单方任意解除权应限定适用情形或给出补偿机制。",
        "legal_basis": "《民法典》第562条、第563条",
        "beneficiary": Beneficiary.NEUTRAL,
        "severity_if_missing": Severity.MEDIUM,
        "required": True,
    },
    {
        "rule_key": "confidentiality.scope",
        "clause_type": "保密",
        "standard_text": "保密信息的范围、期限、例外情形（已公开/合法取得）应明确。",
        "acceptable_range": "",
        "legal_basis": "《民法典》第501条",
        "beneficiary": Beneficiary.NEUTRAL,
        "severity_if_missing": Severity.MEDIUM,
        "required": False,
    },
    {
        "rule_key": "ip.ownership",
        "clause_type": "知识产权",
        "standard_text": "交付成果的知识产权归属、许可范围与后续使用应明确。",
        "acceptable_range": "",
        "legal_basis": "《民法典》第843条以下（技术合同）",
        "beneficiary": Beneficiary.NEUTRAL,
        "severity_if_missing": Severity.MEDIUM,
        "required": False,
    },
    {
        "rule_key": "force_majeure.notice",
        "clause_type": "不可抗力",
        "standard_text": "不可抗力应有通知义务、证明期限与后果（顺延/解除）安排。",
        "acceptable_range": "",
        "legal_basis": "《民法典》第590条",
        "beneficiary": Beneficiary.NEUTRAL,
        "severity_if_missing": Severity.LOW,
        "required": False,
    },
]


def ensure_builtin(*, contract_type: str = "", stance: str = Stance.NEUTRAL) -> Playbook:
    """确保内置默认库存在（幂等）。"""
    with transaction.atomic():
        playbook, created = Playbook.objects.get_or_create(
            org_id=None,
            contract_type=contract_type,
            stance=stance,
            version=BUILTIN_VERSION,
            defaults={"name": BUILTIN_NAME, "status": PlaybookStatus.ACTIVE},
        )
        if created or not playbook.rules.exists():
            for ordinal, rule in enumerate(BUILTIN_RULES):
                PlaybookRule.objects.get_or_create(
                    playbook=playbook,
                    rule_key=rule["rule_key"],
                    defaults={**{k: v for k, v in rule.items() if k != "rule_key"}, "ordinal": ordinal},
                )
    return playbook


def resolve(*, contract_type: str = "", stance: str = Stance.NEUTRAL, org_id: int | None = None) -> Playbook:
    """按「先窄后宽」找最具体的那一套标准。"""
    candidates: list[dict[str, Any]] = [
        {"org_id": org_id, "contract_type": contract_type, "stance": stance},
        {"org_id": org_id, "contract_type": contract_type, "stance": Stance.NEUTRAL},
        {"org_id": org_id, "contract_type": "", "stance": stance},
        {"org_id": org_id, "contract_type": "", "stance": Stance.NEUTRAL},
    ]
    for spec in candidates:
        found = Playbook.objects.filter(**spec, status=PlaybookStatus.ACTIVE).order_by("-version", "-id").first()
        if found is not None:
            return found
    return ensure_builtin(contract_type=contract_type, stance=stance)


def snapshot_rules(playbook: Playbook) -> list[dict[str, Any]]:
    return [rule.to_snapshot() for rule in playbook.rules.order_by("ordinal", "id")]


def bump_version(playbook: Playbook, *, note: str = "") -> Playbook:
    """复制出一份新版本（旧版本保持 ACTIVE 供历史 run 复现，新版本成为最新）。"""
    with transaction.atomic():
        latest = (
            Playbook.objects.filter(
                org_id=playbook.org_id, contract_type=playbook.contract_type, stance=playbook.stance
            )
            .order_by("-version")
            .first()
        )
        new_version = (latest.version if latest else playbook.version) + 1
        new = Playbook.objects.create(
            org_id=playbook.org_id,
            contract_type=playbook.contract_type,
            stance=playbook.stance,
            version=new_version,
            status=PlaybookStatus.ACTIVE,
            name=playbook.name,
            note=note,
        )
        for rule in playbook.rules.order_by("ordinal", "id"):
            PlaybookRule.objects.create(
                playbook=new,
                rule_key=rule.rule_key,
                ordinal=rule.ordinal,
                clause_type=rule.clause_type,
                standard_text=rule.standard_text,
                acceptable_range=rule.acceptable_range,
                legal_basis=rule.legal_basis,
                beneficiary=rule.beneficiary,
                severity_if_missing=rule.severity_if_missing,
                required=rule.required,
            )
        return new
