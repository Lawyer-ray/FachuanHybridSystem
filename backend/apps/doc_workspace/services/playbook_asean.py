"""东盟十国的合同审查标准库（按法域分册）。

## 为什么每个国家一套，而不是「一套通用 + 若干例外」

同一份「不动产租赁 + 外商经营」的合同，在十个国家的**强制规则完全不同**：

| 问题 | 越南 | 泰国 | 新加坡 | 菲律宾 |
|:--|:--|:--|:--|:--|
| 外国人能持有土地吗 | 不能，只能取得土地使用权 | 原则不能（Land Code 86） | 有地住宅须批准 | 原则不能 |
| 不动产租赁上限 | 按项目期限（通常 50 年） | **30 年**（CCC 540） | 按租约（土地租约通常 ≤ 30 年） | 外资租地 50+25 年 |
| 增值税/消费税 | VAT 10% | VAT 7% | GST 9% | VAT 12% |
| 遣散费 | 每满年 1/2 月工资 | 按年限法定递增 | 无普遍法定标准 | 1 月/年 或 1/2 月/年 |

把这些挤进一套「通用标准」，产出必然是噪音：律师会拿到一堆不适用于本国的结论，
然后逐条删除——这正是过度审查最贵的形态。所以**每个法域一套**，且在
`ReviewRun.playbook_snapshot` 里留快照。

## 引用分三档（决定了「律师能不能信」）

| 档 | `legal_basis` 形态 | 依据 |
|:--|:--|:--|
| **条号已核** | `XX Act Section 21` | BARLC 取到了该条原文（真机逐条跑过，见 `docs/harness/backend/integrations.md`） |
| **仅法名已核** | `XX Act（条号待核）` | 该法在 BARLC 确实存在，但正文切不出条款（判例法国家的英文 PDF 大量缺失） |
| **框架级** | 法名 + 主管机关 | 该国无统一成文法（如文莱无 VAT），或限制来自政策而非单一法条 |

**「条号待核」不是偷懒，是诚实。** 编一个看起来很像的条号（`Section 42`）比不写条号
危险得多：律师拿去核对要花时间，核不上就再也不信这个功能。

2026-11-27 用 `manage.py verify_playbook_citations` 对 BARLC 逐条跑过一轮（真账号）：

| 法域 | 条号核到原文 | 只核到法名 | 备注 |
|:--|:--|:--|:--|
| 泰国 TH | 7 | 1 | `Arbitration Act` 泰国库只收录《法院间仲裁法》 |
| 越南 VN | 3 | 3 | 投资/土地/增值税只核到法名 |
| 印尼 ID | 5 | 0 | 全核到原文 |
| 柬埔寨 KH | 3 | 2 | |
| 老挝 LA | 1 | 4 | |
| 缅甸 MM | 0 | 5 | |
| 马来西亚 MY / 新加坡 SG / 菲律宾 PH / 文莱 BN | 0 | 全部 | **判例法国家成文法的英文全文在 BARLC 不可切分** |

合计 55 条域外规则（TH 8 / VN 6 / MY 5 / SG 5 / ID 5 / PH 6 / KH 5 / LA 5 / MM 5 / BN 5），
19 条带已核条号，其余 36 条显式标「条号待核」。
`--sleep 2` 跑完全量约 4 分钟；结论不一致时命令以退出码 1 结束。

自检命令（需要 BARLC 凭据）：

```bash
cd backend/apiSystem
../../backend/.venv/bin/python manage.py verify_playbook_citations --jurisdiction VN
```
"""

from __future__ import annotations

from typing import Any

from ..models import Beneficiary, Consequence, RuleClass, Severity, Stage

#: 「法名已核、条号待核」的统一后缀。UI 与提示词都会原样展示，所以保持短。
PENDING = "（条号待核）"


def _rule(
    *,
    key: str,
    clause: str,
    standard: str,
    law: str,
    section: str = "",
    cite: str = "Section",
    law_no: str = "",
    note: str = "",
    search_law: str = "",
    acceptable: str = "",
    severity: str = Severity.MEDIUM,
    rule_class: str = RuleClass.CONTRACTUAL,
    stage: str = Stage.GENERAL,
    consequence: str = Consequence.BREACH,
    beneficiary: str = Beneficiary.NEUTRAL,
    required: bool = True,
) -> dict[str, Any]:
    """一条标准。

    ## 为什么把「法名 / 条号 / 法号」拆成三个字段

    `legal_basis` 是**给律师看的展示串**（可以带法号、可以带「条号待核」的说明），
    而核验命令需要的是**能直接丢进 BARLC 的法名**。真机踩过：把
    `Law on Investment (No. 61/2020/QH14)` 整串拿去检索 → 零命中 → 误报
    「标准库引用了不存在的法」19 条。BARLC 的标题里**不带法号**，也不认中文括注。

    所以展示串与检索串必须分开：`law`/`section` 是机器字段（`verify_law` /
    `verify_section`），`law_no`/`note` 只进展示串。落库时机器字段会被
    `ensure_builtin` 按模型字段表过滤掉，不会污染 `PlaybookRule`。

    默认值刻意选「契约性/违约/中危」——真正的强制项必须显式声明。
    """
    parts = [law]
    if law_no:
        parts.append(f"（{law_no}）")
    if section:
        parts.append(f" {cite} {section}")
    else:
        parts.append(PENDING)
    if note:
        parts.append(f"；{note}")
    rule = {
        "rule_key": key,
        "clause_type": clause,
        "standard_text": standard,
        "acceptable_range": acceptable,
        "legal_basis": "".join(parts),
        "beneficiary": beneficiary,
        "severity_if_missing": severity,
        "required": required,
        "rule_class": rule_class,
        "stage": stage,
        "consequence": consequence,
        # 机器可读的核验目标（不进 PlaybookRule，见 docstring）。
        # `search_law` 只在「BARLC 的标题与通行译名不一致」时才用（如库内把
        # Manpower 拼成 Manpower Affirs、把 American 拼法写成 Labor）——
        # 展示串要对律师正确，检索串要对上游正确，两者可以不同。
        "verify_law": search_law or law,
    }
    if section:
        rule["verify_section"] = section
    return rule


