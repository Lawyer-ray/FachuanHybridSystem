"""PDF 拆解任务的「卡死自救」机制。

## 为什么需要它

`qcluster` 在开发环境被 `watchfiles` 包裹（见 Makefile `qcluster-dev`）：只要有任何
`apps/ apiSystem/ plugins/` 下的 .py 变化，watchfiles 就 kill 掉整个 qcluster 子进程
并重启。正在跑的拆分任务随即消失，**但数据库里的 job 仍停在 `processing`**——
没有异常、没有日志、没有 error_message。曾有一次 164 页的真实卷宗任务卡在
135/164 二十余分钟，前端只是不停地转圈，律师完全无从判断。

生产环境同样会死：worker 被 OOM killer 杀掉、部署重启、机器断电。区别只是频率。

## 判活口径（第一判据：心跳）

| 字段 | 谁写 | 用途 |
|:--|:--|:--|
| `heartbeat_at` | worker 每处理一批页 | **唯一可信的存活信号** |
| `updated_at` | 任何 `save()`；进度回写现在显式写 | 兜底（老数据无 heartbeat） |
| `started_at` | 创建任务时写一次 | 判「从未开始」 |

判据：`processing` 状态下，`now - max(heartbeat_at, updated_at) > STALE_SECONDS`，
即视为 worker 已死。阈值必须显著大于进度回写间隔，否则会把慢任务误判为死任务。

## 第二判据：阶段硬超时（**可证明已死**，见 `explain_staleness`）

第一判据有个天花板：它只能等满 `STALE_SECONDS`（30 分钟），因为「安静」本身
证明不了死亡——活着的任务在长阻塞段里也可能几十秒不写库。但有一类死亡是
**可以证明**的：任务被 django-q 按阶段硬超时杀掉。

2026-11-20 的真实事故（一份 93 页卷宗的取字任务，作业号略；`extract` 预算 1200s）：

```
11:43  PaddleOCR 连续 8 次单页超时（每次 300s）
11:58  恢复，页面跑到 93/93（progress=100）
12:00:43  django-q 硬超时杀 worker：
          TimeoutException: Task exceeded maximum timeout value (1200 seconds)
此后   job 行 status=processing / stage=extract / progress=100 / 心跳停在 11:58:56
前端   进度条 100% 但永远不动（比显示失败更误导）
恢复   旧判据要等到 12:28:56，加上每 5 分钟的扫描间隔 ≈ 12:29~12:34 才重排
```

（`extract` 的预算后来又调大过，见 `two_stage.py` 的当前值。本模块的映射是 import
那批常量而不是抄数字（见 `default_stage_timeouts`），所以预算一改，判死阈值自动
跟着走；上面的 1200s 只是那次事故当时的现场数字。）

`tasks.py` 里那句 `except Exception → two_stage.mark_stage_failed(...)` 救不了它：
硬超时是把 worker 进程销毁，异常在 worker 的帧里抛出/或者进程直接被 terminate，
任务函数自己的 `except` 拿不到这一次机会（本次事故行上 error_message 为空即为证）。
`task_result_logging.py` 里那句「任务失败（外部环境不可用，可重试）」只是 logging
filter 改写 django-q 自己的日志，**不是信号回调**，没有 Python 侧钩子可用。

所以本模块加一条**独立的**判死依据，而不是把 `STALE_SECONDS` 调小（调小会误杀
正经在跑的慢任务，代价是整本卷宗重付一次云端费用）：

> `processing` 且 `now - 最后活动 > 该阶段硬超时 + 余量`
> ⇒ django-q 一定已经把它杀了 ⇒ 行上的 `processing` 是残留。

## 重排代价：pages.json 的落盘时机（**已核实**）

重排会不会「把云端费用再付一次」，取决于该阶段的中间产物是否已落盘：

| 阶段 | 产物 | 落盘时机 | 被硬杀后重排的代价 |
|:--|:--|:--|:--|
| `extract` | `pages.json` | `tasks.py::run_extract_stage` 里 **`extract_stage()` 整段返回之后** | pages.json 不存在 → 重排从头跑取字 |
| `extract` | 逐页 OCR 缓存 | `pipeline._resolve_pending_pages` 每批完成即写 | 已 OCR 完的页命中缓存，**不重复计费** |
| `cross_check` | `engine_disagreements.json` | `cross_check_stage()` 返回后 | 重排重跑双引擎（整本再解析两遍） |
| `segment` | 分段行（DB）+ `segments.json` | 分段计算完之后 | 重排重跑 LLM 分段（云端按 token 计费） |

本次事故正是被硬杀在 `save_pages` 之前，所以 `pages.json` **没有**落盘：重排必然
重跑一遍取字。乐观的部分是逐页 OCR 缓存已经逐批写过了，所以重复计费只发生在
「还没落进缓存的那几页」；但那正是本次超时的那 8 页本地 OCR——重排后它们会被
重新尝试，**有机会再次把 1200s 预算烧完**（这也是 `MAX_RECOVERY_ATTEMPTS` 存在的
理由：第二次死在同一处就该停下来让人介入，而不是继续重排）。

## 三种收尾动作（按顺序尝试）

1. **可恢复 → 重排队**：Worker 死了但活没干完（`segments` 为空），直接按当前阶段
   重新 `submit`。这条路最理想：律师什么都不用做。
2. **已有部分成果 → 转待复核**：`segments` 里有东西说明识别结果已落库，
   只是没走完收尾。**不重跑**（164 页重跑一次很贵），直接标 `review_required`，
   让律师基于已有分段继续——分段少几段也比从零开始好。
3. **反复失败 → 标记失败**：`recovery_attempts >= MAX_RECOVERY_ATTEMPTS`，
   停止自动重排（防死循环打满队列），明确写 `error_message` 让人介入。

判死原因（`StalenessVerdict.describe()`）会一并写进 `error_message` 与日志：
「网络断了」和「云端 OCR 太慢把预算烧完了」在运维眼里必须是两件不同的事。

## 为什么不做「立刻重排」

如果 worker 是被某个坏输入打死的，立刻重排会等剂量地再死一次，还连累队列里
其他任务。所以重排次数有上限，且失败原因如实落库。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Mapping

from django.db.models import Q
from django.utils import timezone

from apps.core.dependencies.core import build_task_submission_service
from apps.pdf_splitting.models import PdfSplitJob, PdfSplitJobStatus, PdfSplitMode, PdfSplitStage

logger = logging.getLogger("apps.pdf_splitting")

#: 超过这个时长没有心跳，判定 worker 已死。
#:
#: 为什么从 600 放宽到 1800：在 164 页真实卷宗上，交叉比对（双引擎整本再解析
#: 一遍）+ LLM 分段合计会超过 10 分钟，600s 会把**正常在跑**的任务判死并重排，
#: 而重排等价于把整份卷宗的云端费用再付一次（实测 7da5d020 就卡在这条线上）。
#:
#: 既然心跳现在由后端主动刷新（`services/heartbeat.periodic_heartbeat` 每 15s，
#: 取字阶段每页刷），1800s 只是兜底而不是常态判据：真活着的任务远不会静默半小时，
#: 真死了的晚一点发现也只是多等一会儿，代价远小于误杀重排。
#:
#: ⚠️ 本值只管「第一判据（心跳）」。被 django-q 硬超时杀掉的任务由第二判据
#: （阶段硬超时 + 余量，见 `explain_staleness`）更早判死，**不要**为了缩短恢复
#: 时间去调小它——那会误杀正经在跑的长任务。
STALE_SECONDS = 1800

#: 「阶段硬超时」第二判据的余量（秒）。为什么需要余量，而不是「预算一到就判死」：
#:
#: · django-q 的 SIGALRM（`django_q/timeout.py::TimeoutHandler`）只在 worker 主线程
#:   正在执行 Python 字节码时才会送达。如果那一刻它卡在 fitz / PaddleOCR / psycopg
#:   这类 C 调用里，投递就要等到它下一次回到解释器——晚几秒甚至几十秒都正常；
#: · 兜底的是 guard 循环（`django_q/cluster.py::Sentinel.guard`）：worker 把
#:   `timer.value` 置成 `timeout + 3`，guard 每 `GUARD_CYCLE = 0.5s` 递减一次，
#:   减到 0 才 `process.terminate()`。而 guard 每一轮还要给**每个 worker** 写一条
#:   `Stat`、每 ~30s 跑一次 `scheduler()`（要查计划任务表），这些都会把
#:   「预算到 → terminate」之间再拉开若干秒；
#: · `terminate()`（SIGTERM）之后进程退出、心跳线程最后一拍落库的时间也在窗口里。
#:
#: 120s 覆盖上面全部抖动两个数量级还有余；同时又远小于「误判死亡后重跑一次云端
#: OCR」的代价（164 页实测十几分钟 + 一次完整云端费用）。刻意不取更小的 30s：
#: guard 跑一轮 scheduler 就可能吃掉十几秒，激进阈值会把活任务判死。
STAGE_DEAD_GRACE_SECONDS = 120

#: 判死依据。写进日志与 `error_message`，运维靠它区分「网络断了」与「云端太慢」。
REASON_HARD_TIMEOUT = "hard_timeout"
REASON_HEARTBEAT = "heartbeat_stale"
REASON_ALIVE = "alive"

#: `error_message` 的长度上限，与 `two_stage.mark_stage_failed` 的截断保持一致。
_ERROR_MESSAGE_LIMIT = 4000

#: 同一个任务最多自动重排几次。超过就停下报错，避免坏输入无限循环。
MAX_RECOVERY_ATTEMPTS = 2

#: 一次巡检最多处理多少个任务，防止首轮上线时一口气重排打满队列。
MAX_RECOVERY_PER_RUN = 5


def default_stage_timeouts() -> dict[str, int]:
    """各阶段提交给 django-q 的**硬超时**（秒）。单一真源是 `split/two_stage.py`。

    ## 为什么不在本模块另抄一份数字

    第二判据的正确性依赖一条不等式：``stage_timeouts[stage] >= 该阶段任务的真实 timeout``。
    真实 timeout 只有一个来源——`two_stage.py` 提交时传给 django-q 的那三个常量
    （`submit_extract_stage` / `submit_cross_check_stage` / `submit_segment_stage`），
    看门狗重排也走同一批（见 `_resume_task_for`）。

    在这里再抄一份数字，将来有人调大某阶段预算时就会静默漏改，后果是看门狗把
    **还在正常跑**的任务判死并重排——正好是这条判据最不能犯的错。所以这里选择
    import 而不是硬编码；新增阶段时只要在 `two_stage.py` 有提交常量，在这里登记一行即可。

    没有登记的阶段（含老数据的 `done`、空值）→ 调用方回落 `STALE_SECONDS`。
    """
    from apps.pdf_splitting.services.split.two_stage import (
        CROSS_CHECK_STAGE_TIMEOUT_SECONDS,
        EXTRACT_STAGE_TIMEOUT_SECONDS,
        SEGMENT_STAGE_TIMEOUT_SECONDS,
    )

    # 用枚举成员而不是裸字符串做键：阶段名写错时这条判据会静默失效，
    # 枚举至少有 IDE/类型检查兜一层。
    return {
        PdfSplitStage.EXTRACT: EXTRACT_STAGE_TIMEOUT_SECONDS,
        PdfSplitStage.CROSS_CHECK: CROSS_CHECK_STAGE_TIMEOUT_SECONDS,
        PdfSplitStage.SEGMENT: SEGMENT_STAGE_TIMEOUT_SECONDS,
    }


def _as_int(value: Any) -> int | None:
    """把进度类字段收敛成 int；拿不到（测试替身/脏数据）时返回 None。"""
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _silent_seconds(last: Any, now: Any) -> float | None:
    """最后活动距今多少秒；没有可信的时间字段时返回 None。"""
    if last is None:
        return None
    try:
        return float((now - last).total_seconds())
    except (TypeError, AttributeError):
        return None


@dataclass(frozen=True)
class StalenessVerdict:
    """一次判死结论：死没死、凭什么、当时的现场（阶段/预算/最后进度）。

    做成结构体而不是返回布尔的原因：判死之后要把「为什么判死」写进日志和
    `error_message`。事故复盘时只看到「心跳停了」是没用的——必须能看出
    「`stage=extract` 的 1200s 预算被云端 OCR 烧完了」。
    """

    dead: bool
    reason: str
    stage: str
    stage_budget_seconds: int | None
    threshold_seconds: float
    silent_seconds: float | None
    last_liveness: Any
    progress: int | None
    processed_pages: int | None
    total_pages: int | None

    def describe(self) -> str:
        """一句话说清判死依据与现场，同时也是运维面对的 `error_message` 前缀。"""
        bits: list[str] = []
        if self.processed_pages is not None and self.total_pages is not None:
            bits.append(f"最后进度 {self.processed_pages}/{self.total_pages} 页")
        if self.progress is not None:
            bits.append(f"progress={self.progress}%")
        if self.last_liveness is not None:
            bits.append(f"最后活动 {self.last_liveness}")
        tail = "，".join(bits)

        silent = "静默时长未知" if self.silent_seconds is None else f"已静默 {int(self.silent_seconds)}s"
        if self.reason == REASON_HARD_TIMEOUT:
            budget = int(self.stage_budget_seconds or 0)
            grace = int(self.threshold_seconds - budget)
            head = (
                f"硬超时终止（stage={self.stage}，预算 {budget}s + 余量 {grace}s；{silent}）："
                f"django-q 必已在 {budget}s 处销毁了 worker"
            )
        elif self.reason == REASON_ALIVE:
            head = f"仍在运行（{silent}，判死阈值 {int(self.threshold_seconds)}s）"
        else:
            head = f"心跳超时（{silent} > 阈值 {int(self.threshold_seconds)}s）"
        return f"{head}；{tail}" if tail else head


def _last_liveness(job: PdfSplitJob) -> Any:
    """任务最后的存活信号：心跳优先，退回 updated_at，再退回 started_at/created_at。"""
    candidates = [job.heartbeat_at, job.updated_at, job.started_at, job.created_at]
    return max((item for item in candidates if item is not None), default=None)


def _stage_budget_for(job: PdfSplitJob, stage_timeouts: Mapping[str, int]) -> int | None:
    """该任务当前阶段实际享有的 django-q 硬超时；拿不到就返回 None（回落旧判据）。

    两道闸门都是为了「绝不误杀」：

    1. 只有内容分析走阶段链（`job_service` 里 `CONTENT_ANALYSIS` 才提交
       `submit_extract_stage`，其它模式走单任务 `execute_pdf_split_job` + 集群默认
       `DJANGO_Q_TIMEOUT`）。手工/按页拆分任务的 `stage` 停在默认值 `extract`，
       并不代表它真有该阶段的预算——集群默认值可以被 `DJANGO_Q_TIMEOUT` 调得比
       某阶段的预算更大，那时套用阶段预算就会把**还在跑**的任务判死。所以这里显式排除。
    2. 阶段没有登记预算（老数据 `done`、空值、将来新增但还没登记的阶段）→ None。
    """
    if not stage_timeouts:
        return None
    if getattr(job, "split_mode", None) != PdfSplitMode.CONTENT_ANALYSIS:
        return None
    stage = getattr(job, "stage", "")
    if not isinstance(stage, str) or not stage:
        return None
    budget = stage_timeouts.get(stage)
    return budget if isinstance(budget, int) and budget > 0 else None


def explain_staleness(
    job: PdfSplitJob,
    *,
    now: Any = None,
    stale_seconds: int = STALE_SECONDS,
    stage_timeouts: Mapping[str, int] | None = None,
    grace_seconds: int = STAGE_DEAD_GRACE_SECONDS,
) -> StalenessVerdict:
    """判断一个 `processing` 任务是否**可证明已死**，并给出依据。

    Args:
        now: 测试注入的当前时刻；缺省 `timezone.now()`。
        stale_seconds: 第一判据（心跳）阈值。
        stage_timeouts: 阶段 → 硬超时映射。``None``（默认）= 用 `default_stage_timeouts()`；
            传 ``{}`` = 关闭第二判据，只看心跳（回落到改动前的行为）。
        grace_seconds: 第二判据的余量，见 `STAGE_DEAD_GRACE_SECONDS`。

    ## 判据的精确表达式

    记 ``L = max(heartbeat_at, updated_at, started_at, created_at)``（`_last_liveness`），
    ``silent = now - L``，``budget = stage_timeouts[job.stage]``：

    · 硬超时判死：``budget is not None and silent > budget + grace_seconds``
    · 心跳判死  ：``silent > stale_seconds``
    · 两者同时成立时报 `REASON_HARD_TIMEOUT`：信息量更大，且它本来就是更硬的证据。

    ## 为什么 `silent > budget + grace` 就等价于「必然已死」

    1. 该阶段的任务提交时带着 `timeout=budget`（`two_stage.py` 的三个提交函数，
       看门狗重排也用同一批常量），因此 django-q 不会让它活过 `budget + 3s`：
       SIGALRM 抛 `TimeoutException` 后 worker 自己把 `timer.value = 0`，
       guard 循环看到 0 就 `process.terminate()`；即使 SIGALRM 被卡在 C 调用里没送到，
       那个 `timer.value = budget + 3` 也会被 guard 逐 cycle 递减到 0 并同样 terminate。
    2. `L` 必然 ≤ 该任务开始之后的某个时刻，所以 ``silent = now - L >= now - 任务开始``。
       于是 ``silent > budget + grace`` ⇒ ``now - 任务开始 > budget + grace > budget + 3``
       ⇒ 那个任务早已被 django-q 销毁 ⇒ 行上的 `processing` 是残留。
    3. 反向不会误伤：活着的任务 `L` 最多 15s 前（`heartbeat.periodic_heartbeat` 每 15s，
       取字每页/每批也刷），远小于 `budget + grace`。

    第 2 步用 `L` 而不是 `started_at` 是刻意的：`started_at` 在重排时被改写成
    「入队时刻」，用它会高估已运行时长；而 `L` 一定晚于任务开始，用它只会**推迟**
    判死，永远不会提前——这就是这条判据的保守性来源。

    ## 唯一可能误杀的前提（所以必须守住）

    前提是「该 stage 实际运行的任务 timeout 不大于 `stage_timeouts[stage]`」。
    今天成立（所有提交点都取 `two_stage.py` 的常量，非内容分析任务已由
    `_stage_budget_for` 排除在判据之外）。将来若有人绕过 `two_stage.py` 给同一
    阶段塞一个更大的 timeout，就会把活任务判死——这也是 `default_stage_timeouts()`
    坚持 import 而不是抄数字的原因。

    ## 顺带说明：对哪些阶段其实没有提前

    `cross_check`（45min+余量）与 `segment`（35min+余量）都大于 `STALE_SECONDS = 1800`，
    所以那两个阶段新判据**不会**比旧判据更早触发（它的价值在那里只是「说清死因」）。
    真正提前的只有 `extract`：事故当时是 1200s 预算 → 1320s 判死，比 1800s 早 8 分钟
    （当前预算见 `two_stage.py`，阈值 = 预算 + `STAGE_DEAD_GRACE_SECONDS`）。
    而 `extract` 的 `processing` 只由正在跑的任务写（`service._begin_stage`），
    不存在「任务还在队列里排队」的窗口，所以提前这一段也不会误伤排队中的任务。

    ⚠️ 如果哪天 `extract` 预算被调大到「预算 + 余量 ≥ 1800s」，这条判据在 extract 上
    就不再提前（只剩归因价值）——那时要重新评估 `STALE_SECONDS` 与预算的关系，
    而不是往回改这条判据。
    """
    now = now or timezone.now()
    timeouts: Mapping[str, int] = default_stage_timeouts() if stage_timeouts is None else stage_timeouts
    last = _last_liveness(job)
    silent = _silent_seconds(last, now)
    raw_stage = getattr(job, "stage", "")
    stage = raw_stage if isinstance(raw_stage, str) else ""

    budget = _stage_budget_for(job, timeouts)
    threshold = float(stale_seconds)
    reason = REASON_ALIVE
    dead = False
    if silent is not None:
        if budget is not None and silent > budget + grace_seconds:
            threshold = float(budget + grace_seconds)
            reason = REASON_HARD_TIMEOUT
            dead = True
        elif silent > stale_seconds:
            reason = REASON_HEARTBEAT
            dead = True

    return StalenessVerdict(
        dead=dead,
        reason=reason,
        stage=stage,
        stage_budget_seconds=budget,
        threshold_seconds=threshold,
        silent_seconds=silent,
        last_liveness=last,
        progress=_as_int(getattr(job, "progress", None)),
        processed_pages=_as_int(getattr(job, "processed_pages", None)),
        total_pages=_as_int(getattr(job, "total_pages", None)),
    )


def find_stale_jobs(
    *,
    now: Any = None,
    stale_seconds: int = STALE_SECONDS,
    stage_timeouts: Mapping[str, int] | None = None,
    grace_seconds: int = STAGE_DEAD_GRACE_SECONDS,
) -> list[PdfSplitJob]:
    """列出「状态是 processing 但可证明已死」的任务。

    只查 `processing`：`pending` 是还没被 worker 捡起来（正常，尤其队列忙时），
    `review_required`/`completed`/`failed`/`cancelled` 都是终态或待人工，均不该动。

    判死口径见 `explain_staleness`（心跳 + 阶段硬超时两条判据取或）。
    `stage_timeouts` 缺省用当前阶段预算表；传 `{}` 可退回只按心跳判定。
    """
    now = now or timezone.now()
    threshold = now - timedelta(seconds=stale_seconds)

    # 这个 filter 的 OR 两边覆盖了全集（`updated_at < threshold` 或 `>= threshold`），
    # 是有意为之的**空筛选**：保留它是为了将来能安全改写成真正的粗筛。
    # 注意现在**不能**把阈值写进 SQL——第二判据的阈值是逐任务的（`budget + grace`），
    # 且对 `extract` 而言比 `stale_seconds` **更早**，用统一 SQL 阈值会漏掉要救的任务；
    # 而候选集本来就只有几十条（全表 processing 行），Python 精筛完全够用。
    candidates = PdfSplitJob.objects.filter(
        status=PdfSplitJobStatus.PROCESSING,
    ).filter(Q(updated_at__lt=threshold) | Q(updated_at__gte=threshold))

    stale: list[PdfSplitJob] = []
    for job in candidates:
        verdict = explain_staleness(
            job,
            now=now,
            stale_seconds=stale_seconds,
            stage_timeouts=stage_timeouts,
            grace_seconds=grace_seconds,
        )
        if verdict.dead:
            stale.append(job)
    return stale


def _resume_task_for(job: PdfSplitJob) -> tuple[str, str, int | None]:
    """按任务**当前阶段**决定从哪个任务入口续跑。

    返回 ``(任务路径, 任务名称, 该阶段的临时预算秒数)``。预算为 None 时表示用
    Django-Q 集群默认值（只有旧全量路径会落到这里）。

    ## 为什么不能一律用 `execute_pdf_split_job`

    那条是**旧全量路径**（`analyze_job` → `pipeline.analyze_pdf`），里面**不包含**
    `cross_check_stage`。于是双引擎任务一旦被重排，就会静默退化成单引擎——
    比对结果凭空消失，而律师那边看不出任何异常（任务照样跑完、照样出分段）。

    更糟的是旧路径本身就是为了绕开 600s 硬超时才被拆掉的：它把取字 + 分段
    挤在一次调用里，164 页实测跑到 499s 被杀。重排走回去等于等剂量地再死一次。

    ## 各阶段的正确续跑点

    | 任务当前阶段 | 续跑入口 | 理由 |
    |---|---|---|
    | `cross_check` | `run_cross_check_stage` | 取字产物已在 pages.json，只差比对 |
    | `segment` | `run_segment_stage` | 取字 + 比对都已落盘，只差分段 |
    | `extract` / 其它 | `run_extract_stage` | 从头取字（两阶段链路的正常起点） |

    非内容分析任务（手工拆分 / 按页拆分）仍走旧的全量入口——它们本来就是
    单一任务，没有阶段可复原。

    ## 为什么预算也要跟进来

    重排出来的任务如果不同时带上该阶段的 timeout，就会退回集群默认的 600s——
    等于「看门狗救回来的任务，比它原先那次更容易死」。重排的意义是让任务活着
    跑完，不是在 600s 处再杀它一次。
    """
    from apps.pdf_splitting.services.split.two_stage import (
        CROSS_CHECK_STAGE_TIMEOUT_SECONDS,
        EXTRACT_STAGE_TIMEOUT_SECONDS,
        SEGMENT_STAGE_TIMEOUT_SECONDS,
        TASK_CROSS_CHECK,
        TASK_EXTRACT,
        TASK_SEGMENT,
    )

    if job.split_mode != PdfSplitMode.CONTENT_ANALYSIS:
        return "apps.pdf_splitting.tasks.execute_pdf_split_job", f"pdf_split_{job.id}", None

    stage = getattr(job, "stage", PdfSplitStage.EXTRACT)
    if stage == PdfSplitStage.CROSS_CHECK:
        return TASK_CROSS_CHECK, f"pdf_split_cross_check_{job.id}", CROSS_CHECK_STAGE_TIMEOUT_SECONDS
    if stage == PdfSplitStage.SEGMENT:
        return TASK_SEGMENT, f"pdf_split_segment_{job.id}", SEGMENT_STAGE_TIMEOUT_SECONDS
    return TASK_EXTRACT, f"pdf_split_extract_{job.id}", EXTRACT_STAGE_TIMEOUT_SECONDS


def _compose_message(reason: str, body: str) -> str:
    """把判死原因拼在人工可读结论前面，并按 `error_message` 的上限截断。"""
    message = f"{reason}。{body}" if reason else body
    return message[:_ERROR_MESSAGE_LIMIT]


def _requeue(job: PdfSplitJob, *, reason: str = "") -> str:
    """重新提交任务。返回动作描述。

    入口按当前阶段选（见 `_resume_task_for`）：双引擎任务重排后**仍是双引擎**，
    不会静默退化成旧全量路径；预算也一并带上，不会退回集群默认值再被杀一次。

    `reason` 非空时写进 `error_message`——这是运维事后唯一还能看到的现场记录。
    它会自动消失：任务真正开跑时 `_begin_stage` / `analyze_job` 都会把
    `error_message` 清空，所以它只存在于「已重排、等 worker 捡起」这段窗口，
    不会长期挂在界面上吓人。
    """
    task_path, task_name, timeout = _resume_task_for(job)
    task_id = build_task_submission_service().submit(
        task_path,
        args=[str(job.id)],
        task_name=task_name,
        timeout=timeout,
    )
    now = timezone.now()
    attempt = job.recovery_attempts + 1
    note = ""
    if reason:
        note = _compose_message(
            reason,
            f"已自动重排续跑（第 {attempt} 次，入口 {task_path.rsplit('.', 1)[-1]}），无需人工介入。",
        )
    PdfSplitJob.objects.filter(id=job.id).update(
        status=PdfSplitJobStatus.PENDING,
        task_id=str(task_id),
        started_at=now,
        heartbeat_at=None,
        updated_at=now,
        error_message=note,
        recovery_attempts=attempt,
    )
    return f"requeued(attempt={attempt}, path={task_path.rsplit('.', 1)[-1]}, task_id={task_id})"


def _salvage_as_review(job: PdfSplitJob, *, reason: str = "") -> str:
    """把已产出的部分成果转成待复核，不重跑。

    这是本模块最重要的一条兜底：164 页扫描件的识别成本很高，重跑一次既贵又可能
    再次死在同一个地方。只要 `segments` 里已经有东西，就比从零开始有价值。
    """
    now = timezone.now()
    segment_count = job.segments.count()
    body = f"识别进程中途退出，已按已产出的 {segment_count} 个分段转入待复核。分段可能不完整，请核对后使用或重试。"
    PdfSplitJob.objects.filter(id=job.id).update(
        status=PdfSplitJobStatus.REVIEW_REQUIRED,
        finished_at=now,
        updated_at=now,
        error_message=_compose_message(reason, body),
    )
    return f"salvaged_as_review(segments={segment_count})"


def _mark_failed_after_retries(job: PdfSplitJob, *, reason: str = "") -> str:
    now = timezone.now()
    body = (
        f"识别进程反复中断（已自动重排 {job.recovery_attempts} 次），已停止自动恢复。"
        "请检查后端 worker 日志，或缩小材料页数后重试。"
    )
    PdfSplitJob.objects.filter(id=job.id).update(
        status=PdfSplitJobStatus.FAILED,
        finished_at=now,
        updated_at=now,
        error_message=_compose_message(reason, body),
    )
    return "marked_failed_after_retries"


def recover_job(job: PdfSplitJob, *, verdict: StalenessVerdict | None = None) -> str:
    """对单个卡死任务执行收尾。返回实际动作名（用于日志与断言）。

    ⚠️ 判「能不能救」看的是 `segments` 有没有落库，**不是** `processed_pages`。

    这两者不是一回事：分段是全部页解析完之后才一次性 `bulk_create` 的
    （见 `split/service.py::_persist_page_split`），所以一个任务完全可能显示
    「已处理 135/164 页」而 `segments` 仍然是 0。此时把它转成「待复核」只会
    给律师一个空列表——看似救回来了，实际什么都没留下。

    真实的判据只有一条：**有没有能交给律师看的分段**。

    `verdict` 是判死结论，只用于把「凭什么判死」写进 `error_message`；不传也能工作
    （等价于改动前「只写结论不写原因」的行为），方便直接对单个任务手动收尾。
    """

    reason = verdict.describe() if isinstance(verdict, StalenessVerdict) else ""

    if job.recovery_attempts >= MAX_RECOVERY_ATTEMPTS:
        return _mark_failed_after_retries(job, reason=reason)

    has_usable_segments = job.segments.exists()
    if has_usable_segments:
        return _salvage_as_review(job, reason=reason)
    return _requeue(job, reason=reason)


def sweep_stale_jobs(
    *,
    now: Any = None,
    stale_seconds: int = STALE_SECONDS,
    limit: int = MAX_RECOVERY_PER_RUN,
    stage_timeouts: Mapping[str, int] | None = None,
    grace_seconds: int = STAGE_DEAD_GRACE_SECONDS,
) -> dict[str, Any]:
    """巡检并拯救卡死任务。返回汇总，供管理命令与测试断言。

    Args:
        now: 测试注入的当前时刻；缺省用 timezone.now()。
        stale_seconds: 第一判据（心跳）阈值。管理命令的 `--stale-seconds` 走这里——
            原先本函数没有这个参数，命令传了会在运行时抛 TypeError，
            也就是说「可调阈值」这个能力其实一直没生效。
        limit: 单次最多处理几个（防首轮一口气重排打满队列）。
        stage_timeouts: 阶段硬超时映射（第二判据）。``None`` = 用 `default_stage_timeouts()`；
            ``{}`` = 关闭第二判据。
        grace_seconds: 第二判据余量，见 `STAGE_DEAD_GRACE_SECONDS`。

    设计为**幂等**：重复调用不会重复重排（重排后 status 变 PENDING，
    不再被 `find_stale_jobs` 选中）。
    """
    now = now or timezone.now()
    stale = find_stale_jobs(
        now=now,
        stale_seconds=stale_seconds,
        stage_timeouts=stage_timeouts,
        grace_seconds=grace_seconds,
    )[:limit]
    actions: list[dict[str, Any]] = []

    for job in stale:
        # 同一个 now 再算一次判死结论：find_stale_jobs 只回答「哪些」，这里要回答
        # 「凭什么」——阶段、预算、静默时长、最后进度都要落进日志，否则复盘时
        # 又只剩一句「心跳停了」（2026-11-20 那次事故就是这么被误读成网络问题的）。
        verdict = explain_staleness(
            job,
            now=now,
            stale_seconds=stale_seconds,
            stage_timeouts=stage_timeouts,
            grace_seconds=grace_seconds,
        )
        # 判死结论用实例属性传给 `recover_job`，不用 kwarg：本函数的裸调用签名是
        # `recover_job(job)`，既有调用方/测试替身只接受一个位置参数。
        try:
            # 判死结论走显式参数。原先用「实例上挂个 staleness_verdict 属性」传，
            # 既被 mypy 判 attr-defined、又被 ruff B010 禁 setattr —— 隐藏状态本来
            # 就该有个名字：recover_job 早就有 `verdict` 可选参数，直接传即可。
            action = recover_job(job, verdict=verdict)
            logger.warning(
                "pdf_split_job_recovered",
                extra={
                    "job_id": str(job.id),
                    "action": action,
                    "reason": verdict.reason,
                    "stage": verdict.stage,
                    "stage_budget_seconds": verdict.stage_budget_seconds,
                    "threshold_seconds": int(verdict.threshold_seconds),
                    "silent_seconds": None if verdict.silent_seconds is None else int(verdict.silent_seconds),
                    "progress": verdict.progress,
                    "processed_pages": verdict.processed_pages,
                    "total_pages": verdict.total_pages,
                    "last_liveness": str(verdict.last_liveness),
                    "verdict": verdict.describe(),
                },
            )
            actions.append(
                {
                    "job_id": str(job.id),
                    "action": action,
                    "reason": verdict.reason,
                    "stage": verdict.stage,
                }
            )
        except Exception as exc:  # 单个任务失败不能影响其他任务的拯救
            logger.exception(
                "pdf_split_job_recovery_failed",
                extra={"job_id": str(job.id), "reason": verdict.reason, "verdict": verdict.describe()},
            )
            actions.append({"job_id": str(job.id), "action": "error", "error": str(exc)})

    return {"stale_found": len(stale), "actions": actions}
