"""Django app configuration."""

import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class AgentConfig(AppConfig):
    default_auto_field: str = "django.db.models.BigAutoField"
    name: str = "apps.agent"
    verbose_name = "Agent 运行时（pi）"

    def ready(self) -> None:
        """注册内置 agent 后端 + 记忆相关的周期任务。

        ## 为什么后端注册放在 ready() 而不是模块导入副作用

        导入副作用依赖「有人先 import 了那个模块」，而 ``services/chat/stream.py``
        取后端是在请求处理时才发生的一一开发机上跑一轮对话、后台 djq worker
        跑任务、单元测试直接调 ``stream_chat``，三条路径没有任何一个保证先
        import 过 ``pi_backend``。漏了就在第一轮对话里报「未知 agent backend」，
        而且只在冷启动后的**第一轮**暴露，最难复现。

        ``ready()`` 是 Django 保证在 app 可用后执行一次的钩子，三种入口都有。

        ## 为什么注册失败不阻断启动

        与下面的调度表注册相反：后端注册表是进程内纯内存操作，不会因为数据库未
        migrate 而失败。它真的失败（比如代码里写了两个 ``kind="pi"``）是开发期
        错误，此时继续启动只会把错误推到用户请求上。所以要让它直接抛出去
        （不包 try），启动即失败、部署即回滚。
        """
        # 延后 import：``builtin`` 会连带拉起 pi 的 rpc / 池依赖，放在模块头
        # 会让 ``import apps.agent.apps`` 就把 pi 整包加载进来（含子进程相关模块）。
        from .backends.builtin import ensure_registered

        # 启动时先装一遍；同一个函数也在 ``stream_chat`` 取后端前调，注册表
        # 被清空也能自愈（幂等）。两处都走它，避免两套注册逻辑漂移。
        ensure_registered()

        self._connect_gateway_cache_invalidation()
        self._register_memory_schedules()

    @staticmethod
    def _connect_gateway_cache_invalidation() -> None:
        """``LLMProvider`` 增删改 → 立刻清掉网关配置缓存。

        为什么挂在 agent app 的 ``ready()`` 而不是 ``core`` 的：缓存本身
        （``backends.gateway_cache``）只服务 openai-agents / dsh 两个后端，
        是 agent 侧的读优化；把它接进 core 的启动路径会让「清 core 的缓存」
        与「agent 的读法」耦合，而 agent 是可选模块。

        连信号失败只 warning：缓存清不掉最坏结果是「Admin 改了配置，最多 30s
        （:data:`gateway_cache.DEFAULT_TTL_SECONDS`）后生效」，不该让整个进程
        起不来。
        """
        try:
            from django.db.models.signals import post_delete, post_save

            from apps.core.models import LLMProvider

            from .backends.gateway_cache import invalidate_gateway_cache
        except Exception:
            logger.warning("网关配置缓存的失效信号未连接（仅按 TTL 过期）", exc_info=True)
            return

        for signal, uid in ((post_save, "agent_llm_provider_saved"), (post_delete, "agent_llm_provider_deleted")):
            # 直接 connect 而不是 ``@receiver``：本方法在 ``ready()`` 里可能被调用
            # 多次（测试里重建 app registry），``dispatch_uid`` 保证 receiver 只挂一份。
            signal.connect(invalidate_gateway_cache, sender=LLMProvider, dispatch_uid=uid, weak=False)

    @staticmethod
    def _register_memory_schedules() -> None:
        """注册记忆相关的周期任务。

        与 ``apps/core/apps.py`` 同一模式：启动时补注册一次，用
        ``schedule_exists`` 守卫避免重复部署产生重复任务。

        为什么要现在注册：「行为推断」是记忆三条来源里唯一零成本、零幻觉的
        一条（读 ``AgentApproval`` / ``AgentRun`` 的既有审计数据），但它的
        产出只有在**定期跑**时才有意义。落地时它只是一个能被调用的函数，
        没挂 schedule 就等于不存在——这是本轮补上的缺口。

        失败只降级不阻断：调度表可能尚未 migrate，这时 app 仍要能启动。

        **必须经 ``run_startup_db_sync`` 摆渡**：ASGI 部署下 ready() 跑在事件
        循环线程里，直接查调度表会抛 ``SynchronousOnlyOperation``（每个 uvicorn
        进程启动时都会报这条 warning，调度一次也没注册上）。
        """
        try:
            from apps.core.utils.startup_db import allow_startup_db, run_startup_db_sync

            from .services.memory_tasks import _register_schedules

            def _register() -> None:
                with allow_startup_db():
                    _register_schedules()

            run_startup_db_sync(_register)
        except Exception:
            logger.warning("记忆定时任务注册跳过（未就绪）", exc_info=True)
