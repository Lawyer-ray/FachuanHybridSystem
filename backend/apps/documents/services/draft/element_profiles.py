"""案由 → 立案要件档案：一套纯数据、零 IO 的「法律上必须凑齐什么」。

## 为什么要件是数据，不是 prompt
`readiness` 让模型回答的是「这一条在本案对应什么事实、出处在哪、是否具备」，不是
「这个案子法律上需要哪几条」。后者一旦交给模型，每次跑出来的清单都不一样：律师没法
复核，也没法解释「为什么这次说缺、下次说不缺」。所以同一案由永远命中同一套 key，
模型只能在这套 key 上打分。

## 为什么 evidence_forms 用 tuple 存、对外再转 list
档案是模块级共享常量，被任何调用方拿到后 `append` 一下就会污染后续所有案件。
tuple 让「改档案」变成显式重建而不是顺手改一个全局 list；对外的矩阵/JSON 里仍然是 list。

## 新案由怎么加
复制一份 `ElementRequirement` 列表 + 触发词进 `ELEMENT_PROFILES` 即可，不要改
`readiness` 的闸门——闸门口径与案由无关，是「blocking 缺口 ≥1 / 缺失 ≥3」这两条硬线。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ElementRequirement:
    """一个立案要件：key 稳定、label 给人看、why 说明缺了会怎样。"""

    key: str
    label: str
    why: str
    evidence_forms: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "label": self.label,
            "why": self.why,
            "evidence_forms": list(self.evidence_forms),
        }


@dataclass(frozen=True)
class VerificationQuestion:
    """向委托人或经办人核实的常见问题（材料回答不了、但直接影响主张的那类）。"""

    to: str
    question: str
    why: str

    def as_dict(self) -> dict[str, str]:
        return {"to": self.to, "question": self.question, "why": self.why}


@dataclass(frozen=True)
class ElementProfile:
    """一份案由对应的完整要件档案。"""

    key: str
    label: str
    triggers: tuple[str, ...]
    requirements: tuple[ElementRequirement, ...]


#: 兜底档案：任何没命中专属档案的案由都落到这里，绝不让调用方拿到「没有要件」。
DEFAULT_PROFILE_KEY = "contract_payment"

LEASE_ARREARS_REQUIREMENTS: tuple[ElementRequirement, ...] = (
    ElementRequirement(
        key="contract_formation",
        label="合同成立生效",
        why="合同不成立或未生效，付款义务与解除权就失去依据，起诉会被直接驳回",
        evidence_forms=("合同原件或完整扫描件（含签字盖章页）", "签订授权或代理手续", "补充协议/变更文件"),
    ),
    ElementRequirement(
        key="our_entitlement",
        label="我方权利来源",
        why="不能证明原告是出租方/发包方或其合法承继人，就没有请求被告付款的资格",
        evidence_forms=("合同当事人页", "权利转让/承继文件", "收款主体确认函"),
    ),
    ElementRequirement(
        key="payment_obligation_due_date",
        label="付款义务与到期日",
        why="没有付款义务与到期日，就无法认定逾期，违约金和解除权都起算不了",
        evidence_forms=("合同付款条款", "付款节点表/年度缴款通知", "对账确认单"),
    ),
    ElementRequirement(
        key="unpaid_fact",
        label="未付事实",
        why="只有欠款主张没有未付证据，被告一句「已付」就能把举证责任推回我方",
        evidence_forms=("银行流水/收款明细", "对账单或催款台账", "发票/收据存根"),
    ),
    ElementRequirement(
        key="amount_calculation",
        label="金额计算",
        why="本金、违约金、管理费口径算不清，诉请金额会被当庭核减",
        evidence_forms=("欠款明细表（按期间/项目）", "合同计价条款", "违约金计算表"),
    ),
    ElementRequirement(
        key="demand_and_breach",
        label="催告与违约",
        why="没有催告与违约事实，违约起算点和解除前的宽限期都证明不了",
        evidence_forms=("律师函/催告函", "送达凭证（快递单/签收记录/EMS 查询）", "微信/邮件催告记录"),
    ),
    ElementRequirement(
        key="contractual_termination_right",
        label="约定解除权",
        why="没有合同依据的解除是违法解除，解除通知反而可能变成对方索赔的把柄",
        evidence_forms=("合同解除条款全文", "违约情形与解除条件条款", "补充协议"),
    ),
    ElementRequirement(
        key="termination_notice",
        label="解除通知或行使",
        why="解除权不通知不生效；未行使就起诉要求返还土地，会被认为合同仍在履行",
        evidence_forms=("解除通知/律师函原件", "送达凭证", "对方回复或签收记录"),
    ),
    ElementRequirement(
        key="security_deposit",
        label="履约保证金（没收或抵扣）",
        why="保证金金额、缴纳事实与持有状态不清，没收/抵扣的诉请会落空或算错",
        evidence_forms=("保证金条款", "缴纳凭证/收款收据", "保证金变更或退还记录"),
    ),
    ElementRequirement(
        key="premises_return",
        label="返还土地与地上物",
        why="解除后不主张返还与腾退，判决只解决钱，土地和地上物仍被占用",
        evidence_forms=("土地交付记录/交接单", "现场照片或测绘资料", "地上物清单"),
    ),
    ElementRequirement(
        key="enforcement_costs",
        label="维权费用",
        why="律师费、保全费等维权费用没有合同或票据依据，法院不会支持",
        evidence_forms=("维权费用条款", "委托代理合同与律师费发票", "保全费/公证费票据"),
    ),
    ElementRequirement(
        key="jurisdiction_and_parties",
        label="管辖与主体",
        why="被告身份不明无法立案送达；管辖约定或连接点缺失会被移送，时间成本全落在客户身上",
        evidence_forms=("被告身份证复印件或户籍信息", "原告营业执照/主体资格证明", "合同管辖条款或不动产所在地证明"),
    ),
)

CONTRACT_PAYMENT_REQUIREMENTS: tuple[ElementRequirement, ...] = (
    ElementRequirement(
        key="contract_formation",
        label="合同成立生效",
        why="合同不成立或未生效，付款请求就没有请求权基础",
        evidence_forms=("合同原件或完整扫描件（含签字盖章页）", "签订授权或代理手续", "补充协议/变更文件"),
    ),
    ElementRequirement(
        key="our_entitlement",
        label="我方权利来源",
        why="不能证明原告是合同债权人或其合法承继人，就没有请求付款的资格",
        evidence_forms=("合同当事人页", "债权转让/承继文件", "收款主体确认函"),
    ),
    ElementRequirement(
        key="payment_obligation_due_date",
        label="付款义务与到期日",
        why="没有付款义务与到期日，就无法认定逾期，违约金也起算不了",
        evidence_forms=("合同付款条款", "付款节点表/结算单", "对账确认单"),
    ),
    ElementRequirement(
        key="unpaid_fact",
        label="未付事实",
        why="只有欠款主张没有未付证据，被告一句「已付」就能把举证责任推回我方",
        evidence_forms=("银行流水/收款明细", "对账单或催款台账", "发票/收据存根"),
    ),
    ElementRequirement(
        key="amount_calculation",
        label="金额计算",
        why="本金、违约金口径算不清，诉请金额会被当庭核减",
        evidence_forms=("欠款明细表（按期间/项目）", "合同计价条款", "违约金计算表"),
    ),
    ElementRequirement(
        key="demand_and_breach",
        label="催告与违约",
        why="没有催告与违约事实，违约起算点和宽限期都证明不了",
        evidence_forms=("催款函/律师函", "送达凭证", "微信/邮件催告记录"),
    ),
    ElementRequirement(
        key="liability_and_costs",
        label="违约责任与维权费用",
        why="违约金、律师费等费用没有合同或票据依据，法院不会支持",
        evidence_forms=("违约责任条款", "维权费用条款", "律师费发票/保全费票据"),
    ),
    ElementRequirement(
        key="parties_identity",
        label="主体与送达地址",
        why="被告身份或送达地址不明无法立案送达，会被拖成公告送达",
        evidence_forms=("被告身份证复印件或户籍信息", "原告营业执照/主体资格证明", "合同送达地址条款"),
    ),
    ElementRequirement(
        key="jurisdiction",
        label="管辖依据",
        why="管辖约定无效或没有连接点，立案会被移送，时间成本全落在客户身上",
        evidence_forms=("合同管辖条款", "被告住所地/合同履行地证明"),
    ),
)

#: 常见核实问题：按档案分组，只问材料回答不了、但直接影响主张的事项。
QUESTION_BANK: dict[str, tuple[VerificationQuestion, ...]] = {
    "lease_arrears": (
        VerificationQuestion(
            to="委托人经办人",
            question="截至起诉前，被告已支付哪些期间、哪些项目的款项？有无付款凭证？",
            why="已付部分直接决定欠款本金，律师函只列未付期间，不能当作完整对账",
        ),
        VerificationQuestion(
            to="委托人财务",
            question="合同约定的付款节点与实际收款节点分别是什么时候？",
            why="到期日决定逾期起算与违约金，节点不清就算不出天数",
        ),
        VerificationQuestion(
            to="委托人经办人",
            question="土地/场地是否已实际交付给被告？有无交接单或现场记录？",
            why="交付事实是租金/承包金请求的对价基础，被告常以未交付抗辩",
        ),
        VerificationQuestion(
            to="委托人",
            question="被告确认的送达地址是哪里？合同里是否写了送达条款？",
            why="送达地址决定立案与后续文书能否有效送达，缺了会拖成公告送达",
        ),
        VerificationQuestion(
            to="委托人财务",
            question="履约保证金是否已实际缴纳？现在由谁持有、有无退还或抵扣记录？",
            why="保证金诉请需要缴纳与持有事实，只有合同条款不足以主张没收",
        ),
        VerificationQuestion(
            to="委托人经办人",
            question="水费/管理费的通知或账单是否送达被告？被告最后一次确认收到是哪一天？",
            why="按通知计费的期间从送达日起算，收不到通知的期间法院通常不支持",
        ),
    ),
    "contract_payment": (
        VerificationQuestion(
            to="委托人经办人",
            question="截至起诉前，被告已支付哪些款项？有无付款凭证？",
            why="已付部分直接决定欠款本金，单方台账不能当作完整对账",
        ),
        VerificationQuestion(
            to="委托人财务",
            question="合同约定的付款节点与实际收款节点分别是什么时候？",
            why="到期日决定逾期起算与违约金，节点不清就算不出天数",
        ),
        VerificationQuestion(
            to="委托人",
            question="被告确认的送达地址是哪里？合同里是否写了送达条款？",
            why="送达地址决定立案与后续文书能否有效送达，缺了会拖成公告送达",
        ),
        VerificationQuestion(
            to="委托人经办人",
            question="合同项下的交付/履行是否已经完成？有无验收或确认记录？",
            why="对待给付是否履行，决定付款条件是否已经成就",
        ),
    ),
}

ELEMENT_PROFILES: dict[str, ElementProfile] = {
    "lease_arrears": ElementProfile(
        key="lease_arrears",
        label="土地/房屋租赁承包欠租",
        triggers=("租赁", "承包", "租金", "承包金", "分包", "土地"),
        requirements=LEASE_ARREARS_REQUIREMENTS,
    ),
    DEFAULT_PROFILE_KEY: ElementProfile(
        key=DEFAULT_PROFILE_KEY,
        label="合同付款（兜底）",
        triggers=("合同", "买卖", "服务", "承揽", "借款"),
        requirements=CONTRACT_PAYMENT_REQUIREMENTS,
    ),
}


def pick_profile(cause_of_action: str, *, hint: str = "") -> ElementProfile:
    """按案由取要件档案：专属档案优先，其余一律落到兜底档案。

    为什么不在兜底档案也做「触发词匹配」：兜底的定义就是「没命中任何专属档案」。
    把它也放进匹配循环，只会让「案由为空」和「案由是买卖合同」走出两条不同的路径，
    而它们要的其实是同一份通用档案。

    **为什么要多一个 hint**：库里登记的案由经常只有一个大类（真机 case 489 就是「合同纠纷」），
    而真正区分要件的是标的与合同类型（土地分包/承包）。只按案由匹配会让所有合同案都落到
    9 条兜底要件上，解除权、保证金、返还土地这些本案真正的战场一条都不问。hint 由调用方
    给（材料抬头/合同名/案件名），拼在案由后面一起匹配——**它只影响选哪份档案，不进提示词**。
    """
    text = f"{cause_of_action or ''} {hint or ''}".strip()
    for profile in ELEMENT_PROFILES.values():
        if profile.key == DEFAULT_PROFILE_KEY:
            continue
        if any(trigger in text for trigger in profile.triggers):
            return profile
    return ELEMENT_PROFILES[DEFAULT_PROFILE_KEY]


__all__ = [
    "CONTRACT_PAYMENT_REQUIREMENTS",
    "DEFAULT_PROFILE_KEY",
    "ELEMENT_PROFILES",
    "LEASE_ARREARS_REQUIREMENTS",
    "QUESTION_BANK",
    "ElementProfile",
    "ElementRequirement",
    "VerificationQuestion",
    "pick_profile",
]
