"""
法律文书生成系统 - 选项类定义

本模块定义所有 TextChoices 类,用于模型字段的选项.
"""

from __future__ import annotations

from django.db import models

# ============================================================
# 案件类型和阶段选项(与 core.enums 保持一致)
# ============================================================


class DocumentCaseType(models.TextChoices):
    """文书适用的案件类型"""

    CIVIL = "civil", "民事"
    ADMINISTRATIVE = "administrative", "行政"
    CRIMINAL = "criminal", "刑事"
    EXECUTION = "execution", "申请执行"
    BANKRUPTCY = "bankruptcy", "破产"
    ALL = "all", "通用"


class DocumentCaseStage(models.TextChoices):
    """文书适用的案件阶段"""

    FIRST_TRIAL = "first_trial", "一审"
    SECOND_TRIAL = "second_trial", "二审"
    ENFORCEMENT = "enforcement", "执行"
    LABOR_ARBITRATION = "labor_arbitration", "劳动仲裁"
    ADMIN_REVIEW = "administrative_review", "行政复议"
    RETRIAL = "retrial", "再审"
    ALL = "all", "通用"


class DocumentContractType(models.TextChoices):
    """文书适用的合同类型(与 CaseType 保持一致)"""

    CIVIL = "civil", "民商事"
    CRIMINAL = "criminal", "刑事"
    ADMINISTRATIVE = "administrative", "行政"
    LABOR = "labor", "劳动仲裁"
    INTL = "intl", "商事仲裁"
    SPECIAL = "special", "专项服务"
    ADVISOR = "advisor", "常法顾问"
    ALL = "all", "通用"


# ============================================================
# 文件夹模板选项
# ============================================================


class FolderTemplateType(models.TextChoices):
    """文件夹模板类型"""

    CONTRACT = "contract", "合同文件夹模板"
    CASE = "case", "案件文件夹模板"


# ============================================================
# 文件模板选项
# ============================================================


class DocumentTemplateType(models.TextChoices):
    """文件模板类型(第一级分类)"""

    CONTRACT = "contract", "合同文件模板"
    CASE = "case", "案件文件模板"
    ARCHIVE = "archive", "归档文件模板"


class DocumentContractSubType(models.TextChoices):
    """合同文书子类型(第二级分类)"""

    CONTRACT = "contract", "合同模板"
    SUPPLEMENTARY_AGREEMENT = "supplementary_agreement", "补充协议模板"


class DocumentCaseFileSubType(models.TextChoices):
    """案件文件子类型(第二级分类)"""

    PLEADING_MATERIALS = "pleading_materials", "诉状材料"
    EVIDENCE_MATERIALS = "evidence_materials", "证据材料"
    POWER_OF_ATTORNEY_MATERIALS = "power_of_attorney_materials", "授权委托材料"
    PROPERTY_PRESERVATION_MATERIALS = "property_preservation_materials", "财产保全材料"
    SERVICE_ADDRESS_MATERIALS = "service_address_materials", "送达地址材料"
    REFUND_ACCOUNT_MATERIALS = "refund_account_materials", "收款退费账户材料"
    APPLICATION_MATERIALS = "application_materials", "申请材料"
    OTHER_MATERIALS = "other_materials", "其他材料"


class DocumentArchiveSubType(models.TextChoices):
    """归档文件子类型(第二级分类)"""

    CASE_COVER = "case_cover", "案卷封面模板"
    CLOSING_ARCHIVE_REGISTER = "closing_archive_register", "结案归档登记表模板"
    INNER_CATALOG = "inner_catalog", "卷内目录模板"
    LAWYER_WORK_LOG = "lawyer_work_log", "律师工作日志模板"
    SERVICE_QUALITY_CARD = "service_quality_card", "律师办案服务质量监督卡模板"
    CASE_SUMMARY = "case_summary", "办案小结模板"


# ============================================================
# 占位符选项
# ============================================================


class PlaceholderCategory(models.TextChoices):
    """替换词分类"""

    CASE = "case", "案件信息"
    PARTY = "party", "当事人信息"
    CONTRACT = "contract", "合同信息"
    LAWYER = "lawyer", "律师信息"
    COURT = "court", "法院信息"
    OTHER = "other", "其他"


class PlaceholderFormatType(models.TextChoices):
    """替换词格式类型"""

    TEXT = "text", "文本"
    DATE = "date", "日期"
    DATETIME = "datetime", "日期时间"
    CURRENCY = "currency", "货币"
    NUMBER = "number", "数字"
    PERCENTAGE = "percentage", "百分比"


# ============================================================
# 审计日志选项
# ============================================================


class TemplateAuditAction(models.TextChoices):
    """审计日志操作类型"""

    CREATE = "create", "创建"
    UPDATE = "update", "更新"
    DELETE = "delete", "删除"
    ACTIVATE = "activate", "启用"
    DEACTIVATE = "deactivate", "禁用"
    DUPLICATE = "duplicate", "复制"
    SET_DEFAULT = "set_default", "设为默认"


# ============================================================
# 诉讼地位匹配模式
# ============================================================


class LegalStatusMatchMode(models.TextChoices):
    """诉讼地位匹配模式"""

    ANY = "any", "任意匹配"
    ALL = "all", "全部包含"
    EXACT = "exact", "完全一致"


# ============================================================
# 外部模板选项
# ============================================================


class TemplateCategory(models.TextChoices):
    """外部模板类别"""

    PROPERTY_DECLARATION = "property_declaration", "财产申报表"
    SERVICE_ADDRESS = "service_address", "送达地址确认书"
    CREDITOR_DECLARATION = "creditor_declaration", "债权申报表"
    ELEMENT_COMPLAINT = "element_complaint", "要素式诉状"
    POWER_OF_ATTORNEY = "power_of_attorney", "授权委托书"
    LEGAL_AID = "legal_aid", "法律援助申请表"
    PRESERVATION_APPLICATION = "preservation_application", "财产保全申请书"
    OTHER = "other", "其他"


class SourceType(models.TextChoices):
    """模板来源类型"""

    COURT = "court", "法院"
    ADMINISTRATOR = "administrator", "破产管理人"
    ARBITRATION = "arbitration", "仲裁委员会"
    ADMINISTRATIVE = "administrative", "行政机关"
    OTHER = "other", "其他"


class FillType(models.TextChoices):
    """字段填充类型"""

    TEXT = "text", "文本替换"
    CHECKBOX = "checkbox", "勾选复选框"
    DELETE_INAPPLICABLE = "delete_inapplicable", "删除不适用项"


class TemplateStatus(models.TextChoices):
    """外部模板状态"""

    UPLOADED = "uploaded", "已上传"
    ANALYZING = "analyzing", "分析中"
    ANALYSIS_FAILED = "analysis_failed", "分析失败"
    READY = "ready", "可填充"  # 分析完成，可以直接填充