# ── 引用完整性（所有法域共用）──────────────────────────────────────────


CITATION_RULES: list[dict[str, Any]] = [
    _rule(
        key="foreign_law.citation_invalid",
        clause="法律引用",
        standard=(
            "合同引用的域外法条文必须真实存在且现行有效。经域外法查明，"
            "**检索不到该法或该条**的引用必须替换为正确的法名与条号，或删除该引用。"
            "【后果】以不存在的法律为依据的条款，在争议中不产生任何说服力，"
            "甚至可作为对方主张「起草方未尽审慎义务」的依据。"
        ),
        acceptable="只需写明真实存在的法名 + 条号。",
        law="（域外法查明结果：该引用不存在，无需外部核验）",
        note="BARLC 查明",
        severity=Severity.HIGH,
        rule_class=RuleClass.MANDATORY,
        consequence=Consequence.UNEFFECTIVE,
    ),
    _rule(
        key="foreign_law.citation_unconfirmed",
        clause="法律引用",
        standard=(
            "域外法引用无法经查明确认（法名只是近似、正文切分不完整、或查明服务不可用）；"
            "签约前须由执业律师核对原文，不得直接依赖。"
            "【后果】未经核实的引用可能是错法号、旧版本或已修订条文。"
        ),
        law="（域外法查明结果：待人工核对，无需外部核验）",
        note="BARLC 查明",
        severity=Severity.MEDIUM,
        rule_class=RuleClass.PROCEDURAL,
        required=False,
    ),
    _rule(
        key="foreign_law.citation_verified",
        clause="法律引用",
        standard=(
            "域外法引用已查明到条文原文；应核对合同对该条的**表述与适用**是否与原文一致"
            "（常见错误：把上限写成下限、把例外写成原则、引用已被修订的版本）。"
            "【后果】引对了法但说反了内容，与引错法在争议中效果相同。"
        ),
        law="（域外法查明结果：条文原文已取得，无需外部核验）",
        note="BARLC 查明",
        severity=Severity.MEDIUM,
        rule_class=RuleClass.PROCEDURAL,
        required=False,
    ),
]


# ── 泰国（TH）──────────────────────────────────────────────────────────
#: 条号口径：8 条条号中 7 条已核到原文（CCC 538/540、Land Code 86、
#: Condominium Act 19 bis、Foreign Business Act 8、Revenue Code 77/1、
#: Labor Protection Act 118）；`Arbitration Act` 只核到法名，故标「条号待核」。

THAI_RULES: list[dict[str, Any]] = [
    _rule(
        key="th.foreign_business_license",
        clause="经营资格",
        standard=(
            "外国自然人/外国法人在泰国经营《外国人经营业务法》附表二/附表三所列业务"
            "（含各类服务、租赁、建筑、餐饮、部分批发零售），须先取得外国人经营许可证"
            "或投资促进（BOI）优惠；合同应约定许可取得为生效/交割前提及未取得的后果。"
            "【后果】无证经营可被责令停业、罚款乃至刑事责任；以泰籍人代持规避许可的，"
            "该规避安排不受法律保护。"
        ),
        acceptable="业务确不落入附表（如经部级法规豁免），须在合同中写明豁免依据。",
        law="Foreign Business Act",
        law_no="B.E. 2542 (1999)",
        section="8",
        severity=Severity.HIGH,
        rule_class=RuleClass.MANDATORY,
        stage=Stage.BEFORE,
        consequence=Consequence.ADMINISTRATIVE,
    ),
    _rule(
        key="th.land_ownership_foreigner",
        clause="不动产权属",
        standard=(
            "外国人原则上不得在泰国拥有土地；仅在依条约享有权利并经内政部批准等"
            "极窄例外下可以取得。以外国名义直接持有土地、或通过泰籍人代持的，"
            "合同应改采长期租赁、公寓（外资份额内）或 BOI 优惠路径。"
            "【后果】违反者可能被责令处分土地，且代持安排可能被认定规避法律。"
        ),
        acceptable="租赁、公寓单元（49% 外资份额内）、BOI 批准持有。",
        law="Land Code",
        section="86",
        severity=Severity.HIGH,
        rule_class=RuleClass.MANDATORY,
        stage=Stage.BEFORE,
        consequence=Consequence.INVALID,
    ),
    _rule(
        key="th.condo_foreign_quota",
        clause="不动产权属",
        standard=(
            "公寓单元的外籍业主合计持有面积不得超过该公寓总单元面积的 49%；"
            "应核查公寓的外籍持有比例余额，并约定因份额已满无法过户时的替代安排与退款责任。"
            "【后果】超额部分无法登记，买方只能主张违约。"
        ),
        law="Condominium Act",
        law_no="B.E. 2522 (1979)",
        section="19 bis",
        severity=Severity.HIGH,
        rule_class=RuleClass.MANDATORY,
        stage=Stage.BEFORE,
        consequence=Consequence.UNEFFECTIVE,
    ),
    _rule(
        key="th.lease_term_limit",
        clause="租赁期限",
        standard=(
            "不动产租赁期限不得超过 30 年；约定更长期限的，超过部分自动缩短为 30 年。"
            "需要更长使用期的，应改为「30 年 + 依约续期」或取得法定例外，"
            "并在合同中写明续期条件与登记安排。"
            "【后果】合同里写到 50 年/99 年，实际只在 30 年内有效。"
        ),
        acceptable="30 年以内；超出部分无效但不影响其余条款。",
        law="Civil and Commercial Code",
        section="540",
        severity=Severity.HIGH,
        rule_class=RuleClass.MANDATORY,
        stage=Stage.BEFORE,
        consequence=Consequence.UNEFFECTIVE,
    ),
    _rule(
        key="th.lease_registration",
        clause="租赁形式要件",
        standard=(
            "不动产租赁超过 3 年的，必须作成书面文件并在主管机关登记；未登记的，"
            "超过 3 年的部分不能以诉讼强制执行。合同应约定登记义务人、时限、税费与责任。"
            "【后果】不登记 = 第 4 年起无法诉请履行。"
        ),
        acceptable="3 年以内可口头，但仍建议书面。",
        law="Civil and Commercial Code",
        section="538",
        severity=Severity.HIGH,
        rule_class=RuleClass.PROCEDURAL,
        stage=Stage.DURING,
        consequence=Consequence.UNEFFECTIVE,
    ),
    _rule(
        key="th.vat_rate",
        clause="价款与税",
        standard=(
            "增值税率为 7%（明确含税/不含税口径），另需注意服务费预提税与印花税；"
            "跨境支付还应约定代扣代缴义务人。"
            "【后果】税率写错会让报价与实际税负相差数个百分点，且不合规税额不能抵扣。"
        ),
        acceptable="7%（依法定调整）。",
        law="Revenue Code",
        section="77/1",
        stage=Stage.DURING,
        rule_class=RuleClass.MANDATORY,
        consequence=Consequence.ADMINISTRATIVE,
    ),
    _rule(
        key="th.dispute_resolution",
        clause="争议解决",
        standard=(
            "仲裁协议必须以书面形式作出，并明确仲裁机构名称（如 THAC / SIAC）、"
            "仲裁地、仲裁员人数与语言；选择诉讼的，应明确泰国法院管辖。"
            "【后果】机构名称不确定或「或裁或审」的条款可能被认定仲裁协议不成立。"
        ),
        law="Arbitration Act",
        law_no="B.E. 2545 (2002)",
        note="BARLC 泰国库仅收录《法院间仲裁法》，本条条号需律师核对原文",
        severity=Severity.HIGH,
    ),
    _rule(
        key="th.labour_severance",
        clause="劳动用工",
        standard=(
            "解除劳动合同时的遣散费按服务年限法定计算（随年限递增至 400 天工资），"
            "不得以约定低于法定标准；外籍员工还须持有工作许可证。"
            "【后果】低于法定标准的约定无效，雇主仍须按法定标准支付，并可能被罚。"
        ),
        acceptable="不得低于法定标准。",
        law="Labor Protection Act",
        law_no="B.E. 2541 (1998)",
        section="118",
        severity=Severity.HIGH,
        rule_class=RuleClass.MANDATORY,
        stage=Stage.AFTER,
        consequence=Consequence.ADMINISTRATIVE,
    ),
]


