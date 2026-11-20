"""长阻塞阶段的「后台心跳」。

## 为什么需要它

取字阶段每页都会回调，心跳自然跟着刷（`PdfSplitService.touch_heartbeat`）。
但有几段路**既没有进度回调、又要跑很久**：

· 交叉比对（`run_dual_engine`）：整本 PDF 再解析一遍，164 页实测十几分钟；
· LLM 分段（`detect_segments_with_fallback`）：4-8 分钟；
· 逐页 OCR 兜底（`_ocr_pages_worker`）：单页云端识别最坏 300s，一页一拍就是
  几分钟没有进度回调（2026-11-20 事故，见下）。

这些期间 DB 一行不写，`job_recovery` 的看门狗会把**仍在正常工作**的任务判死
并重排——重排意味着整份卷宗再花一次云端费用。所以这里起一个守护线程，在阻塞
期间按固定间隔刷心跳，收工就停。

## 两个入口，一份实现

· `periodic_heartbeat(job_id)`：调用方手里有 job_id（cross_check / segment 阶段）；
· `heartbeat_block(beat)`：调用方手里只有一个**回调**（逐页 OCR 在线程池里跑，
  拿不到 job_id，也不该为了写一个时间戳把 job 行读出来）。

两者共用同一套线程与写库逻辑（`touch_heartbeat` 是唯一实现）；`split/service.py`
的同名方法只是转调它，不另写一份——同一件事有三份实现时，改心跳策略必然漏改。

## 为什么放独立模块

`split/service.py` 已经很长的，而这段逻辑和拆分业务毫无关系，只是「定时写一个
时间戳」。独立成上下文管理器后，任何未来的长阻塞段都能直接 `with` 一下。
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from django.utils import timezone

from apps.pdf_splitting.models import PdfSplitJob

logger = logging.getLogger("apps.pdf_splitting")

#: 默认心跳间隔。比看门狗阈值（1800s）小两个数量级，留足写库抖动与 GIL 延迟的余量。
DEFAULT_HEARTBEAT_INTERVAL = 15


def touch_heartbeat(*, job_id: Any) -> None:
    """刷新心跳，不动进度。

    必须走 `QuerySet.update()`：`auto_now` 只在 `Model.save()` 时生效，而这里
    不想为了一个时间戳把整行读出来再写回去（那是并发写覆盖）。
    """
    now = timezone.now()
    PdfSplitJob.objects.filter(id=job_id).update(heartbeat_at=now, updated_at=now)


def _heartbeat_loop(
    beat: Callable[[], None], interval: float, stop: threading.Event, log_extra: dict[str, Any]
) -> None:
    """守护线程主体：等到下一个间隔点，若未被叫停就刷一次心跳。

    用 `Event.wait()` 而不是 `time.sleep()`：收工时能立刻唤醒退出，不必再多等
    一整个间隔（否则线程会拖到进程结束前才散，测试里尤其明显）。

    参数是**回调**而不是 job_id：逐页 OCR 的线程池里拿不到 job_id，但它同样需要
    「阻塞期间也有一拍心跳」。job_id 版本由 `periodic_heartbeat` 用闭包包出来。
    """
    while not stop.wait(interval):
        try:
            beat()
        except Exception:
            # 心跳线程绝不能因为一次写库抖动炸掉主流程：心跳只是存活信号，
            # 丢一拍还有下一拍，看门狗阈值（1800s）也留了百倍余量。
            logger.warning("pdf_split_periodic_heartbeat_failed", exc_info=True, extra=log_extra)


@contextmanager
def _periodic(beat: Callable[[], None], *, interval: float, name: str, log_extra: dict[str, Any]) -> Iterator[None]:
    """`periodic_heartbeat` / `heartbeat_block` 的公共实现：起线程 → yield → 收工叫停。

    为什么用 `finally` 停线程而不是让线程自己跑完：线程是 daemon，不显式叫停
    就会一直贴着 job 活着直到进程退出——同一 worker 连续跑多个任务时会攒出一
    堆僵尸心跳线程，还会给早已结束的任务续命（看门狗永远看不出它死了）。
    """
    stop = threading.Event()
    thread = threading.Thread(
        target=_heartbeat_loop,
        args=(beat, interval, stop, log_extra),
        name=name,
        # daemon：即使主流程被强杀（worker 超时/OOM），也不留线程吊住进程退出。
        daemon=True,
    )
    thread.start()
    try:
        yield
    finally:
        stop.set()
        # 给线程一点时间收尾，但不 join 到天荒地老：它下一件事只是写一行时间戳，
        # 1 秒足够；超时就随 daemon 属性一起走，不允许心跳拖慢主流程收工。
        thread.join(timeout=1.0)


@contextmanager
def periodic_heartbeat(job_id: Any, interval: float = DEFAULT_HEARTBEAT_INTERVAL) -> Iterator[None]:
    """在 `with` 块执行期间，每 `interval` 秒刷一次心跳（调用方有 job_id 时用它）。"""
    with _periodic(
        lambda: touch_heartbeat(job_id=job_id),
        interval=interval,
        name=f"pdf-split-heartbeat-{job_id}",
        log_extra={"job_id": str(job_id)},
    ):
        yield


@contextmanager
def heartbeat_block(beat: Callable[[], None], *, interval: float = DEFAULT_HEARTBEAT_INTERVAL) -> Iterator[None]:
    """在 `with` 块执行期间，每 `interval` 秒调一次 `beat()`（调用方只有回调时用它）。

    为什么需要「回调版」：逐页 OCR 在线程池的 worker 里跑（见
    `split/ocr_handler._ocr_pages_worker`），那里既没有 job_id，也不该为了写一个
    时间戳去查 job 表；上层（`split/pipeline`）比谁都清楚该给哪个 job 刷心跳，
    所以往下传的是**动作**而不是**主键**——线程池与任务编排因此不必互相认识。

    2026-11-20 事故：93 页卷宗在 extract 阶段遇上 PaddleOCR 连续 8 次单页超时
    （每次 300s），期间心跳冻结 839s。心跳本是唯一可信的存活信号，一冻结，看门狗
    （`job_recovery`，阈值 1800s）就分不清「在正常重试」和「真死了」。
    """
    with _periodic(beat, interval=interval, name="pdf-split-heartbeat-block", log_extra={}):
        yield
