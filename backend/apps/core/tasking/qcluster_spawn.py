"""macOS 上 django-q 子进程启动方式从 fork 切换为 spawn。

django-q 的 cluster.py 硬编码 get_context("fork")，在 macOS 上会触发
ObjC 运行时竞态崩溃（+[NSNumber initialize] may have been in progress
in another thread when fork() was called）。OBJC_DISABLE_INITIALIZE_FORK_SAFETY
由 libobjc 在进程启动早期读取，Python 运行时设置无效，因此必须直接替换
context 工厂函数。

django-q 的 sentinel/worker/pusher/monitor 入口均自带 django.setup()，
spawn 模式完全兼容。

此文件放在 apps/core/tasking/ 下是因为结构测试要求仅核心基础设施层
可直接 import django_q，业务层需要通过 apps.core.tasking 抽象。
"""

from __future__ import annotations

import logging
import multiprocessing
import sys

logger = logging.getLogger(__name__)


def patch_django_q_mp_context_for_macos() -> None:
    """macOS 上将 django-q 子进程创建方式从 fork 切换为 spawn。"""
    if sys.platform != "darwin":
        return

    try:
        from django_q import cluster as django_q_cluster
    except ImportError:
        logger.debug("django_q 不可用，跳过 spawn patch")
        return

    original = django_q_cluster.get_mp_context
    if getattr(original, "_fachuan_spawn_patched", False):
        return

    def _spawn_context() -> multiprocessing.context.BaseContext:
        return multiprocessing.get_context("spawn")

    _spawn_context._fachuan_spawn_patched = True
    django_q_cluster.get_mp_context = _spawn_context
    logger.info("macOS 检测：django-q 子进程改用 spawn 启动，规避 fork ObjC 崩溃")