# ── 越南（VN）──────────────────────────────────────────────────────────
#: 条号已核：Civil Code 427 / Commercial Arbitration Law 16 / Labor Code 46。
#: 投资与土地只核到法名（取回的「第 21 条」是修订条，不是准入规则；不硬凑）。

VIETNAM_RULES: list[dict[str, Any]] = [
    _rule(
        key="vn.foreign_investment_admission",
        clause="经营资格",
        standard=(
            "越南对「有条件投资经营行业」实行准入条件管理：外国投资者须取得投资登记证"
            "（IRC）/企业登记证，特定行业还需满足外资持股上限或取得主管部门批准。"
            "合同应把「取得 IRC/ERC 及行业许可」写成生效或交割前提，并约定未取得的后果。"
            "【后果】未取得即经营可被责令停业、罚款，且相关合同可能无法履行。"
        ),
        law="Law on Investment",
        law_no="No. 61/2020/QH14",
        severity=Severity.HIGH,
        rule_class=RuleClass.MANDATORY,
        stage=Stage.BEFORE,
        consequence=Consequence.ADMINISTRATIVE,
    ),
    _rule(
        key="vn.land_use_rights_foreign",
        clause="不动产权属",
        standard=(
            "外国投资者在越南**不得取得土地所有权**，只能依法取得土地使用权"
            "（受让/租赁，期限按投资项目确定，一般不超过 50 年，特殊项目不超过 70 年）。"
            "合同应写明土地使用权的取得方式、期限、到期处理与地上建筑物归属。"
            "【后果】约定土地所有权移转的条款在法律上无法履行。"
        ),
        law="Law on Land",
        law_no="No. 31/2024/QH15",
        severity=Severity.HIGH,
        rule_class=RuleClass.MANDATORY,
        stage=Stage.BEFORE,
        consequence=Consequence.INVALID,
    ),
    _rule(
        key="vn.contract_termination_effect",
        clause="解除与后果",
        standard=(
            "合同解除后，双方应返还已受领的财物并赔偿损失；约定违约金时，"
            "越南法下违约金总额可受实际损失约束。合同应写明解除条件、通知程序与结算方式。"
            "【后果】解除条款写不清，实际争议会退回到法定返还与损失赔偿的举证。"
        ),
        law="Civil Code",
        law_no="No. 91/2015/QH13",
        cite="Article",
        section="427",
        stage=Stage.AFTER,
    ),
    _rule(
        key="vn.arbitration_agreement_form",
        clause="争议解决",
        standard=(
            "仲裁协议必须为书面形式（含合同中的仲裁条款、独立协议、电子通信等形式），"
            "并明确仲裁机构（如 VIAC）与仲裁地。"
            "【后果】口头仲裁合意不成立；条款不明时法院可能不受理仲裁申请。"
        ),
        law="Commercial Arbitration Law",
        law_no="No. 54/2010/QH12",
        cite="Article",
        section="16",
        severity=Severity.HIGH,
    ),
    _rule(
        key="vn.labour_severance",
        clause="劳动用工",
        standard=(
            "劳动合同终止时，雇主应为连续工作满 12 个月的劳动者支付遣散费"
            "（每工作满一年支付半个月工资）；外籍劳动者还须持工作许可证。"
            "【后果】约定低于法定标准的遣散费无效，仍按法定标准支付。"
        ),
        law="Labor Code",
        law_no="No. 45/2019/QH14",
        cite="Article",
        section="46",
        severity=Severity.HIGH,
        rule_class=RuleClass.MANDATORY,
        stage=Stage.AFTER,
        consequence=Consequence.ADMINISTRATIVE,
    ),
    _rule(
        key="vn.vat_rate",
        clause="价款与税",
        standard=(
            "增值税一般税率 10%（部分货物/服务适用 5% 或阶段性 8% 优惠），"
            "合同须明确含税/不含税与发票类型；跨境服务还涉及外国承包商税（FCT）。"
            "【后果】税率与含税口径写错，报价与实际税负差额由谁承担会变成争议。"
        ),
        law="Law on Value Added Tax",
        stage=Stage.DURING,
        rule_class=RuleClass.MANDATORY,
        consequence=Consequence.ADMINISTRATIVE,
    ),
]


