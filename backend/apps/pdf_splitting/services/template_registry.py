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
    ),
)

_REGISTRY = {FILING_MATERIALS_V1.key: FILING_MATERIALS_V1}


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
