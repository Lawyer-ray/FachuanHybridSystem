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
            strong_keywords=("民事起诉状", "起诉状"),
            weak_keywords=("诉讼请求", "事实与理由", "原告", "被告", "人民法院"),
            negative_keywords=("证据清单", "授权委托书", "送达地址确认书", "退费账户确认书"),
            continuation_keywords=("诉讼请求", "事实与理由", "原告", "被告", "人民法院", "具状人", "此致"),
        ),
        SegmentTemplateRule(
            segment_type=PdfSplitSegmentType.EVIDENCE_LIST,
            label="证据清单及明细",
            default_filename="证据清单及明细",
            strong_keywords=("证据清单", "证据目录"),
            weak_keywords=("证明内容", "页码", "原件", "复印件", "提交人"),
            negative_keywords=("起诉状", "申请书"),
        ),
        SegmentTemplateRule(
            segment_type=PdfSplitSegmentType.PRESERVATION_MATERIALS,
            label="财产保全资料",
            default_filename="财产保全资料",
            strong_keywords=("财产保全申请书", "保全申请书"),
            weak_keywords=("查封", "扣押", "冻结", "申请事项", "事实与理由"),
            negative_keywords=("证据清单", "授权委托书"),
        ),
        SegmentTemplateRule(
            segment_type=PdfSplitSegmentType.PARTY_IDENTITY,
            label="双方当事人主体信息",
            default_filename="双方当事人主体信息",
            strong_keywords=("居民身份证", "中华人民共和国居民身份证"),
            weak_keywords=("营业执照", "公民身份号码", "统一社会信用代码", "签发机关"),
            negative_keywords=("授权委托书", "送达地址确认书"),
        ),
        SegmentTemplateRule(
            segment_type=PdfSplitSegmentType.AUTHORIZATION_MATERIALS,
            label="授权委托材料",
            default_filename="授权委托材料",
            strong_keywords=("授权委托书",),
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
            strong_keywords=("诉讼费用退费账户确认书", "退费账户确认书"),
            weak_keywords=("收款人", "开户行名称", "退费"),
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