# ── 马来西亚（MY）──────────────────────────────────────────────────────
#: 判例法国家：BARLC 有成文法标题但**英文全文不可切分** → 全部「条号待核」。

MALAYSIA_RULES: list[dict[str, Any]] = [
    _rule(
        key="my.land_foreign_ownership",
        clause="不动产权属",
        standard=(
            "外国公司/外国人在马来西亚取得土地受《国家土地法典》与**州级政策**双重限制："
            "多数情形须取得州当局同意，且不得取得马来保留地；已建成物业的外资持有门槛"
            "（最低价、类型）由各州规定。合同应把「取得州当局同意」写成交割前提。"
            "【后果】未获同意无法登记，买方只能主张违约。"
        ),
        law="National Land Code (Revised 2020)",
        severity=Severity.HIGH,
        rule_class=RuleClass.MANDATORY,
        stage=Stage.BEFORE,
        consequence=Consequence.UNEFFECTIVE,
    ),
    _rule(
        key="my.employment_termination",
        clause="劳动用工",
        standard=(
            "《1955 就业法》要求终止雇佣须有正当理由或依约通知；无正当理由解雇的，"
            "劳动者可向劳工局申诉，可能被判复职或赔偿。"
            "【后果】合同若约定「可无理由即时解雇」，该约定在法定程序面前不成立。"
        ),
        law="Employment Act 1955",
        rule_class=RuleClass.MANDATORY,
        stage=Stage.AFTER,
        consequence=Consequence.ADMINISTRATIVE,
    ),
    _rule(
        key="my.arbitration_agreement",
        clause="争议解决",
        standard=(
            "《2005 仲裁法》要求仲裁协议为书面形式；一方违反仲裁协议起诉时，"
            "另一方可在出庭前申请法院中止诉讼并提交仲裁。仲裁地、机构（AIAC）与语言须写清。"
            "【后果】未在期限内申请中止，争议可能被法院实体审理，仲裁条款形同虚设。"
        ),
        law="Arbitration Act 2005",
        severity=Severity.HIGH,
    ),
    _rule(
        key="my.sst",
        clause="价款与税",
        standard=(
            "马来西亚以销售税（Sales Tax 5%/10%）与服务税（Service Tax 6%，部分 8%）"
            "替代增值税；合同须明确价格是否含税、由谁申报缴纳、以及 SST 登记号。"
            "【后果】含税口径与税率写错，差额通常由付款方吸收。"
        ),
        law="Sales Tax Act 2018",
        note="服务税见 Service Tax Act 2018",
        stage=Stage.DURING,
        rule_class=RuleClass.MANDATORY,
        consequence=Consequence.ADMINISTRATIVE,
    ),
    _rule(
        key="my.foreign_investment",
        clause="经营资格",
        standard=(
            "马来西亚**没有一般性外资准入审批**，多数行业允许外资 100% 持股；"
            "但批发零售（WRT）、金融、油气、通信等须取得行业主管机关许可。"
            "合同应写明「由哪一方负责取得何项许可」及未取得的解约/退款安排。"
            "【后果】把「无需审批」写成陈述保证，一旦落入受监管行业即为虚假陈述。"
        ),
        law="Companies Act 2016",
        note="行业许可按主管部门规定",
        stage=Stage.BEFORE,
        required=False,
    ),
]


# ── 新加坡（SG）────────────────────────────────────────────────────────

