"""
法律文书生成系统 - 选项类定义

本模块定义所有 TextChoices 类,用于模型字段的选项.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

# ============================================================
# 案件类型和阶段选项(与 core.enums 保持一致)
# ============================================================


class DocumentCaseType(models.TextChoices):
    """文书适用的案件类型"""

    CIVIL = "civil", _("民事")
    ADMINISTRATIVE = "administrative", _("行政")
    CRIMINAL = "criminal", _("刑事")
    EXECUTION = "execution", _("申请执行")
    BANKRUPTCY = "bankruptcy", _("破产")
    ALL = "all", _("通用")


class DocumentCaseStage(models.TextChoices):
    """文书适用的案件阶段"""

    FIRST_TRIAL = "first_trial", _("一审")
    SECOND_TRIAL = "second_trial", _("二审")
    ENFORCEMENT = "enforcement", _("执行")
    LABOR_ARBITRATION = "labor_arbitration", _("劳动仲裁")
    ADMIN_REVIEW = "administrative_review", _("行政复议")
    RETRIAL = "retrial", _("再审")
    ALL = "all", _("通用")


class DocumentContractType(models.TextChoices):
    """文书适用的合同类型(与 CaseType 保持一致)"""

    CIVIL = "civil", _("民商事")
    CRIMINAL = "criminal", _("刑事")
    ADMINISTRATIVE = "administrative", _("行政")
    LABOR = "labor", _("劳动仲裁")
    INTL = "intl", _("商事仲裁")
    SPECIAL = "special", _("专项服务")
    ADVISOR = "advisor", _("常法顾问")
    ALL = "all", _("通用")


# ============================================================
# 文件夹模板选项
# ============================================================


class FolderTemplateType(models.TextChoices):
    """文件夹模板类型"""

    CONTRACT = "contract", _("合同文件夹模板")
    CASE = "case", _("案件文件夹模板")


# ============================================================
# 文件模板选项
# ============================================================


class DocumentTemplateType(models.TextChoices):
    """文件模板类型(第一级分类)"""

    CONTRACT = "contract", _("合同文件模板")
    CASE = "case", _("案件文件模板")
    ARCHIVE = "archive", _("归档文件模板")


class DocumentContractSubType(models.TextChoices):
    """合同文书子类型(第二级分类)"""

    CONTRACT = "contract", _("合同模板")
    SUPPLEMENTARY_AGREEMENT = "supplementary_agreement", _("补充协议模板")


class DocumentCaseFileSubType(models.TextChoices):
    """案件文件子类型(第二级分类)"""

    PLEADING_MATERIALS = "pleading_materials", _("诉状材料")
    EVIDENCE_MATERIALS = "evidence_materials", _("证据材料")
    POWER_OF_ATTORNEY_MATERIALS = "power_of_attorney_materials", _("授权委托材料")
    PROPERTY_PRESERVATION_MATERIALS = "property_preservation_materials", _("财产保全材料")
    SERVICE_ADDRESS_MATERIALS = "service_address_materials", _("送达地址材料")
    REFUND_ACCOUNT_MATERIALS = "refund_account_materials", _("收款退费账户材料")
    APPLICATION_MATERIALS = "application_materials", _("申请材料")
    OTHER_MATERIALS = "other_materials", _("其他材料")


class DocumentArchiveSubType(models.TextChoices):
    """归档文件子类型(第二级分类)"""

    CASE_COVER = "case_cover", _("案卷封面模板")
    CLOSING_ARCHIVE_REGISTER = "closing_archive_register", _("结案归档登记表模板")
    INNER_CATALOG = "inner_catalog", _("卷内目录模板")
    LAWYER_WORK_LOG = "lawyer_work_log", _("律师工作日志模板")
    SERVICE_QUALITY_CARD = "service_quality_card", _("律师办案服务质量监督卡模板")
    CASE_SUMMARY = "case_summary", _("办案小结模板")


# ============================================================
# 占位符选项
# ============================================================


class PlaceholderCategory(models.TextChoices):
    """替换词分类"""

    CASE = "case", _("案件信息")
    PARTY = "party", _("当事人信息")
    CONTRACT = "contract", _("合同信息")
    LAWYER = "lawyer", _("律师信息")
    COURT = "court", _("法院信息")
    OTHER = "other", _("其他")


class PlaceholderFormatType(models.TextChoices):
    """替换词格式类型"""

    TEXT = "text", _("文本")
    DATE = "date", _("日期")
    DATETIME = "datetime", _("日期时间")
    CURRENCY = "currency", _("货币")
    NUMBER = "number", _("数字")
    PERCENTAGE = "percentage", _("百分比")


# ============================================================
# 审计日志选项
# ============================================================


class TemplateAuditAction(models.TextChoices):
    """审计日志操作类型"""

    CREATE = "create", _("创建")
    UPDATE = "update", _("更新")
    DELETE = "delete", _("删除")
    ACTIVATE = "activate", _("启用")
    DEACTIVATE = "deactivate", _("禁用")
    DUPLICATE = "duplicate", _("复制")
    SET_DEFAULT = "set_default", _("设为默认")


# ============================================================
# 诉讼地位匹配模式
# ============================================================


class LegalStatusMatchMode(models.TextChoices):
    """诉讼地位匹配模式"""

    ANY = "any", _("任意匹配")
    ALL = "all", _("全部包含")
    EXACT = "exact", _("完全一致")


# ============================================================
# 外部模板选项
# ============================================================


class TemplateCategory(models.TextChoices):
    """外部模板类别"""

    PROPERTY_DECLARATION = "property_declaration", _("财产申报表")
    SERVICE_ADDRESS = "service_address", _("送达地址确认书")
    CREDITOR_DECLARATION = "creditor_declaration", _("债权申报表")
    ELEMENT_COMPLAINT = "element_complaint", _("要素式诉状")
    POWER_OF_ATTORNEY = "power_of_attorney", _("授权委托书")
    LEGAL_AID = "legal_aid", _("法律援助申请表")
    PRESERVATION_APPLICATION = "preservation_application", _("财产保全申请书")
    OTHER = "other", _("其他")


class SourceType(models.TextChoices):
    """模板来源类型"""

    COURT = "court", _("法院")
    ADMINISTRATOR = "administrator", _("破产管理人")
    ARBITRATION = "arbitration", _("仲裁委员会")
    ADMINISTRATIVE = "administrative", _("行政机关")
    OTHER = "other", _("其他")


class FillType(models.TextChoices):
    """字段填充类型"""

    TEXT = "text", _("文本替换")
    CHECKBOX = "checkbox", _("勾选复选框")
    DELETE_INAPPLICABLE = "delete_inapplicable", _("删除不适用项")


class TemplateStatus(models.TextChoices):
    """外部模板状态"""

    UPLOADED = "uploaded", _("已上传")
    ANALYZING = "analyzing", _("分析中")
    ANALYSIS_FAILED = "analysis_failed", _("分析失败")
    READY = "ready", _("可填充")  # 分析完成，可以直接填充
