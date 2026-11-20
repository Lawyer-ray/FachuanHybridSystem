"""修复 django-q Cluster.stop() 在 macOS 上不幂等 / 不可重入导致的 atexit 报错。

django_q2 的 cluster.py 对 SIGTERM / SIGINT 都注册了 Cluster.sig_handler，
且 sig_handler 无条件转发到 Cluster.stop()：

    def stop(self) -> bool:
        if not self.sentinel.is_alive():
            return False
        self.stop_event.set()        # ← stop_event 已置 None 时 AttributeError
        self.sentinel.join()
        self.start_event = None
        self.stop_event = None       # ← 首次 stop() 跑完把事件清空

qcluster 主进程在 q.start() 返回后，靠 atexit 的 _exit_function() ->
active_children() -> p.join() -> os.waitpid(sentinel) 阻塞驻留（worker 由
sentinel 拉起）。此时若再来一个退出信号（watchfiles 自动重启、双击 Ctrl-C、
终端广播 SIGINT/SIGTERM），Python 会在阻塞的 os.waitpid 中投递信号、直接执行
sig_handler -> stop()；而前一次 stop() 若已把 stop_event / start_event 置 None，
这次就在 stop_event.set() 处炸出：

    AttributeError: 'NoneType' object has no attribute 'set'

（真实栈：util._exit_function -> p.join -> _popen.wait -> os.waitpid 中被打断，
回调进 django_q/cluster.sig_handler -> stop。）该异常发生在解释器退出阶段，
只以 "Exception ignored in atexit callback" 打印、不崩溃，但说明 cluster 未
干净拆机——遗留的 spawn worker 池可能退化为 PPID=1 孤儿进程，用旧模型代码抢
任务（见项目记忆 django-q-orphan-workers）。

修复要点（全平台安全，不改动正常单次退出语义）：

1. **None 短路**：进入即检查，sentinel / stop_event 任一为 None（未启动或已
   拆机）直接 return False，从根源杜绝 NoneType.set()。
2. **可重入短路**：Python 信号处理器只跑在主线程、且可中断任意字节码边界，
   因此「stop 进行中」（卡在 sentinel.join()）到达的后续信号会在同一线程再次
   进入 stop()。用 RLock（同一线程可重入，避免普通 Lock 自锁死锁）+ 一个
   _fachuan_stopping 标志：重入调用立即 return False，不重复 join、不重复清尾。

django-q fork 包名带 2（import lib 名为 django_q），与官方 django-q 同源。
若上游未来修复此问题，本补丁的 None/重入短路会自动降级为 no-op。

同属 macOS qcluster 稳定性补丁族，集中放在 apps/core/tasking/ 下（结构测试
仅放行该目录及 management commands 直接 import django_q，见
tests/ci/structure/test_no_django_q_leak.py）。

## 第二个坑：解释器收尾期收到退出信号 → 永久死锁（同文件 sig_handler 补丁）

即使 stop() 变成幂等，**信号来得太晚**仍会把 qcluster 变成永久僵尸：进程已经进了
atexit（`q.start()` 已返回，主线程卡在 `active_children() -> p.join() -> os.waitpid`），
此时再来一个 SIGTERM/SIGINT，django-q 的 sig_handler 会调 `Cluster.stop()` →
`sentinel.join()` → `Popen.wait()` 去抢**同一个** `_waitpid_lock`（multiprocessing 的
SemLock 不可重入、同一线程二次 acquire 即自杀式死锁）。真实现场（`sample <pid>` 抓的栈）：

    Py_RunMain → Py_FinalizeEx → atexit_callfuncs
      → os_waitpid                ← 持有 _waitpid_lock
        → PyErr_CheckSignals      ← 信号在这里投递
          → Cluster.stop() → sentinel.join()
            → SemLock.acquire → sem_wait   ← 永远卡住

后果不是崩溃而是**静默僵死**：主进程活着、心跳键已 TTL 消失、worker 全死（子进程留成
zombie），Redis 队列只进不出。2026-11-20 实测该状态持续 16 小时、积压 296 条任务，
法院短信处理卡在 status=pending 且 error_message 为空，前端只有「解析短信 进行中…」。
更糟的是 stop patch 里的重入保护会让后续信号一律短路，进程连 Ctrl-C / SIGTERM
都杀不掉，只能 SIGKILL。

修法：**解释器已在收尾时不要碰 Cluster.stop()**，恢复默认处置并重新抛一次信号，
让进程带着真实退出信号立刻结束（`sys.is_finalizing()` 是唯一可靠的判定）。
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import threading

logger = logging.getLogger(__name__)


def patch_django_q_cluster_stop_for_macos() -> None:
    """让 django-q 的 Cluster.stop() 变得幂等且可重入。"""
    try:
        from django_q import cluster as django_q_cluster
    except ImportError:
        logger.debug("django_q 不可用，跳过 Cluster.stop 补丁")
        return

    original = django_q_cluster.Cluster.stop
    if getattr(original, "_fachuan_stop_patched", False):
        return

    def _stop(self) -> bool:  # type: ignore[no-untyped-def]
        # RLock：信号处理器与主线程同线程可重入，避免普通 Lock 自锁死锁。
        guard = self.__dict__.setdefault("_fachuan_stop_guard", threading.RLock())
        with guard:
            # 1) 重入短路：已有一次 stop() 正在拆机（多半卡在 sentinel.join()），
            #    后续信号在同一线程再次进来，直接返回，不重复 join / 清尾。
            if self.__dict__.get("_fachuan_stopping"):
                return False

            sentinel = getattr(self, "sentinel", None)
            stop_event = getattr(self, "stop_event", None)
            # 2) None 短路：从未启动，或已拆机被清空，安全返回，杜绝 None.set()。
            if sentinel is None or stop_event is None:
                return False
            # 3) sentinel 已退出（含上次 stop() 已 join 完）：补一次清尾并短路。
            if not sentinel.is_alive():
                self.start_event = None
                self.stop_event = None
                return False

            self.__dict__["_fachuan_stopping"] = True
            try:
                return bool(original(self))
            finally:
                self.__dict__["_fachuan_stopping"] = False

    _stop._fachuan_stop_patched = True  # type: ignore[attr-defined]
    django_q_cluster.Cluster.stop = _stop
    logger.info("django-q Cluster.stop() 已 patch 为幂等 / 可重入（规避 atexit AttributeError）")


def _exit_on_signal(signum: int) -> None:
    """恢复默认处置并对自己重发该信号，让进程按真实退出信号结束。"""
    try:
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)
    except Exception:  # pragma: no cover - 兜底：连重发信号都失败时硬退出
        logger.exception("解释器收尾期重发信号失败，强制退出: signal=%s", signum)
        os._exit(1)


def patch_django_q_sig_handler_for_finalizing() -> None:
    """解释器收尾期（atexit）收到的 SIGTERM/SIGINT 直接退出，不进 Cluster.stop()。

    触发条件窄但致命：`q.start()` 已返回、进程正在 atexit 里 `p.join()` 等 sentinel，
    而此时 `_waitpid_lock` 已被持有。任何走 `Cluster.stop() -> sentinel.join()` 的
    退出信号都会在同一线程二次 acquire 该 SemLock 并永久挂起，同时让 worker 池
    全部消失——队列只进不出，且进程对后续信号免疫（见模块 docstring）。

    收尾期一律 `SIG_DFL` + 重发，语义上等价于「没装处理器时被杀掉」，退出码正常。
    """
    try:
        from django_q import cluster as django_q_cluster
    except ImportError:
        logger.debug("django_q 不可用，跳过 sig_handler 补丁")
        return

    original = django_q_cluster.Cluster.sig_handler
    if getattr(original, "_fachuan_sig_patched", False):
        return

    def _sig_handler(self, signum: int, frame: object) -> None:  # type: ignore[no-untyped-def]
        if sys.is_finalizing():
            logger.warning("解释器已在收尾，收到信号 %s：直接退出（不再走 Cluster.stop，避免 waitpid 死锁）", signum)
            _exit_on_signal(signum)
            return
        original(self, signum, frame)

    _sig_handler._fachuan_sig_patched = True  # type: ignore[attr-defined]
    django_q_cluster.Cluster.sig_handler = _sig_handler
    logger.info("django-q sig_handler 已 patch：收尾期信号直接退出（规避 waitpid 死锁僵死）")