SINGAPORE_RULES: list[dict[str, Any]] = [
    _rule(
        key="sg.residential_property_foreign",
        clause="不动产权属",
        standard=(
            "外国人取得新加坡**有地住宅（landed residential property）**须依《住宅财产法》"
            "取得政府批准；公寓单元不受该限制，但仍须缴纳额外买方印花税（ABSD）。"
            "合同应把「取得批准」写成交割前提，并明确 ABSD 由谁承担。"
            "【后果】未获批准无法过户，买方须承担违约与税费损失。"
        ),
        law="Residential Property Act 1976",
        severity=Severity.HIGH,
        rule_class=RuleClass.MANDATORY,
        stage=Stage.BEFORE,
        consequence=Consequence.UNEFFECTIVE,
    ),
    _rule(
        key="sg.arbitration_agreement",
        clause="争议解决",
        standard=(
            "新加坡把仲裁分成两套：国内仲裁适用 Arbitration Act 2001，国际仲裁适用 "
            "International Arbitration Act 1994。仲裁协议须书面；国际仲裁下法院除法定"
            "情形外不得干预。"
            "应明确选择哪一部法、仲裁地（SIAC 默认新加坡）与仲裁员人数。"
            "【后果】未选清适用哪部法，救济路径（上诉/撤销）会完全不同。"
        ),
        law="Arbitration Act 2001",
        note="国际仲裁见 International Arbitration Act 1994",
        severity=Severity.HIGH,
    ),
    _rule(
        key="sg.gst",
        clause="价款与税",
        standard=(
            "货物与服务税（GST）自 2024-01-01 起为 9%；合同须明确价格含税与否、"
            "跨境服务是否适用零税率、以及由谁做 GST 登记与申报。"
            "【后果】价格未写含税，9% 的差额通常由收款方吸收。"
        ),
        law="Goods and Services Tax Act 1993",
        stage=Stage.DURING,
        rule_class=RuleClass.MANDATORY,
        consequence=Consequence.ADMINISTRATIVE,
    ),
    _rule(
        key="sg.employment_termination",
        clause="劳动用工",
        standard=(
            "《1968 就业法》规定通知期与不当解雇救济；新加坡**没有普遍法定遣散费**，"
            "裁员补偿通常按合同、集体协议或三方指引（TRF）处理。"
            "【后果】合同若不写裁员补偿，法律不会替你补一个标准。"
        ),
        law="Employment Act 1968",
        stage=Stage.AFTER,
        required=False,
    ),
    _rule(
        key="sg.foreign_investment",
        clause="经营资格",
        standard=(
            "新加坡无一般外资准入审批，外资可 100% 持股；但受行业许可约束"
            "（银行/资本市场由 MAS、法律服务、地产代理、私立教育等）。"
            "合同应写明许可取得责任与「未取得即解约退款」的安排。"
        ),
        law="Companies Act 1967",
        note="行业许可按主管部门规定",
        stage=Stage.BEFORE,
        required=False,
    ),
]


# ── 印度尼西亚（ID）────────────────────────────────────────────────────
#: 5 条条号全部核到原文（Agrarian 21 / Investment 5 / Arbitration 5 /
#: Manpower 156 / VAT 7）。法名按 BARLC 原样（含其拼写 `Manpower Affirs`）。

INDONESIA_RULES: list[dict[str, Any]] = [
    _rule(
        key="id.land_ownership_foreign",
        clause="不动产权属",
        standard=(
            "《土地基本规定法》下**只有印尼公民可以拥有土地所有权（Hak Milik）**；"
            "外国主体只能取得使用权（Hak Pakai）、建筑权（HGB）或租赁权（Hak Sewa），"
            "且有期限与面积限制。合同应写明权利类型、期限与到期处理。"
            "【后果】约定把所有权过户给外国公司的条款自始无法登记。"
        ),
        law="Law Concerning Basic Regulations on Agrarian",
        law_no="No. 5/1960",
        cite="Article",
        section="21",
        severity=Severity.HIGH,
        rule_class=RuleClass.MANDATORY,
        stage=Stage.BEFORE,
        consequence=Consequence.INVALID,
    ),
    _rule(
        key="id.foreign_investment",
        clause="经营资格",
        standard=(
            "外资在印尼须以 PT PMA 形式经营，并受「投资领域清单」与最低投资额约束；"
            "合同应把 BKPM 批准与营业执照（OSS 系统）写成交割前提。"
            "【后果】不在清单内的行业不得经营；以本地人代持的安排不受保护。"
        ),
        law="capital investment Act",
        law_no="No. 25/2007",
        cite="Article",
        section="5",
        severity=Severity.HIGH,
        rule_class=RuleClass.MANDATORY,
        stage=Stage.BEFORE,
        consequence=Consequence.ADMINISTRATIVE,
    ),
    _rule(
        key="id.arbitration_scope",
        clause="争议解决",
        standard=(
            "印尼《仲裁与替代争议解决法》只允许**商事性质的争议**提交仲裁，"
            "且仲裁协议须书面；选择境外仲裁时，执行仍需经印尼法院承认程序。"
            "合同应明确仲裁地、机构（BANI/SIAC）与执行安排。"
            "【后果】超出商事范围或未按法定形式订立的仲裁条款不成立。"
        ),
        law="Arbitration and Alternative Dispute Resolution Law",
        law_no="No. 30/1999",
        cite="Article",
        section="5",
        severity=Severity.HIGH,
    ),
    _rule(
        key="id.labour_severance",
        clause="劳动用工",
        standard=(
            "解除劳动关系时雇主须支付遣散费（按工龄月数工资）与服务金，"
            "并遵守法定协商/报备程序；约定低于法定标准的补偿无效。"
            "【后果】直接解雇可能被认定无效，需恢复劳动关系并补发工资。"
        ),
        law="Law on Manpower Affairs",
        law_no="No. 13/2003",
        search_law="Law on Manpower Affirs",
        cite="Article",
        section="156",
        severity=Severity.HIGH,
        rule_class=RuleClass.MANDATORY,
        stage=Stage.AFTER,
        consequence=Consequence.ADMINISTRATIVE,
    ),
    _rule(
        key="id.vat_rate",
        clause="价款与税",
        standard=(
            "印尼增值税自 2022 年起为 11%（由政府条例调整），另有服务预提税与"
            "土地/建筑转让税；合同须明确含税口径与由谁开具发票（Faktur Pajak）。"
            "【后果】税率与含税口径写错，差额通常由收款方吸收。"
        ),
        law="Law on Goods and Services Value Added Tax and Sales Tax on Luxury Goods",
        cite="Article",
        section="7",
        stage=Stage.DURING,
        rule_class=RuleClass.MANDATORY,
        consequence=Consequence.ADMINISTRATIVE,
    ),
]


# ── 菲律宾（PH）────────────────────────────────────────────────────────
#: BARLC 对菲律宾成文法**没有可切分的英文正文**（真机逐条验证）→ 一律「条号待核」。

