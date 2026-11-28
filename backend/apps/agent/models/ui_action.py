"""Agent UI 动作审计表：``confirm`` / ``guarded`` 档动作的派发与回执留痕。

## 为什么只有 confirm / guarded 落库，safe 不落

一次对话里 ``safe`` 动作（跳页、开面板、切筛选）能连发五六条，而它们**没有任何业务
副作用**：写下来只会让表随对话线性膨胀，事后追责要查的永远是「这一次写库 / 上传是谁
点的头」。所以写入口（``services/ui_action/audit.reserve_dispatch``）自己按 ``risk``
挡掉 safe——调用方不可能漏判。

## 为什么「同一动作同参数只允许一个在飞」是数据库约束，而不是下发前的一次查询

下发前「查一眼台账」挡不住两个 worker 同时下发同一条动作：两边都查空，于是同一个写库
被执行两遍。判据因此交给数据库：:class:`Meta` 里的 ``constraints`` 声明了一条**部分**
唯一索引 ``(session, action, arguments_hash) WHERE outcome='unknown'``，一次 ``acreate``
就是占位，冲突（``IntegrityError``）就是「已经有一条在飞」（见
``services/ui_action/audit.reserve_dispatch``）。三个取舍写在这里，免得后来人把索引改坏：

- **为什么是部分索引而不是全表唯一**：全表唯一会让「同一个材料包判过 done」永远不能再
  判一次——而同一动作本来就可以合法地做很多遍（律师改主意、换目标、先判错再纠正）。
  加上 ``outcome='unknown'`` 这个条件之后，一结算（``ok`` / ``error`` / ``denied`` /
  ``aborted`` / ``expired`` 任一）索引项就消失：约束只约束「在飞」，不约束历史。
- **为什么键里不放 ``call_id``**：``call_id`` 每次下发都现场生成（``uuid.uuid4().hex``），
  放进唯一键等于每条都不同——约束永远成立，也就永远没用。
- **为什么没有会话时约束不生效**：``session`` 可为 NULL（后台任务 / 未挂会话的直连
  调用），而 PostgreSQL 的唯一索引默认是 ``NULLS DISTINCT``——两个 NULL 互不相等，
  所以 NULL 会话的行一条都进不了这棵索引。这一点是可接受的：没有会话的下发本来就没有
  可竞争的上下文（同一页面对应一个会话），而给这些行编一个假会话只会让审计撒谎。
  也正因如此，「同一键只有一条在飞」只在有会话时成立，测试要分别覆盖两种情形。

## 为什么 ``outcome`` 默认 ``unknown`` 而不是 ``ok``

回执可能**永远不到**（页面没打开、律师切走了、前端崩了）。这张表的读者是事后审计
（「这个动作到底成了没有」）与动作历史列表。默认值定成 ``ok`` 等于把所有「没回执」
在报表里写成「成功」——法律场景里这是最不能出的错。``unknown`` 才是唯一诚实的答案：
我们发了，但我们不知道。

## 为什么 ``decision`` 和 ``outcome`` 是两件事，不能合成一列

两列回答的是**两个不同主体**的问题：

- ``decision`` = **人**（或超时机制）对「要不要做」的判定：``approved`` / ``denied`` /
  ``expired``；
- ``outcome`` = **页面**对「做成了没有」的回报：``unknown`` / ``ok`` / ``error`` /
  ``aborted`` / ``denied`` / ``expired``。

合成一列的直接后果是「律师拒绝了」和「页面执行失败」在报表里长得一样，而这两件事
的处理方式完全相反：前者是「他明确不要，别再问」，后者是「可以换个方式重试」。
本表因此把「谁批的」与「做成了没有」分开记——只有 ``denied`` / ``expired`` 这两种
**没有执行过**的结局会在两列里同时出现（``outcome`` 也要落一次，否则「拒绝了几个」
这类查询就得先 join 一列可能为空的决策），但它们的语义仍然由 ``decision`` 定义。

## 为什么 ``verified`` 允许为空（``None``）

``verified`` 记的是**服务端**自己去看了一眼库之后的结论（见
``services/ui_action/verify.py``）。把它做成 ``BooleanField(default=False)`` 是错的口径：
「我核实了，库里没变」和「我根本没法核实」（材料包不存在、核实器没登记、核实过程里
数据库报错）是两件完全不同的事。前者要求模型对律师说「没成功」，后者只允许说
「页面回执说成功，但服务端没核实到」——而 ``False`` 会把后者也说成「假成功」，
``True`` 会把前者说成真成功。两种都是法律场景里不能出的错，所以 ``None`` 必须
作为一个**合法答案**存在，而不是被当成 ``False`` 的别名。
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from .approval import AgentApproval
from .session import AgentSession


class AgentUiAction(models.Model):
    """一次 UI 动作的审计行（派发/被拒时写入，之后就地更新）。

    写入方只有三处，全部走 ``services/ui_action/audit.py``：

    1. :func:`audit.reserve_dispatch` —— **下发前**插一行占位（``outcome="unknown"``），
       并由 ``Meta.constraints`` 的部分唯一索引保证同键只有一条在飞；
    2. :func:`audit.record_denial` —— 审批未通过时插一行（``outcome`` 与 ``decision``
       都是 ``denied``）——被拒绝的审批也是一条必须留痕的事实：事后要能回答
       「他明确拒绝过什么」；
    3. :func:`audit.apply_receipt` / :func:`audit.apply_verification` —— 回执与核实结论
       到达后按 ``call_id`` 就地更新，且**只能改一次**（终态不可变）。

    行数 ≠ 执行次数，它只说明「系统发出了（或拦下了）这个动作」，结局看 ``outcome``
    与 ``verified``。
    """

    #: 派发时生成的 32 位十六进制 id（``publish_ui_action`` 的 ``call_id``）。
    #: 回执按它定位那一行，所以必须唯一；唯一约束自带索引，见 :class:`Meta`。
    call_id = models.CharField(max_length=64, unique=True, verbose_name="动作调用标识")
    session = models.ForeignKey(
        AgentSession,
        on_delete=models.CASCADE,
        related_name="ui_actions",
        null=True,
        blank=True,
        verbose_name="所属会话",
    )
    #: 动作所属用户（由会话推得）。不与会话级联删除：会话被清掉后审计仍要能回答
    #: 「谁让 AI 干过这件事」，所以是 SET_NULL 而不是 CASCADE。
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="agent_ui_actions",
        null=True,
        blank=True,
        verbose_name="所属用户",
    )
    action = models.CharField(max_length=64, verbose_name="动作名")
    #: 下发给页面的参数（写库前经 ``audit.sanitize_arguments`` 脱敏，与快照同口径）。
    arguments = models.JSONField(default=dict, blank=True, verbose_name="动作参数")
    #: 批准的是哪一份参数（``audit.arguments_hash_of`` 的 sha256 hexdigest）。
    #: 存在的理由只有一个：防「批 A 执行 B」——只记批准人与动作名时，同一个动作换个
    #: 参数（改另一条记录、改另一个材料包）在台账上与批准过的那次长得一模一样。
    arguments_hash = models.CharField(max_length=64, blank=True, default="", verbose_name="参数哈希")
    #: 风险档（``confirm`` / ``guarded``；``safe`` 不入库，见模块 docstring）。
    risk = models.CharField(max_length=16, verbose_name="风险档")
    #: 放行这次动作的审批人。best-effort 关联（见 ``audit.reserve_dispatch``）：
    #: 找不到审批行就留空，**不要**因此拒写审计——下发已经发生，那是事实。
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="agent_ui_actions_approved",
        null=True,
        blank=True,
        verbose_name="批准人",
    )
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name="批准时间")
    #: 放行/驳回这次动作的审批单（不是 best-effort 猜出来的那一条，而是按 approval_id
    #: 精确关联的那张卡）。为空 = 这条动作没有对应的审批单（后台任务 / 免审批路径）。
    approval = models.ForeignKey(
        AgentApproval,
        on_delete=models.SET_NULL,
        related_name="ui_actions",
        null=True,
        blank=True,
        verbose_name="关联审批单",
    )
    #: 人对「要不要做」的判定：``approved`` / ``denied`` / ``expired``，空串 = 还没判定。
    #: 与 ``outcome`` 是两个主体的问题，见模块 docstring。
    decision = models.CharField(max_length=16, blank=True, default="", verbose_name="审批决定")
    #: 决定理由：律师写下的驳回理由，或系统给的原因（如「晚于回执窗口到达」）。
    decision_note = models.CharField(max_length=300, blank=True, default="", verbose_name="决定理由")
    decided_at = models.DateTimeField(null=True, blank=True, verbose_name="决定时间")
    #: 回执窗口的截止时间（``audit.RECEIPT_TTL``）。过期后这一行的结果**不许**再被改写，
    #: 迟到的回执只能把它落成 ``expired``（见 ``audit.apply_receipt``）。
    expires_at = models.DateTimeField(null=True, blank=True, verbose_name="回执截止时间")
    #: 批量下发（``services/ui_action/batch.py``）的批次身份；单步动作为空串。
    batch_id = models.CharField(max_length=64, blank=True, default="", verbose_name="批次标识")
    #: 是否有页面在收听（``publish_ui_action`` 的 ``delivered`` 口径）。
    #: 与 ``outcome`` 分开记：没送达的动作也可能收到回执（律师刚好刷新打开了页面）。
    delivered = models.BooleanField(default=False, verbose_name="已送达")
    #: 页面回执的真实结局：``ok`` / ``error`` / ``aborted``（页面回传），``denied`` /
    #: ``expired``（从未执行，由 ``decision`` 定义），默认 ``unknown``。
    outcome = models.CharField(max_length=16, default="unknown", verbose_name="执行结果")
    #: 失败原因码，只在 ``outcome="error"`` 时有值（别的结局带着它会被误读成故障）。
    error_code = models.CharField(max_length=32, blank=True, default="", verbose_name="失败原因码")
    #: 执行完成后页面的真实地址（``ok`` 时最能证明「页面到底在哪」）。
    observed_location = models.CharField(max_length=300, blank=True, default="", verbose_name="执行后地址")
    #: 服务端核实结论：``True`` 真成功 / ``False`` 页面报成功但库里没变 / ``None`` 无法核实。
    #: 三态而不是两态的理由见模块 docstring——「无法核实」是合法答案。
    verified = models.BooleanField(null=True, blank=True, verbose_name="服务端核实")
    #: 核实说明（核实器给的那句话：库里是什么、为什么核不了）。
    verify_note = models.CharField(max_length=300, blank=True, default="", verbose_name="核实说明")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "Agent UI 动作审计"
        verbose_name_plural = "Agent UI 动作审计"
        ordering = ["-created_at"]
        indexes = [
            # 只加这一条：``call_id`` 的 unique 约束本身就是一棵 B-tree 索引，回执按它定位
            # 已经够快；再叠一条 ``Index(fields=["call_id"])`` 只是同一棵索引的第二份拷贝
            # （每次写入多维护一份），所以这里**故意**不再声明。
            # 会话维度的索引服务「这个会话里 AI 干过什么」——按时间倒序扫最新几条。
            models.Index(fields=["session", "-created_at"], name="agent_uiaction_session_idx"),
        ]
        constraints = [
            # 服务端幂等的**唯一**真相：同一会话里，同一个动作 + 同一份参数最多一条
            # 「未结算」（``outcome="unknown"``）。用部分索引而不是全表唯一，是因为「同一
            # 动作同参数」可以合法地做很多遍（律师改主意），结算之后约束必须自然解除；
            # 键里不放 ``call_id``，因为它每次下发都不同（放进去等于没有约束）；
            # ``session`` 为 NULL 时 PostgreSQL 认为 NULL 互不相等，约束不生效
            # （没有会话的下发没有可竞争的上下文）——三条取舍的详细论证见模块 docstring。
            # 条件里的 ``"unknown"`` 与 ``audit.OUTCOME_UNKNOWN`` 同值：模型层不 import
            # 服务层（服务层已经 import 模型，反向会成环），所以改值时必须两处一起改。
            models.UniqueConstraint(
                fields=["session", "action", "arguments_hash"],
                condition=models.Q(outcome="unknown"),
                name="agent_uiaction_unsettled_uniq",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.action} [{self.outcome}]"
