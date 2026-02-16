"""
法律文书生成系统 - 选项类定义

本模块定义所有 TextChoices 类,用于模型字段的选项.
"""

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