PHILIPPINES_RULES: list[dict[str, Any]] = [
    _rule(
        key="ph.foreign_equity_limit",
        clause="经营资格",
        standard=(
            "菲律宾以《外商投资法》+「外商投资负面清单」限制外资股比，"
            "多数受限制行业上限为 40%（1987 宪法第十二条对自然资源与公用事业的要求）；"
            "合同应核查目标业务是否在负面清单内、外资股比是否超限，并约定替代持股方案。"
            "【后果】超限持股可被认定违反反挂名法（Anti-Dummy Law），面临刑事风险。"
        ),
        law="Foreign Investments Act of 1991",
        law_no="RA 7042",
        severity=Severity.HIGH,
        rule_class=RuleClass.MANDATORY,
        stage=Stage.BEFORE,
        consequence=Consequence.INVALID,
    ),
    _rule(
        key="ph.condominium_foreign_quota",
        clause="不动产权属",
        standard=(
            "《公寓法》要求：公寓项目中外国主体持有的单元面积合计不得超过 40%，"
            "且外国买家不得取得土地。合同应核查项目剩余外资配额并约定退路。"
            "【后果】超出配额的单元无法登记，买方只能主张违约。"
        ),
        law="The Condominium Act",
        law_no="RA 4726",
        severity=Severity.HIGH,
        rule_class=RuleClass.MANDATORY,
        stage=Stage.BEFORE,
        consequence=Consequence.UNEFFECTIVE,
    ),
    _rule(
        key="ph.investors_lease",
        clause="租赁期限",
        standard=(
            "《外国投资者租赁法》允许外国投资者租赁私人土地最长 50 年、"
            "可续期 25 年；且租赁面积与用途受限制。合同应写明期限、续期条件与登记。"
            "【后果】超过法定上限的租期部分不能登记。"
        ),
        law="Investors' Lease Act",
        law_no="RA 7652",
        severity=Severity.HIGH,
        rule_class=RuleClass.MANDATORY,
        stage=Stage.BEFORE,
        consequence=Consequence.UNEFFECTIVE,
    ),
    _rule(
        key="ph.labour_separation_pay",
        clause="劳动用工",
        standard=(
            "《劳动法典》规定因裁员/冗员解除劳动关系时须支付遣散费"
            "（冗员为每服务一年一个月工资，裁员为每一年半个月工资，至少一个月）。"
            "【后果】约定低于法定标准的遣散方案无效。"
        ),
        law="Labor Code of the Philippines",
        severity=Severity.HIGH,
        rule_class=RuleClass.MANDATORY,
        stage=Stage.AFTER,
        consequence=Consequence.ADMINISTRATIVE,
    ),
    _rule(
        key="ph.vat_rate",
        clause="价款与税",
        standard=(
            "菲律宾增值税率为 12%（《1997 国家税收法典》），部分交易为零税率或免税；"
            "合同须明确含税口径、预提税（EWT）与发票要求。"
        ),
        law="National Internal Revenue Code of 1997",
        stage=Stage.DURING,
        rule_class=RuleClass.MANDATORY,
        consequence=Consequence.ADMINISTRATIVE,
    ),
    _rule(
        key="ph.arbitration_agreement",
        clause="争议解决",
        standard=(
            "菲律宾以《仲裁法》(RA 876) 与《替代争议解决法》(RA 9285) 规范仲裁，"
            "仲裁协议须书面；涉外仲裁多选择 SIAC/HKIAC 或 PDRCI。"
            "【后果】条款不明时，法院可能不受理中止诉讼申请。"
        ),
        law="Arbitration Law",
        law_no="RA 876",
        severity=Severity.HIGH,
    ),
]


# ── 柬埔寨（KH）────────────────────────────────────────────────────────
#: 条号已核：Land Law 8 / Investment Act 3 / Civil Code 483 / Labor Law 73。

CAMBODIA_RULES: list[dict[str, Any]] = [
    _rule(
        key="kh.land_foreign_ownership",
        clause="不动产权属",
        standard=(
            "《土地法》规定**只有高棉国籍的自然人或法人可以拥有土地所有权**；"
            "外国人/外资公司只能租赁（最长 50 年并可续一次，或依特许/长期租赁）"
            "或购买**二层以上**公寓单元（不得持有底层与土地份额）。"
            "合同应写明权利类型、期限与登记方式。"
            "【后果】约定把土地所有权过户给外资公司的条款无法登记。"
        ),
        law="Land Law",
        law_no="2001",
        cite="Article",
        section="8",
        severity=Severity.HIGH,
        rule_class=RuleClass.MANDATORY,
        stage=Stage.BEFORE,
        consequence=Consequence.INVALID,
    ),
    _rule(
        key="kh.investment_registration",
        clause="经营资格",
        standard=(
            "柬埔寨投资须向 CDC（发展理事会）申请「合格投资项目（QIP）」登记，"
            "并取得附条件注册证书；优惠（关税/所得税豁免）与登记绑定，"
            "合同应明确由哪一方办理登记、登记失败时的处理。"
            "【后果】未登记即无优惠，且部分业务须经批准方可经营。"
        ),
        law="Investment Act Of The Kingdom Of Cambodia (014/2021)",
        section="3",
        severity=Severity.HIGH,
        rule_class=RuleClass.MANDATORY,
        stage=Stage.BEFORE,
        consequence=Consequence.ADMINISTRATIVE,
    ),
    _rule(
        key="kh.labour_fixed_duration",
        clause="劳动用工",
        standard=(
            "《劳动法》对固定期限劳动契约的终止有专门规定（须在合同期满终止或"
            "依法补偿）；不得以续签固定期限契约替代无固定期限契约义务。"
            "【后果】约定「随时终止且不补偿」的固定期限条款无效。"
        ),
        law="Labor Law",
        law_no="1997",
        cite="Article",
        section="73",
        rule_class=RuleClass.MANDATORY,
        stage=Stage.AFTER,
        consequence=Consequence.ADMINISTRATIVE,
    ),
    _rule(
        key="kh.arbitration_agreement",
        clause="争议解决",
        standard=(
            "柬埔寨《商事仲裁法》(2006) 要求仲裁协议书面，并设国家商事仲裁中心"
            "（NCAC）；涉外条款常选 SIAC / HKIAC。仲裁地、语言与仲裁员人数须写清。"
            "【后果】条款不明会导致仲裁申请被驳回，争议退回法院（审理周期很长）。"
        ),
        law="Law on Commercial Arbitration (10/2006)",
        severity=Severity.HIGH,
    ),
    _rule(
        key="kh.vat_rate",
        clause="价款与税",
        standard=(
            "柬埔寨增值税为 10%（见《税法》与实施副法令）；跨境服务与出口适用零税率，合同须明确含税口径与代扣代缴义务。"
        ),
        law="Sub-Decree No. 55 on the revision of Article 56 of Sub-Decree No. 114 on December 24, 1999 on Value Added Tax",
        note="增值税实施副法令",
        stage=Stage.DURING,
        rule_class=RuleClass.MANDATORY,
        consequence=Consequence.ADMINISTRATIVE,
    ),
]


