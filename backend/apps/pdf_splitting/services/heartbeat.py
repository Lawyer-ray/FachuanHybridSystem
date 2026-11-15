"""长阻塞阶段的「后台心跳」。

## 为什么需要它

取字阶段每页都会回调，心跳自然跟着刷（`PdfSplitService.touch_heartbeat`）。
但有两段路**既没有进度回调、又要跑很久**：

· 交叉比对（`run_dual_engine`）：整本 PDF 再解析一遍，164 页实测十几分钟；
· LLM 分段（`detect_segments_with_fallback`）：4-8 分钟。

这两段期间 DB 一行不写，`job_recovery` 的看门狗会把**仍在正常工作**的任务判死
并重排——重排意味着整份卷宗再花一次云端费用。所以这里起一个守护线程，在阻塞
期间按固定间隔刷心跳，收工就停。

## 为什么放独立模块

`split/service.py` 已经很长的，而这段逻辑和拆分业务毫无关系，只是「定时写一个
时间戳」。独立成上下文管理器后，任何未来的长阻塞段都能直接 `with` 一下。
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
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


def _heartbeat_loop(job_id: Any, interval: float, stop: threading.Event) -> None:
    """守护线程主体：等到下一个间隔点，若未被叫停就刷一次心跳。

    用 `Event.wait()` 而不是 `time.sleep()`：收工时能立刻唤醒退出，不必再多等
    一整个间隔（否则线程会拖到进程结束前才散，测试里尤其明显）。
    """
    while not stop.wait(interval):
        try:
            touch_heartbeat(job_id=job_id)
        except Exception:
            # 心跳线程绝不能因为一次写库抖动炸掉主流程：心跳只是存活信号，
            # 丢一拍还有下一拍，看门狗阈值（1800s）也留了百倍余量。
            logger.warning("pdf_split_periodic_heartbeat_failed", exc_info=True, extra={"job_id": str(job_id)})


@contextmanager
def periodic_heartbeat(job_id: Any, interval: float = DEFAULT_HEARTBEAT_INTERVAL) -> Iterator[None]:
    """在 `with` 块执行期间，每 `interval` 秒刷一次心跳。

    为什么用 `finally` 停线程而不是让线程自己跑完：线程是 daemon，不显式叫停
    就会一直贴着 job 活着直到进程退出——同一 worker 连续跑多个任务时会攒出一
    堆僵尸心跳线程，还会给早已结束的任务续命（看门狗永远看不出它死了）。
    """
    stop = threading.Event()
    thread = threading.Thread(
        target=_heartbeat_loop,
        args=(job_id, interval, stop),
        name=f"pdf-split-heartbeat-{job_id}",
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
