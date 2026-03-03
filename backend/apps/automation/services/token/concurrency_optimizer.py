"""
并发优化服务

优化并发场景下的资源使用，提供智能的并发控制和资源管理。
"""

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from apps.core.exceptions import TokenAcquisitionTimeoutError

logger = logging.getLogger(__name__)


@dataclass
class ConcurrencyConfig:
    """并发控制配置"""

    max_concurrent_acquisitions: int = 3  # 最大并发获取数
    max_concurrent_per_site: int = 2  # 每个站点最大并发数
    max_concurrent_per_account: int = 1  # 每个账号最大并发数
    acquisition_timeout: float = 300.0  # 获取超时时间（秒）
    lock_timeout: float = 30.0  # 锁超时时间（秒）
    queue_timeout: float = 60.0  # 队列等待超时时间（秒）
    resource_check_interval: float = 1.0  # 资源检查间隔（秒）


@dataclass
class ResourceUsage:
    """资源使用情况"""

    total_acquisitions: int = 0
    site_acquisitions: dict[str, int] = field(default_factory=dict)
    account_acquisitions: dict[str, int] = field(default_factory=dict)
    active_locks: set[str] = field(default_factory=set)


@dataclass
class _WaitEntry:
    """队列中的等待条目"""

    acquisition_id: str
    site_name: str
    account: str
    enqueued_at: float
    event: asyncio.Event