# ── 老挝（LA）──────────────────────────────────────────────────────────
#: 条号已核：Resolution of Economic Disputes 5。其余只核到法名。

LAOS_RULES: list[dict[str, Any]] = [
    _rule(
        key="la.land_lease_foreign",
        clause="不动产权属",
        standard=(
            "老挝《土地法》下外国人/外资法人**不得拥有土地所有权**，只能租赁国有或"
            "私人土地并按法律登记；租赁期限与续期依土地类别与投资审批确定。"
            "合同应写明租赁登记义务、期限与到期处理。"
            "【后果】约定所有权移转无法生效，租赁未登记亦难以对抗第三人。"
        ),
        law="Land Law (Amended)",
        law_no="2020",
        severity=Severity.HIGH,
        rule_class=RuleClass.MANDATORY,
        stage=Stage.BEFORE,
        consequence=Consequence.INVALID,
    ),
    _rule(
        key="la.investment_promotion",
        clause="经营资格",
        standard=(
            "老挝《投资促进法》把投资分为特许经营、受控与普通清单：前两类须经"
            "投资主管部门（MPI）批准并取得经营登记证；优惠与清单绑定。"
            "合同应写明批准取得责任与未获批准的解约/退款安排。"
        ),
        law="Law on Investment Promotion (Amended)",
        law_no="2016",
        severity=Severity.HIGH,
        rule_class=RuleClass.MANDATORY,
        stage=Stage.BEFORE,
        consequence=Consequence.ADMINISTRATIVE,
    ),
    _rule(
        key="la.arbitration",
        clause="争议解决",
        standard=(
            "老挝《经济争端解决法》允许当事人选择协商、调解、仲裁或诉讼；"
            "选择仲裁的，须书面约定并明确机构（如老挝经济争议仲裁中心）。"
            "【后果】未书面约定则无法进入仲裁；境外裁决执行需经法院承认。"
        ),
        law="Law on Resolution of Economic Disputes",
        law_no="2018",
        cite="Article",
        section="5",
        severity=Severity.HIGH,
    ),
    _rule(
        key="la.labour_severance",
        clause="劳动用工",
        standard=(
            "解除劳动合同时，雇主须依《劳动法》支付遣散/补偿（按工龄与合同类型），"
            "外籍员工须持工作许可与配额指标。约定低于法定标准的补偿无效。"
        ),
        law="Labor Act (Revised)",
        law_no="2014",
        rule_class=RuleClass.MANDATORY,
        stage=Stage.AFTER,
        consequence=Consequence.ADMINISTRATIVE,
    ),
    _rule(
        key="la.vat_rate",
        clause="价款与税",
        standard="老挝增值税为 10%，合同须明确含税口径与代扣代缴安排。",
        law="Law on Value Added Tax (Revised)",
        stage=Stage.DURING,
        rule_class=RuleClass.MANDATORY,
        consequence=Consequence.ADMINISTRATIVE,
    ),
]


# ── 缅甸（MM）──────────────────────────────────────────────────────────
#: 缅甸无民法典式成文合同法可引；土地与投资限制主要落在投资许可与专门法上。

