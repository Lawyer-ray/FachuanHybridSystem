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

from ..models import (
    Beneficiary,
    Consequence,
    Playbook,
    PlaybookRule,
    PlaybookStatus,
    RuleClass,
    Severity,
    Stage,
    Stance,
)

logger = logging.getLogger(__name__)

BUILTIN_NAME = "内置通用审查标准"
BUILTIN_VERSION = 2
#
# 2026-11-26 v2：按法务总的「四类规则」重写土地类强制规则（拆抵押/查封、拆两类优先购买权、
# 把土壤修复从 inherited 改判为 mandatory 行政档、补 consequence 档位）。
# **改任何 standard_text / legal_basis 都必须 bump 本版本号**：ReviewRun.playbook_snapshot
# 存的是当时那一版口径，不 bump 就会出现「上月为什么这么判」对不上。

#: 内置默认检查项（通用合同）。
#:
#: 只放**有明确法律依据、且缺失会造成可量化损失**的条款类型——「建议措辞更严谨」
#: 这类不进库，它们是过度审查的主要来源。
_RAW_BUILTIN_RULES: list[dict[str, Any]] = [
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


#: 每条内置规则的「类别 + 阶段」。
#:
#: 这两列不是装饰：`rule_class=mandatory` 会让该条**免疫立场降权与条数闸**
#: （见 `review_pipeline`）。把「抵押未解除不得转让」判成一条可谈的商业建议，
#: 等于让清单漏掉「合同无效」级别的风险——这是法务总的「第五元规则扫描」教出来的。
_RULE_META: dict[str, tuple[str, str]] = {
    "subject.identity": (RuleClass.CONTRACTUAL, Stage.BEFORE),
    # 主体资格涉及行为能力/代理权限，违反可能影响效力 → 强制性
    "subject.capacity": (RuleClass.MANDATORY, Stage.BEFORE),
    "subject.amount_consistency": (RuleClass.CONTRACTUAL, Stage.DURING),
    "performance.deadline": (RuleClass.CONTRACTUAL, Stage.DURING),
    "breach.liquidated_damages_cap": (RuleClass.CONTRACTUAL, Stage.AFTER),
    "dispute.jurisdiction": (RuleClass.CONTRACTUAL, Stage.GENERAL),
    "termination.unilateral": (RuleClass.CONTRACTUAL, Stage.AFTER),
    "confidentiality.scope": (RuleClass.CONTRACTUAL, Stage.GENERAL),
    "ip.ownership": (RuleClass.CONTRACTUAL, Stage.GENERAL),
    "force_majeure.notice": (RuleClass.CONTRACTUAL, Stage.GENERAL),
}

BUILTIN_RULES: list[dict[str, Any]] = [
    {**rule, "rule_class": _RULE_META[rule["rule_key"]][0], "stage": _RULE_META[rule["rule_key"]][1]}
    for rule in _RAW_BUILTIN_RULES
]

#: 土地使用权/房地产转让专用的**强制性 + 承继性 + 程序性**规则。
#:
#: 来源：一位法务总的审查方法图（转让前/中/后 + 第五元规则扫描）+
#: 现行法条。**条号只写到「条」，不猜款项**——款项以现行法为准，由执业律师核对；
#: 拿不准的一律标「待核实」而不是编一个。
#:
#: 这些规则以前之所以缺失，是因为标准库按「条款类型」列（主体/价款/违约），
#: 而它们大多不是「条款写得好不好」，是「这块地现在能不能转」——按条款类型遍历
#: 永远遍历不到。
LAND_TRANSFER_RULES: list[dict[str, Any]] = [
    # ── 转让前：这块地现在能不能转 ──────────────────────────────────────
    {
        "rule_key": "land.seizure_or_title_dispute",
        "clause_type": "转让资格",
        "standard_text": (
            "标的土地及地上建筑物在签约与过户时不得处于被查封、被依法收回、权属有争议、"
            "未依法登记领取权属证书，或共有房地产未经其他共有人书面同意的状态。"
            "【后果】上述情形属**不得转让**：登记机构不予登记，转让办不成。"
        ),
        "acceptable_range": "已解除查封/已消除争议的，须附解除证明或生效法律文书。",
        "legal_basis": "《城市房地产管理法》第38条",
        "beneficiary": Beneficiary.NEUTRAL,
        "severity_if_missing": Severity.HIGH,
        "required": True,
        "rule_class": RuleClass.MANDATORY,
        "stage": Stage.BEFORE,
        "consequence": Consequence.ADMINISTRATIVE,
    },
    {
        "rule_key": "land.mortgage_transfer_restriction",
        "clause_type": "转让资格",
        "standard_text": (
            "标的处于抵押状态时，转让应**及时通知抵押权人**；抵押合同或登记簿另有约定"
            "「禁止/限制转让」的，须取得抵押权人同意或先解除抵押。带押转让还须明确"
            "抵押权顺位、价款提存与优先清偿安排。"
            "【后果】违反禁止转让约定的，转让可能不发生效力或**不得对抗抵押权人**，"
            "抵押权人可请求提前清偿或提存。"
            "【注意】《民法典》第406条已取代旧《物权法》第191条：抵押期间**可以**转让，"
            "义务核心是通知与「约定禁止」的处理，不是一律禁止。"
        ),
        "acceptable_range": "无「禁止转让」约定的，通知抵押权人并留存送达凭证即可。",
        "legal_basis": "《民法典》第406条；禁止/限制转让约定的效力细则见担保制度司法解释〔待核实〕",
        "beneficiary": Beneficiary.NEUTRAL,
        "severity_if_missing": Severity.HIGH,
        "required": True,
        "rule_class": RuleClass.MANDATORY,
        "stage": Stage.BEFORE,
        "consequence": Consequence.UNENFORCEABLE,
    },
    {
        "rule_key": "land.investment_ratio",
        "clause_type": "转让资格",
        "standard_text": (
            "以出让方式取得土地使用权的，转让时应已支付全部出让金并取得权证，"
            "且按出让合同约定完成开发投资总额的 25% 以上（成片开发须形成工业用地或"
            "其他建设用地条件）。"
            "【后果】本条通常按**管理性规定**理解：未达比例**一般不导致合同无效**，"
            "但过户可能被拒、并可被行政处罚。不要写成「合同无效」——那是过度定性。"
        ),
        "acceptable_range": "",
        "legal_basis": "《城市房地产管理法》第39条（效力定性以当地裁判口径为准〔待核实〕）",
        "beneficiary": Beneficiary.NEUTRAL,
        "severity_if_missing": Severity.HIGH,
        "required": True,
        "rule_class": RuleClass.MANDATORY,
        "stage": Stage.BEFORE,
        "consequence": Consequence.ADMINISTRATIVE,
    },
    {
        "rule_key": "land.allocated_approval",
        "clause_type": "转让资格",
        "standard_text": (
            "以划拨方式取得土地使用权的，转让房地产应报有批准权的人民政府审批；"
            "准予转让的，由受让方办理出让手续并缴纳出让金；未获批前不得交割。"
            "【后果】未经批准属**未生效**（非当然无效），可补正；登记机构不予办理。"
        ),
        "acceptable_range": "",
        "legal_basis": "《城市房地产管理法》第40条；《民法典》第502条第2款（未生效）",
        "beneficiary": Beneficiary.NEUTRAL,
        "severity_if_missing": Severity.HIGH,
        "required": True,
        "rule_class": RuleClass.MANDATORY,
        "stage": Stage.BEFORE,
        "consequence": Consequence.UNEFFECTIVE,
    },
    {
        "rule_key": "land.collective_land",
        "clause_type": "转让资格",
        "standard_text": (
            "集体土地不得擅自作为经营性建设用地入市或搞房地产开发：入市须规划确定为"
            "工业、商业等经营性用途、依法登记，并经本集体成员的村民会议三分之二以上"
            "成员或村民代表同意；城市规划区内集体土地须先征收转为国有方可有偿出让。"
            "【后果】**合同无效**，且无法办理任何登记。"
        ),
        "acceptable_range": "",
        "legal_basis": "《土地管理法》第63条；《城市房地产管理法》第9条",
        "beneficiary": Beneficiary.NEUTRAL,
        "severity_if_missing": Severity.HIGH,
        "required": True,
        "rule_class": RuleClass.MANDATORY,
        "stage": Stage.BEFORE,
        "consequence": Consequence.INVALID,
    },
    {
        # 两类优先购买权的后果**不同**，合并成一条必然一边高估一边低估：
        # 共有人可主张按同等条件购买（真能翻盘）；承租人只能索赔（合同不因此无效）。
        "rule_key": "land.preemption.coowner",
        "clause_type": "第三方权利",
        "standard_text": (
            "按份共有人享有同等条件下的优先购买权；转让前应先书面通知并给足行使期，"
            "或取得其放弃优先购买权的书面文件。"
            "【后果】未通知的，共有人可主张按同等条件购买，交易可能被推翻；"
            "共有房地产未经其他共有人书面同意不得转让。"
        ),
        "acceptable_range": "",
        "legal_basis": "《民法典》第305条；《城市房地产管理法》第38条",
        "beneficiary": Beneficiary.NEUTRAL,
        "severity_if_missing": Severity.HIGH,
        "required": False,
        "rule_class": RuleClass.MANDATORY,
        "stage": Stage.BEFORE,
        "consequence": Consequence.INVALID,
    },
    {
        "rule_key": "land.preemption.lessee",
        "clause_type": "第三方权利",
        "standard_text": (
            "出租人出卖租赁房屋的，应在出卖前的合理期限内通知承租人，承租人享有"
            "同等条件下的优先购买权；应取得放弃文件或送达凭证。"
            "【后果】妨害承租人优先购买权的，承租人只能请求赔偿损失，"
            "**买卖合同效力不受影响**——不要写成「合同无效」。"
        ),
        "acceptable_range": "",
        "legal_basis": "《民法典》第726条、第728条",
        "beneficiary": Beneficiary.NEUTRAL,
        "severity_if_missing": Severity.LOW,
        "required": False,
        "rule_class": RuleClass.CONTRACTUAL,
        "stage": Stage.BEFORE,
        "consequence": Consequence.BREACH,
    },
    # ── 转让中：怎么交付、怎么登记 ──────────────────────────────────────
    {
        "rule_key": "land.building_with_land",
        "clause_type": "转让标的",
        "standard_text": (
            "建设用地使用权转让的，附着于该土地上的建筑物、构筑物及其附属设施**一并处分**；"
            "反之亦然（房地一体）。"
            "【后果】单独处分土地或房屋的部分无效/不能登记。"
        ),
        "acceptable_range": "",
        "legal_basis": "《民法典》第356条、第357条",
        "beneficiary": Beneficiary.NEUTRAL,
        "severity_if_missing": Severity.HIGH,
        "required": True,
        "rule_class": RuleClass.MANDATORY,
        "stage": Stage.DURING,
        "consequence": Consequence.INVALID,
    },
    {
        "rule_key": "land.use_and_term",
        "clause_type": "土地用途",
        "standard_text": (
            "土地用途、容积率等规划条件与剩余使用年限应与权证、出让合同及规划许可一致；"
            "转让后年限为原出让年限减去已使用年限；变更用途须经出让方与规划主管部门同意"
            "并调整出让金。"
            "【后果】擅自改变用途可能被责令改正/罚款/收回土地，变更登记办不成。"
            "（调整出让金的具体条款〔待核实〕）"
        ),
        "acceptable_range": "",
        "legal_basis": "《民法典》第350条、第348条、第359条",
        "beneficiary": Beneficiary.NEUTRAL,
        "severity_if_missing": Severity.MEDIUM,
        "required": False,
        "rule_class": RuleClass.MANDATORY,
        "stage": Stage.DURING,
        "consequence": Consequence.ADMINISTRATIVE,
    },
    {
        "rule_key": "land.registration_effect",
        "clause_type": "登记",
        "standard_text": (
            "不动产物权转让经依法登记发生效力；合同应约定过户登记的申请主体（双方共同申请）、"
            "时限、材料清单、税费承担与完税前置、逾期责任，以及一方不配合时的替代救济。"
            "【后果】未登记则物权不变动，受让方只能主张违约；登记被退件则交割卡住。"
        ),
        "acceptable_range": "",
        "legal_basis": "《民法典》第209条、第215条（区分原则：未登记不影响合同效力）",
        "beneficiary": Beneficiary.NEUTRAL,
        "severity_if_missing": Severity.HIGH,
        "required": True,
        "rule_class": RuleClass.PROCEDURAL,
        "stage": Stage.DURING,
        "consequence": Consequence.ADMINISTRATIVE,
    },
    # ── 转让后：谁背什么 ────────────────────────────────────────────────
    {
        "rule_key": "land.grant_contract_succession",
        "clause_type": "权利义务承继",
        "standard_text": (
            "出让合同载明的权利义务随土地使用权一并转移；受让方承继原出让合同的义务"
            "（投资强度、产业准入、开竣工时限、自持比例、转让限制），并办理出让合同"
            "变更/备案手续；出让方同意或备案是交割前置。"
            "【后果】不办变更**不使义务消失**，只会让受让方无法抗辩「我不知道」，"
            "甚至被认定违约、被收回土地。本合同的条款改得再漂亮也挡不住上游义务。"
        ),
        "acceptable_range": "",
        "legal_basis": "《城市房地产管理法》第42条；《民法典》第555条",
        "beneficiary": Beneficiary.NEUTRAL,
        "severity_if_missing": Severity.HIGH,
        "required": True,
        "rule_class": RuleClass.INHERITED,
        "stage": Stage.AFTER,
        "consequence": Consequence.BREACH,
    },
    {
        "rule_key": "land.soil_remediation",
        "clause_type": "标的瑕疵",
        "standard_text": (
            "转让前应查明地块历史用途与污染状况（是否列入建设用地土壤污染风险管控和"
            "修复名录）；土壤污染责任人负风险管控与修复义务，责任人无法认定时由"
            "**土地使用权人**实施；本合同应明确修复责任归属、费用承担、信息披露与赔偿。"
            "【后果】受让方可能承接**法定**修复义务与被限制用途/禁止开工（非无效）。"
        ),
        "acceptable_range": "",
        "legal_basis": "《土壤污染防治法》第45条（用途变更前调查的条款〔待核实〕）",
        "beneficiary": Beneficiary.NEUTRAL,
        "severity_if_missing": Severity.HIGH,
        "required": False,
        "rule_class": RuleClass.MANDATORY,
        "stage": Stage.AFTER,
        "consequence": Consequence.ADMINISTRATIVE,
    },
    {
        # 与上一条互补：上一条是「法定行政义务」，这一条是「合同义务随标的一并转移」。
        # 两者的律师动作不同：前者查名录定责任，后者核清上游合同。
        "rule_key": "risk.soil_liability_succession",
        "clause_type": "权利义务承继",
        "standard_text": (
            "原土地使用权人/排污者遗留的污染责任、修复费用与政府协议项下义务随标的一并转移；"
            "应要求转让方就未披露的污染与上游协议义务作出陈述保证并承担赔偿。"
            "【后果】受让方替前人背修复费与整改义务。"
        ),
        "acceptable_range": "",
        "legal_basis": "《民法典》第555条；《土壤污染防治法》第45条（责任人认定规则）",
        "beneficiary": Beneficiary.NEUTRAL,
        "severity_if_missing": Severity.MEDIUM,
        "required": False,
        "rule_class": RuleClass.INHERITED,
        "stage": Stage.AFTER,
        "consequence": Consequence.BREACH,
    },
]


def _is_land_transfer(contract_type: str) -> bool:
    probe = contract_type or ""
    return any(key in probe for key in ("土地", "房地产", "建设用地", "不动产"))


def rules_for(contract_type: str = "") -> list[dict[str, Any]]:
    """按合同类型选内置规则集（土地/房地产类额外追加强制性与承继性规则）。"""
    return [*BUILTIN_RULES, *LAND_TRANSFER_RULES] if _is_land_transfer(contract_type) else list(BUILTIN_RULES)


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
            for ordinal, rule in enumerate(rules_for(contract_type)):
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