class ConcurrencyOptimizer:
    """
    并发优化器

    功能：
    1. 智能并发控制（总数 / 站点 / 账号三级限制）
    2. 队列管理：超限时阻塞等待，释放资源时唤醒
    3. 资源使用监控
    """

    def __init__(self, config: ConcurrencyConfig | None = None):
        self.config = config or ConcurrencyConfig()
        self._locks: dict[str, asyncio.Lock] = {}
        self._lock_creation_lock = asyncio.Lock()
        self._resource_usage = ResourceUsage()
        # 用 deque 替代 asyncio.Queue，方便遍历和按条件唤醒
        self._wait_queue: deque[_WaitEntry] = deque()

    async def acquire_resource(self, acquisition_id: str, site_name: str, account: str) -> bool:
        """
        获取资源（并发控制）

        超过并发限制时阻塞等待，直到有资源释放或超时。

        Raises:
            TokenAcquisitionTimeoutError: 获取资源超时
        """
        start_time = time.time()

        logger.info(
            "请求获取资源", extra={"acquisition_id": acquisition_id, "site_name": site_name, "account": account}
        )

        try:
            # 并发限制检查 + 排队等待
            if not self._check_concurrency_limits(site_name, account):
                await self._wait_for_slot(acquisition_id, site_name, account)

            # 获取账号级锁
            lock_key = f"{site_name}:{account}"
            lock = await self._get_lock(lock_key)

            try:
                await asyncio.wait_for(lock.acquire(), timeout=self.config.lock_timeout)
            except TimeoutError as e:
                elapsed = time.time() - start_time
                logger.error(
                    "获取锁超时",
                    extra={
                        "acquisition_id": acquisition_id,
                        "site_name": site_name,
                        "account": account,
                        "elapsed": elapsed,
                    },
                )
                raise TokenAcquisitionTimeoutError(f"获取资源锁超时: {self.config.lock_timeout}秒") from e

            # 更新资源使用情况
            self._update_resource_usage(site_name, account, increment=True)

            elapsed = time.time() - start_time
            logger.info(
                "资源获取成功",
                extra={
                    "acquisition_id": acquisition_id,
                    "site_name": site_name,
                    "account": account,
                    "elapsed": elapsed,
                    "total_acquisitions": self._resource_usage.total_acquisitions,
                },
            )
            return True

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(
                "资源获取失败",
                extra={
                    "acquisition_id": acquisition_id,
                    "site_name": site_name,
                    "account": account,
                    "error": str(e),
                    "elapsed": elapsed,
                },
            )
            raise

    async def release_resource(self, acquisition_id: str, site_name: str, account: str) -> None:
        """释放资源并唤醒队列中符合条件的等待者"""
        try:
            lock_key = f"{site_name}:{account}"
            lock = await self._get_lock(lock_key)

            if lock.locked():
                lock.release()

            self._update_resource_usage(site_name, account, increment=False)

            logger.info(
                "资源已释放",
                extra={
                    "acquisition_id": acquisition_id,
                    "site_name": site_name,
                    "account": account,
                    "total_acquisitions": self._resource_usage.total_acquisitions,
                },
            )

            # 唤醒队列中第一个符合并发限制的等待者
            self._wake_next_eligible()

        except Exception as e:
            logger.error(
                "释放资源失败",
                extra={"acquisition_id": acquisition_id, "site_name": site_name, "account": account, "error": str(e)},
            )

    async def get_resource_usage(self) -> dict[str, Any]:
        """获取资源使用情况"""
        return {
            "total_acquisitions": self._resource_usage.total_acquisitions,
            "site_acquisitions": dict(self._resource_usage.site_acquisitions),
            "account_acquisitions": dict(self._resource_usage.account_acquisitions),
            "active_locks": len(self._resource_usage.active_locks),
            "queue_size": len(self._wait_queue),
            "config": {
                "max_concurrent_acquisitions": self.config.max_concurrent_acquisitions,
                "max_concurrent_per_site": self.config.max_concurrent_per_site,
                "max_concurrent_per_account": self.config.max_concurrent_per_account,
            },
        }

    async def optimize_concurrency(self) -> dict[str, Any]:
        """优化并发配置"""
        usage = await self.get_resource_usage()
        recommendations: list[dict[str, Any]] = []

        if usage["total_acquisitions"] >= self.config.max_concurrent_acquisitions * 0.8:
            recommendations.append(
                {
                    "type": "increase_max_concurrent",
                    "current": self.config.max_concurrent_acquisitions,
                    "recommended": self.config.max_concurrent_acquisitions + 1,
                    "reason": "总并发数接近上限",
                }
            )

        for site, count in usage["site_acquisitions"].items():
            if count >= self.config.max_concurrent_per_site:
                recommendations.append(
                    {
                        "type": "site_bottleneck",
                        "site": site,
                        "current_count": count,
                        "reason": f"站点 {site} 并发数达到上限",
                    }
                )

        if usage["queue_size"] > 5:
            recommendations.append(
                {
                    "type": "queue_backlog",
                    "queue_size": usage["queue_size"],
                    "reason": "队列积压严重，建议增加并发数或优化处理速度",
                }
            )

        return {
            "current_usage": usage,
            "recommendations": recommendations,
            "optimization_applied": False,
        }

    async def cleanup_resources(self) -> None:
        """清理资源"""
        try:
            await self._cleanup_expired_locks()

            # 清理队列中所有等待者（不唤醒，让它们超时）
            self._wait_queue.clear()

            self._resource_usage = ResourceUsage()
            logger.info("并发资源清理完成")

        except Exception as e:
            logger.error("资源清理失败: %s", e)

    # ── 内部方法 ──

    def _check_concurrency_limits(self, site_name: str, account: str) -> bool:
        """检查是否可以立即执行（不超过三级并发限制）"""
        if self._resource_usage.total_acquisitions >= self.config.max_concurrent_acquisitions:
            return False

        site_count = self._resource_usage.site_acquisitions.get(site_name, 0)
        if site_count >= self.config.max_concurrent_per_site:
            return False

        account_count = self._resource_usage.account_acquisitions.get(account, 0)
        if account_count >= self.config.max_concurrent_per_account:
            return False

        return True

    async def _wait_for_slot(self, acquisition_id: str, site_name: str, account: str) -> None:
        """入队并阻塞，直到被 _wake_next_eligible 唤醒或超时"""
        entry = _WaitEntry(
            acquisition_id=acquisition_id,
            site_name=site_name,
            account=account,
            enqueued_at=time.time(),
            event=asyncio.Event(),
        )
        self._wait_queue.append(entry)

        logger.info(
            "请求已加入队列等待",
            extra={"acquisition_id": acquisition_id, "queue_size": len(self._wait_queue)},
        )

        try:
            await asyncio.wait_for(entry.event.wait(), timeout=self.config.queue_timeout)
        except TimeoutError as e:
            # 超时后从队列移除
            try:
                self._wait_queue.remove(entry)
            except ValueError:
                pass
            logger.error("队列等待超时", extra={"acquisition_id": acquisition_id})
            raise TokenAcquisitionTimeoutError("排队等待资源超时") from e

    def _wake_next_eligible(self) -> None:
        """遍历等待队列，唤醒第一个符合并发限制的条目；清理过期条目"""
        now = time.time()
        to_remove: list[_WaitEntry] = []

        for entry in self._wait_queue:
            # 清理过期
            if now - entry.enqueued_at > self.config.queue_timeout:
                to_remove.append(entry)
                continue

            if self._check_concurrency_limits(entry.site_name, entry.account):
                entry.event.set()
                to_remove.append(entry)
                break

        for entry in to_remove:
            try:
                self._wait_queue.remove(entry)
            except ValueError:
                pass

    async def _get_lock(self, lock_key: str) -> asyncio.Lock:
        """获取或创建锁对象"""
        async with self._lock_creation_lock:
            if lock_key not in self._locks:
                self._locks[lock_key] = asyncio.Lock()
            return self._locks[lock_key]

    def _update_resource_usage(self, site_name: str, account: str, increment: bool) -> None:
        """更新资源使用计数"""
        delta = 1 if increment else -1

        self._resource_usage.total_acquisitions = max(0, self._resource_usage.total_acquisitions + delta)

        current_site = self._resource_usage.site_acquisitions.get(site_name, 0)
        new_site_count = max(0, current_site + delta)
        if new_site_count > 0:
            self._resource_usage.site_acquisitions[site_name] = new_site_count
        else:
            self._resource_usage.site_acquisitions.pop(site_name, None)

        current_account = self._resource_usage.account_acquisitions.get(account, 0)
        new_account_count = max(0, current_account + delta)
        if new_account_count > 0:
            self._resource_usage.account_acquisitions[account] = new_account_count
        else:
            self._resource_usage.account_acquisitions.pop(account, None)

    async def _cleanup_expired_locks(self) -> None:
        """清理未被持有的锁对象"""
        expired_locks = [k for k, v in self._locks.items() if not v.locked()]
        for lock_key in expired_locks:
            self._locks.pop(lock_key, None)
        if expired_locks:
            logger.debug("清理了 %d 个过期锁", len(expired_locks))


# 全局并发优化器实例
concurrency_optimizer = ConcurrencyOptimizer()
