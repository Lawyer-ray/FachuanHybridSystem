from __future__ import annotations

from typing import TypedDict

from django.db import transaction

from apps.documents.models import ProxyMatterRule


class ProxyMatterRuleSeed(TypedDict):
    case_types: list[str]
    case_type: str | None
    case_stage: str | None
    legal_statuses: list[str]
    legal_status_match_mode: str
    items_text: str
    priority: int
    is_active: bool


DEFAULT_PROXY_MATTER_RULES: tuple[ProxyMatterRuleSeed, ...] = (
    {
        "case_types": ["civil"],
        "case_type": "civil",
        "case_stage": "enforcement",
        "legal_statuses": ["applicant"],
        "legal_status_match_mode": "any",
        "items_text": "申请执行；代为调查、提供证据；申请财产保全或证据保全；追加/变更被执行人；执行和解；申请撤回执行；申请执行异议；申请恢复执行；执行异议答辩；代为出庭；执行和解；代为签署和受领有关文书；出席执行听证会；转委托；申请撤销、中止和终结执行；代为收取、保管执行财物和文件；代为支付诉讼或诉讼相关费用以及代收和保管法院退还的该类费用。",
        "priority": 100,
        "is_active": True,
    },
    {
        "case_types": ["civil"],
        "case_type": "civil",
        "case_stage": "first_trial",
        "legal_statuses": ["defendant"],
        "legal_status_match_mode": "any",
        "items_text": "代为应诉、答辩、举证、质证、参加庭审及法庭辩论；代为承认、反驳、变更诉讼请求，进行和解、调解，提起反诉；代为签收、领取法律文书及款项；办理本案一审相关的全部诉讼事宜。",
        "priority": 100,
        "is_active": True,
    },
    {
        "case_types": ["criminal"],
        "case_type": "criminal",
        "case_stage": "first_trial",
        "legal_statuses": ["criminal_defendant"],
        "legal_status_match_mode": "any",
        "items_text": "依法会见在押被告人，提供法律咨询，了解案件有关情况；代为申请取保候审、监视居住等变更强制措施；查阅、摘抄、复制本案案卷材料；向侦查机关、检察机关、审判机关提出无罪、罪轻、减轻、免除处罚的辩护意见；参与本案侦查、审查起诉、第一审、第二审（如有）诉讼活动，参加庭前会议、法庭调查与法庭辩论，发表辩护意见；代为签收、领取本案相关法律文书；办理与本案辩护相关的其他法律事务。\n委托期限： 自本委托书签署之日起至本案全阶段诉讼终结止。",
        "priority": 100,
        "is_active": True,
    },
    {
        "case_types": ["civil"],
        "case_type": "civil",
        "case_stage": "first_trial",
        "legal_statuses": ["plaintiff"],
        "legal_status_match_mode": "any",
        "items_text": "申请立案、调查或提供证据；代为出庭；接收司法文书；申请追加被告或第三人；自行和解、达成调解，申请撤诉；代为变更、放弃诉讼请求；申请财产、证据、行为保全；申请查询被告人口户籍信息；申请人民法院调查取证；申请退费；申请鉴定。",
        "priority": 100,
        "is_active": True,
    },
    {
        "case_types": ["civil"],
        "case_type": "civil",
        "case_stage": "labor_arbitration",
        "legal_statuses": ["respondent"],
        "legal_status_match_mode": "any",
        "items_text": "代为接收、签收劳动仲裁相关法律文书；代为答辩、提交证据、参加庭审、陈述事实与理由；代为进行质证、辩论、调解、和解；代为提出、承认、变更、放弃仲裁请求；代为签收调解书、裁决书等法律文书；代为处理与本案相关的其他仲裁程序事宜。",
        "priority": 100,
        "is_active": True,
    },
)


class ProxyMatterRuleInitService:
    """初始化代理事项规则默认数据。"""

    @transaction.atomic
    def initialize_defaults(self) -> dict[str, int]:
        created = 0
        updated = 0

        for seed in DEFAULT_PROXY_MATTER_RULES:
            lookup = {
                "case_type": seed["case_type"],
                "case_stage": seed["case_stage"],
                "legal_status_match_mode": seed["legal_status_match_mode"],
                "priority": seed["priority"],
            }
            defaults = {
                "case_types": list(seed["case_types"]),
                "legal_statuses": list(seed["legal_statuses"]),
                "items_text": seed["items_text"],
                "is_active": seed["is_active"],
            }

            rule, is_created = ProxyMatterRule.objects.update_or_create(defaults=defaults, **lookup)  # type: ignore[arg-type]
            if is_created:
                created += 1
                continue

            changed_fields: list[str] = []
            for field_name, field_value in defaults.items():
                if getattr(rule, field_name) != field_value:
                    setattr(rule, field_name, field_value)
                    changed_fields.append(field_name)
            if changed_fields:
                rule.save(update_fields=changed_fields + ["updated_at"])
                updated += 1

        return {"created": created, "updated": updated}
