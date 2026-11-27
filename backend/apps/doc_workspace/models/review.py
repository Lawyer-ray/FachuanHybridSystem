"""以「项目文件夹里的那一份文件」为坐标的审查模型。

## 为什么不是 `ReviewTask`

旧模型是「一次上传 → 一个任务 → 一份产物 docx」。它与文件夹里那份文件**没有任何
关系**：律师在文件夹里改完它不知道，一次审查的结果挂不回文件，想审第二次必须
再上传一次。于是「AI 审查」永远活在另一个页面里。

这里的坐标直接沿用 `ContractWritePatch` / `DocSnapshot` 已经在用的三元组：

    (owner_kind, owner_id, subpath)

审查、修订、版本快照、裁决全在同一个坐标系里，不需要任何映射。
**审查不产生第二份 docx**——结论要么是修订、要么是批注，都落在原文件上。

## 三个正交维度，不要挤成一列

| 维度 | 取值 | 回答的问题 |
|---|---|---|
| `verdict` | compliant / deviation / missing / not-applicable | 这条**该不该改** |
| `severity` | high / medium / low | **不改会亏多少** |
| `kind` | risk / typo / format / manual | **这是哪一类活** |

「偏离我方标准但后果轻微」和「完全符合标准但后果严重」的正确动作完全不同
（谈 vs 改）。挤进一个 `severity` 就表达不了。

`not-applicable` 单独存在的意义：它把覆盖率从糊涂账变成可算的分数。
分母 = 适用条款数，分子 = 已满足数。没有这一档，一份只有 6 条可审条款的框架协议
会被算成「47 条标准里满足 6 条 = 12 分」。
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.db import models


class RunStatus(models.TextChoices):
    QUEUED = "queued", "排队中"
    RUNNING = "running", "审查中"
    DONE = "done", "已完成"
    FAILED = "failed", "失败"
    SUPERSEDED = "superseded", "已被新一轮取代"


class Verdict(models.TextChoices):
    COMPLIANT = "compliant", "符合"
    DEVIATION = "deviation", "偏离"
    MISSING = "missing", "缺失"
    NOT_APPLICABLE = "not_applicable", "不适用"


class Severity(models.TextChoices):
    HIGH = "high", "高"
    MEDIUM = "medium", "中"
    LOW = "low", "低"


class FindingKind(models.TextChoices):
    RISK = "risk", "风险"
    TYPO = "typo", "错别字"
    FORMAT = "format", "格式"
    MANUAL = "manual", "人工痕迹"


class Delivery(models.TextChoices):
    """这条结论用哪种载体交付。"""

    REVISION = "revision", "修订痕迹"
    COMMENT = "comment", "批注"
    BOTH = "both", "修订 + 批注"
    LIST_ONLY = "list_only", "只进清单"


class FindingStatus(models.TextChoices):
    """结论的生命周期。

    `stale` / `moot` / `merged` / `unanchored` 四个态不加，必然出现：
    律师边改边审，清单里出现「建议把 X 改成 Y」而 X 早就没了 → 点「定位」跳到
    空白处 → 信任损毁只发生一次。
    """

    PROPOSED = "proposed", "待决"
    ACCEPTED = "accepted", "已采纳"
    REJECTED = "rejected", "已驳回"
    STALE = "stale", "锚点失效"
    MOOT = "moot", "已被消解"
    MERGED = "merged", "已合并"
    UNANCHORED = "unanchored", "锚不到"


class RejectReason(models.TextChoices):
    """驳回理由**必须是理由码**，不是自由文本。

    自由文本永远没法统计：误报率、同类条款降权、给客户的「评估 47 条采纳 31 条」
    全都算不出来。
    """

    COMMERCIAL = "commercial", "商业让步"
    JURISDICTION = "jurisdiction", "法域不适"
    ALREADY_COVERED = "already_covered", "已被其他条款覆盖"
    FALSE_POSITIVE = "false_positive", "误报"
    CLIENT_REFUSED = "client_refused", "客户明确拒绝"
    OTHER = "other", "其他"


class Stance(models.TextChoices):
    PARTY_A = "party_a", "代表甲方"
    PARTY_B = "party_b", "代表乙方"
    NEUTRAL = "neutral", "中立复核"


class Jurisdiction(models.TextChoices):
    """审查依据的**法域**（不是当事人国籍，也不是合同语言）。

    为什么必须有这一维：标准库的每条检查项都带 `legal_basis`（`《民法典》第470条`）。
    拿一套中国法标准去审一份泰国土地租赁合同，产出的是**双重错误**：

    1. 漏判——泰国法真正的硬约束（Land Code 第 86 条禁止外国人持地、
       CCC 第 540 条不动产租赁上限 30 年）不在标准库里，一条都不会报；
    2. 错判——按中国法口径要求「统一社会信用代码」「不动产登记」这类中国特有的
       形式要件，给出一堆在泰国根本不成立的结论，律师还得逐条删除。

    法域是**独立于 `contract_type`** 的维度：同一份不动产租赁，中国法与泰国法
    是两套完全不同的强制规则；同一法域下买卖/租赁/服务又是不同的条款集合。
    挤进 `contract_type`（如「泰国土地租赁」）会让路由退化成字符串匹配，
    而「按法域查域外法条文」这件事就没地方挂了。

    取值与 BARLC（西南政法大学东盟域外法查明库）的国别一致，
    映射表见 `services/foreign_law.py` 的 `BARLC_COUNTRY_CODE`。

    **东帝汶（TL）在 BARLC 里没有可用数据**，也没有标准库分册：选中它只会跑
    「引用完整性」那三条规则。这是刻意的——给一套「看着像」的标准，比明说
    「本国无标准库」危险得多。
    """

    CN = "CN", "中国"
    TH = "TH", "泰国"
    VN = "VN", "越南"
    MY = "MY", "马来西亚"
    SG = "SG", "新加坡"
    ID = "ID", "印度尼西亚"
    PH = "PH", "菲律宾"
    LA = "LA", "老挝"
    KH = "KH", "柬埔寨"
    MM = "MM", "缅甸"
    BN = "BN", "文莱"
    TL = "TL", "东帝汶"

    @classmethod
    def oversea_values(cls) -> list[str]:
        """需要域外法查明的法域（除中国外，都是 BARLC 可查的东盟国家）。"""
        return [value for value in cls.values if value != cls.CN]


class RuleClass(models.TextChoices):
    """规则的**类别**——决定「违反之后会怎样」，也就决定律师必须做什么。

    这个维度是法务总的「第五元规则扫描」教出来的，而且它堵住了我们模型里的一个
    真实漏判路径：

    | 类别 | 违反后果 | 正确动作 |
    |---|---|---|
    | mandatory（强制性） | 可能**无效 / 不得对抗第三人 / 行政处罚** | **必须改**，没得谈 |
    | contractual（契约性） | 违约、赔偿 | 可以谈，属于商业判断 |
    | inherited（承继性） | 义务随标的一起转过来，漏了就替前人背债 | 必须核清上游合同 |
    | procedural（程序性） | 办不成事（过户卡住、登记被退） | 必须补齐材料与顺序 |

    **`mandatory` 是免疫的**：它不因立场对齐而降档，也不被过度审查的条数闸丢弃
    （见 `review_pipeline.align_to_stance` / `enforce_gates`）。把「抵押未解除不得
    转让」当成一条可谈的商业建议，等于让清单漏掉「合同无效」级别的风险。
    """

    MANDATORY = "mandatory", "强制性"
    CONTRACTUAL = "contractual", "契约性"
    INHERITED = "inherited", "承继性"
    PROCEDURAL = "procedural", "程序性"


class Stage(models.TextChoices):
    """这笔交易处在哪个阶段。

    「转让前 / 转让中 / 转让后」是律师的工作节奏：先查能不能转，再谈怎么付，
    最后管交割后谁背什么。清单按阶段组织有两个好处：

    1. 律师是按这个顺序干活的，不是按严重度从高到低干；
    2. **某阶段零结论本身就是结论**——证明「这一段查过了」，而不是「AI 忘了」。
       所以 `run.summary["stages"]` 四个键永远都在，零也写出来。
    """

    BEFORE = "before", "转让前"
    DURING = "during", "转让中"
    AFTER = "after", "转让后"
    GENERAL = "general", "通用"


class RiskSource(models.TextChoices):
    """这条结论的风险是**从哪一维发现的**（法务总图中的「四维勘探」）。

    只有 `statute` 是可以靠标准库穷举的；另外三维必须换手段（检索案例、推演流程、
    抽取标的特征）。标出来是为了让律师判断成色：法条硬约束 vs 情景假设，
    复核成本完全不同。
    """

    STATUTE = "statute", "法律规定"
    CASE = "case", "案例检索"
    SCENARIO = "scenario", "场景推演"
    SUBJECT = "subject", "标的特性"


class Consequence(models.TextChoices):
    """违反这条规则之后，**法律上会发生什么**。

    `rule_class` 只说「必须改还是可以谈」，这一档说的是「不改到底会怎样」——
    法务总的四类规则里，强制性与程序性内部还各分几档，混成一档会让两种都失真：

    - `invalid`（可能无效）：合同/条款效力被否定，任何一方与利害关系人都可主张；
    - `unenforceable`（不得对抗第三人）：合同可能有效，但对抗不了抵押权人/共有人；
    - `uneffective`（未生效）：需批准/登记而未经批准的「未生效」，可补正；
    - `administrative`（处罚/登记受阻）：合同仍有效，但办不下来或被罚；
    - `breach`（违约责任）：只是赔钱，属于商业判断区。

    把「承租人优先购买权被妨害 = 只能索赔」写成「无效」是**过度定性**
    （客户会据此砍价或拒签）；把「集体土地擅自入市 = 无效」写成「行政处罚」
    是**漏判**。两种都真实存在过。
    """

    INVALID = "invalid", "可能无效"
    UNENFORCEABLE = "unenforceable", "不得对抗第三人"
    UNEFFECTIVE = "uneffective", "未生效（需批准/补正）"
    ADMINISTRATIVE = "administrative", "处罚/登记受阻"
    BREACH = "breach", "违约责任"


class SourceWeight(models.TextChoices):
    """在「条款的出生证明」里，这个来源是**核心**还是**辅助**。"""

    CORE = "core", "核心来源"
    SUPPORTING = "supporting", "辅助来源"


class ReviewRun(models.Model):
    """一次审查动作（不是一份文档副本）。"""

    id: int

    owner_kind: Any = models.CharField(
        "所属文件夹类型", max_length=16, choices=[("contract", "合同"), ("case", "案件")], db_index=True
    )
    owner_id: Any = models.IntegerField("所属合同/案件 ID", db_index=True)
    subpath: Any = models.CharField("文件夹内相对路径（posix）", max_length=1000)

    content_sha256: Any = models.CharField(
        "被审内容的 sha256",
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text="与 DocSnapshot.sha256 对齐；不一致说明审的不是当前这一版",
    )
    base_snapshot_seq: Any = models.IntegerField("起始快照号", null=True, blank=True)

    contract_type: Any = models.CharField("合同类型（决定用哪套标准）", max_length=64, blank=True, default="")
    jurisdiction: Any = models.CharField(
        "审查法域",
        max_length=8,
        choices=Jurisdiction.choices,
        default=Jurisdiction.CN,
        db_index=True,
        help_text="决定用哪国法作标准；非中国法域会触发域外法查明（BARLC）",
    )
    stance: Any = models.CharField("立场", max_length=16, choices=Stance.choices, default=Stance.NEUTRAL)
    playbook_key: Any = models.CharField("采用的标准库", max_length=120, blank=True, default="")
    playbook_version: Any = models.IntegerField("标准库版本", null=True, blank=True)
    playbook_snapshot: Any = models.JSONField(
        "标准快照",
        default=list,
        blank=True,
        help_text="本次实际用的规则快照；标准改版后仍能解释「当时为什么这么判」",
    )

    status: Any = models.CharField(
        "状态", max_length=16, choices=RunStatus.choices, default=RunStatus.QUEUED, db_index=True
    )
    parent_run: Any = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reruns",
        verbose_name="上一轮（delta 再审查时指回去）",
    )
    summary: Any = models.JSONField("汇总（覆盖率 / 条数 / Top-3）", default=dict, blank=True)
    error_message: Any = models.TextField("失败原因", blank=True, default="")

    created_by_id: Any = models.IntegerField("发起人 user id", null=True, blank=True)
    created_at: Any = models.DateTimeField("创建时间", auto_now_add=True, db_index=True)
    finished_at: Any = models.DateTimeField("完成时间", null=True, blank=True)

    class Meta:
        verbose_name = "审查轮次"
        verbose_name_plural = "审查轮次"
        ordering = ["-created_at", "-id"]
        indexes: ClassVar[list[Any]] = [models.Index(fields=["owner_kind", "owner_id", "subpath", "created_at"])]

    def __str__(self) -> str:
        return f"{self.owner_kind}/{self.owner_id}/{self.subpath} run#{self.id} {self.status}"


class Finding(models.Model):
    """一条审查结论。"""

    id: int

    run: Any = models.ForeignKey(ReviewRun, on_delete=models.CASCADE, related_name="findings", verbose_name="审查轮次")
    ordinal: Any = models.IntegerField("本轮内序号", default=0)

    verdict: Any = models.CharField("结论", max_length=16, choices=Verdict.choices, default=Verdict.DEVIATION)
    severity: Any = models.CharField("严重度", max_length=8, choices=Severity.choices, default=Severity.MEDIUM)
    kind: Any = models.CharField("类型", max_length=8, choices=FindingKind.choices, default=FindingKind.RISK)
    clause_type: Any = models.CharField("条款类型", max_length=64, blank=True, default="")

    rule_key: Any = models.CharField("违反的标准条款", max_length=120, blank=True, default="")
    rule_class: Any = models.CharField(
        "规则类别", max_length=16, choices=RuleClass.choices, default=RuleClass.CONTRACTUAL
    )
    stage: Any = models.CharField("阶段", max_length=16, choices=Stage.choices, default=Stage.GENERAL)
    risk_source: Any = models.CharField(
        "风险来源", max_length=16, choices=RiskSource.choices, default=RiskSource.STATUTE
    )
    source_weight: Any = models.CharField(
        "来源权重", max_length=16, choices=SourceWeight.choices, default=SourceWeight.CORE
    )
    consequence: Any = models.CharField(
        "违反后果档位", max_length=16, choices=Consequence.choices, default=Consequence.BREACH
    )
    case_ref: Any = models.CharField(
        "类案案号（risk_source=case 时必须能回指）",
        max_length=255,
        blank=True,
        default="",
        help_text="没有案号却声称『据类案』的结论会被降为辅助来源——编案号比不提类案严重得多",
    )
    legal_basis: Any = models.CharField("法律依据", max_length=255, blank=True, default="")

    quote: Any = models.TextField("被审原文", blank=True, default="")
    title: Any = models.CharField("一句话结论", max_length=200, blank=True, default="")
    reason: Any = models.TextField("理由（给律师看的）", blank=True, default="")

    suggestion_original: Any = models.TextField("要替换的原文", blank=True, default="")
    suggestion_replacement: Any = models.TextField("改写后的文本", blank=True, default="")
    suggestion_note: Any = models.TextField("批注正文（delivery 含 comment 时用）", blank=True, default="")

    delivery: Any = models.CharField("交付载体", max_length=12, choices=Delivery.choices, default=Delivery.REVISION)
    status: Any = models.CharField(
        "决策状态", max_length=12, choices=FindingStatus.choices, default=FindingStatus.PROPOSED, db_index=True
    )

    reject_reason_code: Any = models.CharField(
        "驳回理由码", max_length=24, choices=RejectReason.choices, blank=True, default=""
    )
    reject_note: Any = models.CharField("驳回补充说明", max_length=255, blank=True, default="")
    decided_by_id: Any = models.IntegerField("裁决人 user id", null=True, blank=True)
    decided_at: Any = models.DateTimeField("裁决时间", null=True, blank=True)

    docx_rev_ids: Any = models.JSONField("落笔写入的修订号", default=list, blank=True)
    comment_ids: Any = models.JSONField("落笔写入的批注号", default=list, blank=True)

    created_at: Any = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "审查结论"
        verbose_name_plural = "审查结论"
        ordering = ["run_id", "ordinal", "id"]
        indexes: ClassVar[list[Any]] = [models.Index(fields=["status", "severity"])]

    def __str__(self) -> str:
        return f"finding#{self.id} {self.verdict}/{self.severity} {self.title[:20]}"
