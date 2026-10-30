from __future__ import annotations

from dataclasses import dataclass

from apps.pdf_splitting.models import PdfSplitSegmentType


@dataclass(frozen=True)
class SegmentTemplateRule:
    segment_type: str
    label: str
    default_filename: str
    strong_keywords: tuple[str, ...]
    weak_keywords: tuple[str, ...] = ()
    negative_keywords: tuple[str, ...] = ()
    continuation_keywords: tuple[str, ...] = ()


@dataclass(frozen=True)
class TemplateDefinition:
    key: str
    version: str
    label: str
    rules: tuple[SegmentTemplateRule, ...]


FILING_MATERIALS_V1 = TemplateDefinition(
    key="filing_materials_v1",
    version="1",
    label="立案材料模板 v1",
    rules=(
        SegmentTemplateRule(
            segment_type=PdfSplitSegmentType.COMPLAINT,
            label="起诉状",
            default_filename="起诉状",
            strong_keywords=("民事起诉状", "起诉状", "民事诉状", "诉状", "民事诉讼起诉状"),
            weak_keywords=("诉讼请求", "事实与理由", "原告", "被告", "人民法院"),
            negative_keywords=("证据清单", "授权委托书", "送达地址确认书", "退费账户确认书"),
            continuation_keywords=("诉讼请求", "事实与理由", "原告", "被告", "人民法院", "具状人", "此致"),
        ),
        SegmentTemplateRule(
            segment_type=PdfSplitSegmentType.EVIDENCE_LIST,
            label="证据清单及明细",
            default_filename="证据清单及明细",
            strong_keywords=("证据清单", "证据目录", "证据材料清单", "证据材料目录"),
            weak_keywords=("证明内容", "页码", "原件", "复印件", "提交人"),
            negative_keywords=("起诉状", "申请书"),
        ),
        SegmentTemplateRule(
            segment_type=PdfSplitSegmentType.PRESERVATION_MATERIALS,
            label="财产保全资料",
            default_filename="财产保全资料",
            strong_keywords=("财产保全申请书", "保全申请书", "诉讼保全申请书", "财产保全申请"),
            weak_keywords=("查封", "扣押", "冻结", "申请事项", "事实与理由"),
            negative_keywords=("证据清单", "授权委托书"),
        ),
        SegmentTemplateRule(
            segment_type=PdfSplitSegmentType.PARTY_IDENTITY,
            label="双方当事人主体信息",
            default_filename="双方当事人主体信息",
            strong_keywords=(
                "居民身份证",
                "中华人民共和国居民身份证",
                "身份证",
                "营业执照",
                "企业信用信息公示",
            ),
            weak_keywords=("公民身份号码", "统一社会信用代码", "签发机关"),
            negative_keywords=("授权委托书", "送达地址确认书"),
        ),
        SegmentTemplateRule(
            segment_type=PdfSplitSegmentType.AUTHORIZATION_MATERIALS,
            label="授权委托材料",
            default_filename="授权委托材料",
            strong_keywords=("授权委托书", "委托代理合同", "法律服务委托合同"),
            weak_keywords=("代理权限", "受托人", "委托人", "律师事务所"),
            negative_keywords=("送达地址确认书", "退费账户确认书"),
        ),
        SegmentTemplateRule(
            segment_type=PdfSplitSegmentType.DELIVERY_ADDRESS_CONFIRMATION,
            label="送达地址确认书",
            default_filename="送达地址确认书",
            strong_keywords=("送达地址确认书",),
            weak_keywords=("诉讼文书", "送达", "电子送达"),
        ),
        SegmentTemplateRule(
            segment_type=PdfSplitSegmentType.REFUND_ACCOUNT_CONFIRMATION,
            label="诉讼费用退费账户确认书",
            default_filename="诉讼费用退费账户确认书",
            strong_keywords=("诉讼费用退费账户确认书", "退费账户确认书", "退费账户确认", "诉讼费退费"),
            weak_keywords=("收款人", "开户行名称", "退费"),
        ),
        SegmentTemplateRule(
            segment_type=PdfSplitSegmentType.LOAN_CONTRACT,
            label="借款合同",
            default_filename="借款合同",
            strong_keywords=("个人借款合同", "借款合同", "贷款合同", "流动资金借款合同"),
            weak_keywords=("借款人", "贷款人", "借款金额", "借款期限", "借款利率"),
        ),
        SegmentTemplateRule(
            segment_type=PdfSplitSegmentType.LOAN_DISBURSEMENT_RECORD,
            label="放款凭证",
            default_filename="放款凭证",
            strong_keywords=("借款借据", "贷款借据", "放款凭证", "贷款发放凭证", "借款凭证"),
            weak_keywords=("放款金额", "贷款账号", "借款日期", "实际发放"),
        ),
        SegmentTemplateRule(
            segment_type=PdfSplitSegmentType.BANK_STATEMENT,
            label="银行流水",
            default_filename="银行流水",
            strong_keywords=("银行交易明细", "账户交易明细", "个人活期明细", "账户明细清单", "交易流水"),
            weak_keywords=("交易日期", "借方发生额", "贷方发生额", "账户余额", "交易摘要"),
        ),
        SegmentTemplateRule(
            segment_type=PdfSplitSegmentType.INTEREST_CALCULATION,
            label="利息计算表",
            default_filename="利息计算表",
            strong_keywords=("利息计算表", "利息明细表", "罚息计算表", "逾期利息计算", "本息计算明细"),
            weak_keywords=("计息期间", "执行利率", "计息天数", "利息金额", "本金余额"),
        ),
        SegmentTemplateRule(
            segment_type=PdfSplitSegmentType.DELIVERY_NOTE,
            label="送货单",
            default_filename="送货单",
            strong_keywords=("送货单", "送货清单", "发货单", "出库单"),
            weak_keywords=("收货单位", "发货单位", "货物名称", "送货日期", "数量"),
        ),
        SegmentTemplateRule(
            segment_type=PdfSplitSegmentType.GOODS_RECEIPT,
            label="收货单",
            default_filename="收货单",
            strong_keywords=("收货单", "收货确认单", "签收单", "货物签收单"),
            weak_keywords=("收货人", "签收人", "收货日期", "验收"),
        ),
        SegmentTemplateRule(
            segment_type=PdfSplitSegmentType.INVOICE,
            label="发票",
            default_filename="发票",
            strong_keywords=("增值税专用发票", "增值税普通发票", "电子发票", "发票联"),
            weak_keywords=("发票号码", "开票日期", "购买方", "销售方", "价税合计"),
        ),
        # ── 诉讼程序类文书 ──
        # 补齐前，判决书/上诉状/答辩状全部落到 unrecognized。
        SegmentTemplateRule(
            segment_type=PdfSplitSegmentType.JUDGMENT,
            label="判决书",
            default_filename="民事判决书",
            strong_keywords=("民事判决书", "判决书", "本院认为", "判决如下"),
            weak_keywords=("审判员", "书记员", "人民陪审员", "如不服本判决", "本院查明"),
        ),
        SegmentTemplateRule(
            segment_type=PdfSplitSegmentType.RULING,
            label="裁定书",
            default_filename="民事裁定书",
            strong_keywords=("民事裁定书", "裁定书", "裁定如下"),
            weak_keywords=("审判长", "本裁定为终审裁定", "准许", "驳回"),
        ),
        SegmentTemplateRule(
            segment_type=PdfSplitSegmentType.MEDIATION_STATEMENT,
            label="调解书",
            default_filename="民事调解书",
            strong_keywords=("民事调解书", "调解书", "协议如下"),
            weak_keywords=("双方当事人自愿达成", "本调解书经双方签收后"),
        ),
        SegmentTemplateRule(
            segment_type=PdfSplitSegmentType.APPEAL_PETITION,
            label="上诉状",
            default_filename="民事上诉状",
            strong_keywords=("民事上诉状", "上诉状", "上诉请求"),
            weak_keywords=("上诉人", "被上诉人", "上诉理由", "不服", "提起上诉"),
        ),
        SegmentTemplateRule(
            segment_type=PdfSplitSegmentType.DEFENSE_STATEMENT,
            label="答辩状",
            default_filename="民事答辩状",
            strong_keywords=("民事答辩状", "答辩状", "答辩意见", "答辩如下"),
            weak_keywords=("答辩人", "被答辩人", "请求驳回", "维持原判"),
        ),
        SegmentTemplateRule(
            segment_type=PdfSplitSegmentType.RETRIAL_APPLICATION,
            label="再审申请书",
            default_filename="再审申请书",
            strong_keywords=("再审申请书", "申请再审"),
            weak_keywords=("再审申请人", "再审请求", "原判决确有错误"),
        ),
        SegmentTemplateRule(
            segment_type=PdfSplitSegmentType.ENFORCEMENT_APPLICATION,
            label="执行申请书",
            default_filename="执行申请书",
            strong_keywords=("执行申请书", "强制执行申请书", "申请执行书"),
            weak_keywords=("申请执行人", "被执行人", "执行依据", "申请事项"),
        ),
        SegmentTemplateRule(
            segment_type=PdfSplitSegmentType.COURT_RECORD,
            label="庭审笔录",
            default_filename="庭审笔录",
            strong_keywords=("庭审笔录", "法庭审理笔录", "询问笔录", "开庭笔录"),
            weak_keywords=("审判员", "书记员", "现在开庭", "核对当事人身份", "质证"),
        ),
        SegmentTemplateRule(
            segment_type=PdfSplitSegmentType.AGENT_OPINION,
            label="代理词",
            default_filename="代理词",
            strong_keywords=("代理词", "代理意见"),
            weak_keywords=("尊敬的审判长", "代理人认为", "综上"),
        ),
    ),
)

