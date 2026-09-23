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
"""

from __future__ import annotations

import logging
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