MYANMAR_RULES: list[dict[str, Any]] = [
    _rule(
        key="mm.investment_endorsement",
        clause="经营资格",
        standard=(
            "外国投资在缅甸须依《缅甸投资法》取得 MIC 投资许可或投资背书"
            "（endorsement），部分业务还受负面清单与合资比例限制；"
            "合同应把许可/背书取得写成交割前提。"
            "【后果】无许可经营可被停业；以本地人代持的安排不受保护。"
        ),
        law="Myanmar Investment Law",
        law_no="2016",
        severity=Severity.HIGH,
        rule_class=RuleClass.MANDATORY,
        stage=Stage.BEFORE,
        consequence=Consequence.ADMINISTRATIVE,
    ),
    _rule(
        key="mm.land_use_right",
        clause="不动产权属",
        standard=(
            "外国人不得取得缅甸土地所有权；外资只能通过 MIC 许可/背书取得"
            "**长期租赁土地使用权**，期限与续期须写进许可。合同应写明租赁期限、"
            "登记与到期后地上建筑物的处理。"
            "【后果】约定土地所有权移转的条款无法登记，租赁超期亦不受保护。"
        ),
        law="Myanmar Investment Law",
        law_no="2016",
        severity=Severity.HIGH,
        rule_class=RuleClass.MANDATORY,
        stage=Stage.BEFORE,
        consequence=Consequence.INVALID,
    ),
    _rule(
        key="mm.arbitration_agreement",
        clause="争议解决",
        standard=(
            "缅甸《仲裁法》(2016) 采 UNCITRAL 示范法体例：仲裁协议须书面，"
            "法院在法定情形下应中止诉讼并提交仲裁；境外裁决可依法承认执行。"
            "合同应明确仲裁地、机构与语言。"
        ),
        law="Arbitration Law",
        law_no="2016",
        severity=Severity.HIGH,
    ),
    _rule(
        key="mm.commercial_tax",
        clause="价款与税",
        standard=(
            "缅甸**没有增值税**，对货物与服务征收商业税（Commercial Tax，一般 5%），"
            "另有预提税；合同须明确含税口径与由谁申报。"
            "【后果】照抄他国「VAT 10%」条款，会与缅甸税制不符并造成税负争议。"
        ),
        law="Commercial Tax Law",
        stage=Stage.DURING,
        rule_class=RuleClass.MANDATORY,
        consequence=Consequence.ADMINISTRATIVE,
    ),
    _rule(
        key="mm.labour_termination",
        clause="劳动用工",
        standard=(
            "缅甸劳动法对解除劳动关系设有程序与补偿要求（依《劳动争议解决法》"
            "与相关条例）；没有统一的可套用公式，须按合同与最新条例核定。"
            "合同应写明通知期、补偿计算与争议处理路径。"
        ),
        law="Settlement of Labour Dispute Law",
        rule_class=RuleClass.MANDATORY,
        stage=Stage.AFTER,
        consequence=Consequence.ADMINISTRATIVE,
    ),
]


# ── 文莱（BN）──────────────────────────────────────────────────────────

BRUNEI_RULES: list[dict[str, Any]] = [
    _rule(
        key="bn.land_ownership",
        clause="不动产权属",
        standard=(
            "文莱《土地法典》下外国人/外资公司取得土地受严格限制，"
            "通常只能取得有期限的租赁（须政府批准），不得取得永久地权。"
            "合同应写明租赁期限、批准条件与到期处理。"
            "【后果】约定所有权移转的条款无法登记。"
        ),
        law="Land Code",
        law_no="1909",
        severity=Severity.HIGH,
        rule_class=RuleClass.MANDATORY,
        stage=Stage.BEFORE,
        consequence=Consequence.INVALID,
    ),
    _rule(
        key="bn.arbitration_agreement",
        clause="争议解决",
        standard=(
            "文莱《仲裁法》（2024 修订版）与《国际仲裁法》采示范法体例："
            "仲裁协议须书面，法院在法定情形下中止诉讼。仲裁地、机构与语言须写清。"
        ),
        law="Arbitration Act (Revised Edition 2024)",
        severity=Severity.HIGH,
    ),
    _rule(
        key="bn.no_vat",
        clause="价款与税",
        standard=(
            "文莱**不征收增值税/消费税**（无 VAT/GST），主要税种为企业所得税；"
            "合同不应照抄「VAT 10%」之类条款，应改为明确「价格已含全部税费」"
            "或按所得税/关税口径约定。"
            "【后果】写错税种会导致报价与实际税负不符，且无法开具对应发票。"
        ),
        law="Income Tax Act",
        note="文莱无 VAT/GST 立法",
        stage=Stage.DURING,
        rule_class=RuleClass.MANDATORY,
        consequence=Consequence.ADMINISTRATIVE,
    ),
    _rule(
        key="bn.employment_termination",
        clause="劳动用工",
        standard=(
            "《2009 就业法》规定终止雇佣的通知期与基本保障；文莱**没有普遍法定遣散费**，"
            "补偿按合同/惯例处理。合同应写明通知期与终止补偿。"
        ),
        law="Employment Order, 2009",
        stage=Stage.AFTER,
        required=False,
    ),
    _rule(
        key="bn.foreign_investment",
        clause="经营资格",
        standard=(
            "文莱无一般外资准入审批，外资可依《公司法》设立公司；"
            "但金融、油气、通信、教育等须取得主管部门许可。"
            "合同应写明许可取得责任与未取得的解约安排。"
        ),
        law="Companies Act Revised Edition 2015",
        stage=Stage.BEFORE,
        required=False,
    ),
]


#: 法域 → 规则集。东帝汶（TL）不在 BARLC 覆盖范围，**故意不给库**：
#: 给一套「看着像」的标准比明说「本国无标准库」危险得多。
RULES_BY_JURISDICTION: dict[str, list[dict[str, Any]]] = {
    "TH": THAI_RULES,
    "VN": VIETNAM_RULES,
    "MY": MALAYSIA_RULES,
    "SG": SINGAPORE_RULES,
    "ID": INDONESIA_RULES,
    "PH": PHILIPPINES_RULES,
    "KH": CAMBODIA_RULES,
    "LA": LAOS_RULES,
    "MM": MYANMAR_RULES,
    "BN": BRUNEI_RULES,
}

#: 法域 → 中文名（`builtin_name` 与提示词共用）
JURISDICTION_LABEL: dict[str, str] = {
    "CN": "中国",
    "TH": "泰国",
    "VN": "越南",
    "MY": "马来西亚",
    "SG": "新加坡",
    "ID": "印度尼西亚",
    "PH": "菲律宾",
    "KH": "柬埔寨",
    "LA": "老挝",
    "MM": "缅甸",
    "BN": "文莱",
}


__all__ = [
    "BRUNEI_RULES",
    "CAMBODIA_RULES",
    "CITATION_RULES",
    "INDONESIA_RULES",
    "JURISDICTION_LABEL",
    "LAOS_RULES",
    "MALAYSIA_RULES",
    "MYANMAR_RULES",
    "PENDING",
    "PHILIPPINES_RULES",
    "RULES_BY_JURISDICTION",
    "SINGAPORE_RULES",
    "THAI_RULES",
    "VIETNAM_RULES",
]