# ══════════════════════════════════════════════════════════
# 二审答辩材料模板
# ══════════════════════════════════════════════════════════
#
# 为什么必须是**独立模板**而不是往立案模板里加类型：
#   LLM 的 prompt 会列出「这个模板可用的 type 键名」并问「这段属于哪一类」。
#   如果把判决书/上诉状塞进「立案材料模板」，模型看到模板名叫 filing_materials
#   会判断这些不属于立案材料，一律回 other → 全部落 unrecognized。
#   实测就是这样：补了枚举与规则，段类型仍是 unrecognized。
#   给二审单独一个模板，模型才知道「在本场景里，判决书是合法的一类」。
APPEAL_DEFENSE_V1 = TemplateDefinition(
    key="appeal_defense_v1",
    version="1",
    label="二审答辩材料模板 v1",
    rules=(
        SegmentTemplateRule(
            segment_type=PdfSplitSegmentType.JUDGMENT,
            label="一审判决书",
            default_filename="一审民事判决书",
            strong_keywords=("民事判决书", "判决书", "判决如下"),
            weak_keywords=("本院认为", "本院查明", "审判员", "书记员", "如不服本判决"),
            negative_keywords=("上诉状", "答辩状", "庭审笔录"),
            continuation_keywords=("本院认为", "判决如下", "审判员", "书记员"),
        ),
        SegmentTemplateRule(
            segment_type=PdfSplitSegmentType.APPEAL_PETITION,
            label="上诉状",
            default_filename="民事上诉状",
            strong_keywords=("民事上诉状", "上诉状", "上诉请求"),
            weak_keywords=("上诉人", "被上诉人", "上诉理由", "提起上诉"),
            negative_keywords=("答辩状", "判决书"),
        ),
        SegmentTemplateRule(
            segment_type=PdfSplitSegmentType.DEFENSE_STATEMENT,
            label="答辩状",
            default_filename="民事答辩状",
            strong_keywords=("民事答辩状", "答辩状", "答辩意见", "答辩如下"),
            weak_keywords=("答辩人", "被答辩人", "请求驳回", "维持原判"),
            negative_keywords=("上诉状", "判决书"),
        ),
        SegmentTemplateRule(
            segment_type=PdfSplitSegmentType.COURT_RECORD,
            label="庭审笔录",
            default_filename="庭审笔录",
            strong_keywords=("庭审笔录", "法庭审理笔录", "开庭笔录", "询问笔录"),
            weak_keywords=("现在开庭", "核对当事人身份", "质证", "审判员", "书记员"),
        ),
        SegmentTemplateRule(
            segment_type=PdfSplitSegmentType.EVIDENCE_LIST,
            label="一审证据材料",
            default_filename="一审证据材料",
            strong_keywords=("证据目录", "证据清单", "证据材料汇编"),
            weak_keywords=("证明目的", "序号", "证据名称"),
        ),
        SegmentTemplateRule(
            segment_type=PdfSplitSegmentType.AUTHORIZATION_MATERIALS,
            label="授权委托材料",
            default_filename="授权委托材料",
            strong_keywords=("授权委托书", "授权委托", "所函", "律师事务所函"),
            weak_keywords=("委托人", "受托人", "代理权限"),
        ),
        SegmentTemplateRule(
            segment_type=PdfSplitSegmentType.PARTY_IDENTITY,
            label="当事人身份材料",
            default_filename="当事人身份材料",
            strong_keywords=("身份证", "营业执照", "法定代表人身份证明"),
            weak_keywords=("公民身份号码", "统一社会信用代码", "住址"),
        ),
        SegmentTemplateRule(
            segment_type=PdfSplitSegmentType.DELIVERY_ADDRESS_CONFIRMATION,
            label="送达地址确认书",
            default_filename="送达地址确认书",
            strong_keywords=("送达地址确认书", "送达地址确认"),
            weak_keywords=("电子送达", "收件人", "确认人"),
        ),
    ),
)


_REGISTRY = {
    FILING_MATERIALS_V1.key: FILING_MATERIALS_V1,
    APPEAL_DEFENSE_V1.key: APPEAL_DEFENSE_V1,
}


def get_template_definition(template_key: str) -> TemplateDefinition:
    return _REGISTRY.get(template_key, FILING_MATERIALS_V1)


def get_segment_label(segment_type: str) -> str:
    for template in _REGISTRY.values():
        for rule in template.rules:
            if rule.segment_type == segment_type:
                return rule.label
    if segment_type == PdfSplitSegmentType.UNRECOGNIZED:
        return "未识别材料"
    return segment_type


def get_default_filename(segment_type: str) -> str:
    for template in _REGISTRY.values():
        for rule in template.rules:
            if rule.segment_type == segment_type:
                return rule.default_filename
    return "未识别材料"
