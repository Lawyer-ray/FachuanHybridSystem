"""
共享枚举定义模块

本模块包含跨多个 Django app 使用的枚举类型，
避免跨模块直接导入 Model 造成的循环依赖问题。

使用方式:
    from apps.core.models.enums import CaseType, CaseStatus, CaseStage, LegalStatus
"""

from django.db import models


class CaseType(models.TextChoices):
    """案件类型"""

    CIVIL = "civil", "民商事"
    CRIMINAL = "criminal", "刑事"
    ADMINISTRATIVE = "administrative", "行政"
    LABOR = "labor", "劳动仲裁"
    INTL = "intl", "商事仲裁"
    SPECIAL = "special", "专项服务"
    ADVISOR = "advisor", "常法顾问"


class LegalStatus(models.TextChoices):
    """诉讼地位"""

    PLAINTIFF = "plaintiff", "原告"
    DEFENDANT = "defendant", "被告"
    THIRD = "third", "第三人"
    APPLICANT = "applicant", "申请人"
    RESPONDENT = "respondent", "被申请人"
    CRIMINAL_DEFENDANT = "criminal_defendant", "被告人"
    VICTIM = "victim", "被害人"
    APPELLANT = "appellant", "上诉人"
    APPELLEE = "appellee", "被上诉人"
    ORIGINAL_PLAINTIFF = "orig_plaintiff", "原审原告"
    ORIGINAL_DEFENDANT = "orig_defendant", "原审被告"
    ORIGINAL_THIRD = "orig_third", "原审第三人"


class CaseStatus(models.TextChoices):
    """案件状态"""

    ACTIVE = "active", "在办"
    CLOSED = "closed", "已结案"


class CaseStage(models.TextChoices):
    """案件阶段"""

    FIRST_TRIAL = "first_trial", "一审"
    SECOND_TRIAL = "second_trial", "二审"
    ENFORCEMENT = "enforcement", "执行"
    LABOR_ARBITRATION = "labor_arbitration", "劳动仲裁"
    ADMIN_REVIEW = "administrative_review", "行政复议"
    PRIVATE_PROSECUTION = "private_prosecution", "自诉"
    INVESTIGATION = "investigation", "侦查"
    PROSECUTION_REVIEW = "prosecution_review", "审查起诉"
    RETRIAL_FIRST = "retrial_first", "重审一审"
    RETRIAL_SECOND = "retrial_second", "重审二审"
    APPLY_RETRIAL = "apply_retrial", "申请再审"
    REHEARING_FIRST = "rehearing_first", "再审一审"
    REHEARING_SECOND = "rehearing_second", "再审二审"
    REVIEW = "review", "提审"
    DEATH_PENALTY_REVIEW = "death_penalty_review", "死刑复核程序"
    PETITION = "petition", "申诉"
    APPLY_PROTEST = "apply_protest", "申请抗诉"
    PETITION_PROTEST = "petition_protest", "申诉抗诉"


class AuthorityType(models.TextChoices):
    """主管机关性质"""

    INVESTIGATION = "investigation", "侦查机关"
    PROSECUTION = "prosecution", "审查起诉机关"
    TRIAL = "trial", "审理机构"
    DETENTION = "detention", "当前关押地点"


class ContactRole(models.TextChoices):
    """工作人员角色"""

    PRESIDING_JUDGE = "presiding_judge", "审判长"
    JUDGE = "judge", "审判员/法官"
    CLERK = "clerk", "书记员"
    JUDGE_ASSISTANT = "judge_assistant", "法官助理"
    PROSECUTOR = "prosecutor", "检察官"
    POLICE = "police", "警官"
    ARBITRATOR = "arbitrator", "仲裁员"
    MEDIATOR = "mediator", "调解员"
    OTHER = "other", "其他"


class SimpleCaseType(models.TextChoices):
    """案件类型（简化版）"""

    CIVIL = "civil", "民事"
    ADMINISTRATIVE = "administrative", "行政"
    CRIMINAL = "criminal", "刑事"
    EXECUTION = "execution", "申请执行"
    BANKRUPTCY = "bankruptcy", "破产"


class CaseLogReminderType(models.TextChoices):
    """案件日志提醒类型"""

    HEARING = "hearing", "开庭"
    ASSET_PRESERVATION = "asset_preservation", "财产保全"
    EVIDENCE_DEADLINE = "evidence_deadline", "举证期限"
    STATUTE_LIMITATIONS = "statute_limitations", "时效"
    APPEAL_PERIOD = "appeal_period", "上诉期"
    OTHER = "other", "其他"


class ChatPlatform(models.TextChoices):
    """群聊平台枚举"""

    FEISHU = "feishu", "飞书"
    DINGTALK = "dingtalk", "钉钉"
    WECHAT_WORK = "wechat_work", "企业微信"
    TELEGRAM = "telegram", "Telegram"
    SLACK = "slack", "Slack"
