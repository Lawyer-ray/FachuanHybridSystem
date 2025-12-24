"""
共享枚举定义模块

本模块包含跨多个 Django app 使用的枚举类型，
避免跨模块直接导入 Model 造成的循环依赖问题。

使用方式:
    from apps.core.enums import CaseType, CaseStatus, CaseStage, LegalStatus
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class CaseType(models.TextChoices):
    """案件类型"""
    CIVIL = "civil", _("民商事")
    CRIMINAL = "criminal", _("刑事")
    ADMINISTRATIVE = "administrative", _("行政")
    LABOR = "labor", _("劳动仲裁")
    INTL = "intl", _("商事仲裁")
    SPECIAL = "special", _("专项服务")
    ADVISOR = "advisor", _("常法顾问")


class LegalStatus(models.TextChoices):
    """诉讼地位"""
    PLAINTIFF = "plaintiff", _("原告")
    DEFENDANT = "defendant", _("被告")
    THIRD = "third", _("第三人")
    APPLICANT = "applicant", _("申请人")
    RESPONDENT = "respondent", _("被申请人")
    CRIMINAL_DEFENDANT = "criminal_defendant", _("被告人")
    VICTIM = "victim", _("被害人")
    APPELLANT = "appellant", _("上诉人")
    APPELLEE = "appellee", _("被上诉人")
    ORIGINAL_PLAINTIFF = "orig_plaintiff", _("原审原告")
    ORIGINAL_DEFENDANT = "orig_defendant", _("原审被告")
    ORIGINAL_THIRD = "orig_third", _("原审第三人")


class CaseStatus(models.TextChoices):
    """案件状态"""
    ACTIVE = "active", _("在办")
    CLOSED = "closed", _("已结案")


class CaseStage(models.TextChoices):
    """案件阶段"""
    FIRST_TRIAL = "first_trial", _("一审")
    SECOND_TRIAL = "second_trial", _("二审")
    ENFORCEMENT = "enforcement", _("执行")
    LABOR_ARBITRATION = "labor_arbitration", _("劳动仲裁")
    ADMIN_REVIEW = "administrative_review", _("行政复议")
    PRIVATE_PROSECUTION = "private_prosecution", _("自诉")
    INVESTIGATION = "investigation", _("侦查")
    PROSECUTION_REVIEW = "prosecution_review", _("审查起诉")
    RETRIAL_FIRST = "retrial_first", _("重审一审")
    RETRIAL_SECOND = "retrial_second", _("重审二审")
    APPLY_RETRIAL = "apply_retrial", _("申请再审")
    REHEARING_FIRST = "rehearing_first", _("再审一审")
    REHEARING_SECOND = "rehearing_second", _("再审二审")
    REVIEW = "review", _("提审")
    DEATH_PENALTY_REVIEW = "death_penalty_review", _("死刑复核程序")
    PETITION = "petition", _("申诉")
    APPLY_PROTEST = "apply_protest", _("申请抗诉")
    PETITION_PROTEST = "petition_protest", _("申诉抗诉")


class AuthorityType(models.TextChoices):
    """主管机关性质"""
    INVESTIGATION = "investigation", _("侦查机关")
    PROSECUTION = "prosecution", _("审查起诉机关")
    TRIAL = "trial", _("审理机构")
    DETENTION = "detention", _("当前关押地点")


class SimpleCaseType(models.TextChoices):
    """案件类型（简化版）"""
    CIVIL = "civil", _("民事")
    ADMINISTRATIVE = "administrative", _("行政")
    CRIMINAL = "criminal", _("刑事")
    EXECUTION = "execution", _("申请执行")
    BANKRUPTCY = "bankruptcy", _("破产")


class CaseLogReminderType(models.TextChoices):
    """案件日志提醒类型"""
    HEARING = "hearing", _("开庭")
    ASSET_PRESERVATION = "asset_preservation", _("财产保全")
    EVIDENCE_DEADLINE = "evidence_deadline", _("举证期限")
    STATUTE_LIMITATIONS = "statute_limitations", _("时效")
    APPEAL_PERIOD = "appeal_period", _("上诉期")
    OTHER = "other", _("其他")


class ChatPlatform(models.TextChoices):
    """群聊平台枚举"""
    FEISHU = 'feishu', _('飞书')
    DINGTALK = 'dingtalk', _('钉钉')
    WECHAT_WORK = 'wechat_work', _('企业微信')
    TELEGRAM = 'telegram', _('Telegram')
    SLACK = 'slack', _('Slack')


