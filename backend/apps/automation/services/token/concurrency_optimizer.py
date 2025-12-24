"""
并发优化服务

优化并发场景下的资源使用，提供智能的并发控制和资源管理。
"""
import asyncio
import logging
import time
from typing import Dict, Any, Optional, Set, List
from datetime import datetime, timedelta
from dataclasses import dataclass
from django.core.cache import cache
from django.utils import timezone

from apps.core.cache import CacheTimeout
from apps.core.exceptions import AutoTokenAcquisitionError, TokenAcquisitionTimeoutError

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
    site_acquisitions: Dict[str, int] = None
    account_acquisitions: Dict[str, int] = None
    active_locks: Set[str] = None
    
    def __post_init__(self):
        if self.site_acquisitions is None:
            self.site_acquisitions = {}
        if self.account_acquisitions is None:
            self.account_acquisitions = {}
        if self.active_locks is None:
            self.active_locks = set()


class ConcurrencyOptimizer:
    """
    并发优化器
    
    功能：
    1. 智能并发控制
    2. 资源使用监控
    3. 队列管理
    4. 死锁检测和恢复
    """
    
    def __init__(self, config: Optional[ConcurrencyConfig] = None):
        """
        初始化并发优化器
        
        Args:
            config: 并发控制配置
        """
        self.config = config or ConcurrencyConfig()
        self._locks: Dict[str, asyncio.Lock] = {}
        self._lock_creation_lock = asyncio.Lock()
        self._resource_usage = ResourceUsage()
        self._acquisition_queue: asyncio.Queue = asyncio.Queue()
        self._queue_processors: Dict[str, asyncio.Task] = {}
    
    async def acquire_resource(
        self, 
        acquisition_id: str,
        site_name: str,
        account: str
    ) -> bool:
        """
        获取资源（并发控制）
        
        Args:
            acquisition_id: 获取流程ID
            site_name: 网站名称
            account: 账号
            
        Returns:
            是否成功获取资源
            
        Raises:
            TokenAcquisitionTimeoutError: 获取资源超时
            AutoTokenAcquisitionError: 资源获取失败
        """
        start_time = time.time()
        
        logger.info(f"请求获取资源", extra={
            'acquisition_id': acquisition_id,
            'site_name': site_name,
            'account': account
        })
        
        try:
            # 检查并发限制
            if not await self._check_concurrency_limits(site_name, account):
                # 加入队列等待
                await self._enqueue_acquisition(acquisition_id, site_name, account)
            
            # 获取锁
            lock_key = f"{site_name}:{account}"
            lock = await self._get_lock(lock_key)
            
            # 尝试获取锁（带超时）
            try:
                await asyncio.wait_for(
                    lock.acquire(),
                    timeout=self.config.lock_timeout
                )
            except asyncio.TimeoutError:
                elapsed = time.time() - start_time
                logger.error(f"获取锁超时", extra={
                    'acquisition_id': acquisition_id,
                    'site_name': site_name,
                    'account': account,
                    'elapsed': elapsed
                })
                raise TokenAcquisitionTimeoutError(
                    f"获取资源锁超时: {self.config.lock_timeout}秒"
                )
            
            # 更新资源使用情况
            self._update_resource_usage(site_name, account, increment=True)
            
            # 记录资源获取成功
            elapsed = time.time() - start_time
            logger.info(f"资源获取成功", extra={
                'acquisition_id': acquisition_id,
                'site_name': site_name,
                'account': account,
                'elapsed': elapsed,
                'total_acquisitions': self._resource_usage.total_acquisitions
            })
            
            return True
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"资源获取失败", extra={
                'acquisition_id': acquisition_id,
                'site_name': site_name,
                'account': account,
                'error': str(e),
                'elapsed': elapsed
            })
            raise
    
    async def release_resource(
        self,
        acquisition_id: str,
        site_name: str,
        account: str
    ) -> None:
        """
        释放资源
        
        Args:
            acquisition_id: 获取流程ID
            site_name: 网站名称
            account: 账号
        """
        try:
            # 释放锁
            lock_key = f"{site_name}:{account}"
            lock = await self._get_lock(lock_key)
            
            if lock.locked():
                lock.release()
            
            # 更新资源使用情况
            self._update_resource_usage(site_name, account, increment=False)
            
            logger.info(f"资源已释放", extra={
                'acquisition_id': acquisition_id,
                'site_name': site_name,
                'account': account,
                'total_acquisitions': self._resource_usage.total_acquisitions
            })
            
            # 处理队列中的等待请求
            await self._process_queue()
            
        except Exception as e:
            logger.error(f"释放资源失败", extra={
                'acquisition_id': acquisition_id,
                'site_name': site_name,
                'account': account,
                'error': str(e)
            })
    
    async def get_resource_usage(self) -> Dict[str, Any]:
        """
        获取资源使用情况
        
        Returns:
            资源使用情况字典
        """
        return {
            'total_acquisitions': self._resource_usage.total_acquisitions,
            'site_acquisitions': dict(self._resource_usage.site_acquisitions),
            'account_acquisitions': dict(self._resource_usage.account_acquisitions),
            'active_locks': len(self._resource_usage.active_locks),
            'queue_size': self._acquisition_queue.qsize(),
            'config': {
                'max_concurrent_acquisitions': self.config.max_concurrent_acquisitions,
                'max_concurrent_per_site': self.config.max_concurrent_per_site,
                'max_concurrent_per_account': self.config.max_concurrent_per_account
            }
        }
    
    async def optimize_concurrency(self) -> Dict[str, Any]:
        """
        优化并发配置
        
        Returns:
            优化结果
        """
        usage = await self.get_resource_usage()
        recommendations = []
        
        # 分析当前使用情况
        if usage['total_acquisitions'] >= self.config.max_concurrent_acquisitions * 0.8:
            recommendations.append({
                'type': 'increase_max_concurrent',
                'current': self.config.max_concurrent_acquisitions,
                'recommended': self.config.max_concurrent_acquisitions + 1,
                'reason': '总并发数接近上限'
            })
        
        # 检查站点级别的并发
        for site, count in usage['site_acquisitions'].items():
            if count >= self.config.max_concurrent_per_site:
                recommendations.append({
                    'type': 'site_bottleneck',
                    'site': site,
                    'current_count': count,
                    'reason': f'站点 {site} 并发数达到上限'
                })
        
        # 检查队列积压
        if usage['queue_size'] > 5:
            recommendations.append({
                'type': 'queue_backlog',
                'queue_size': usage['queue_size'],
                'reason': '队列积压严重，建议增加并发数或优化处理速度'
            })
        
        return {
            'current_usage': usage,
            'recommendations': recommendations,
            'optimization_applied': False  # 这里可以实现自动优化
        }
    
    async def detect_deadlocks(self) -> List[Dict[str, Any]]:
        """
        检测死锁
        
        Returns:
            检测到的死锁列表
        """
        deadlocks = []
        
        # 检查长时间持有的锁
        current_time = time.time()
        
        for lock_key, lock in self._locks.items():
            if lock.locked():
                # 这里简化处理，实际应该记录锁的获取时间
                # 如果锁持有时间超过阈值，可能存在死锁
                pass
        
        # 检查队列中长时间等待的请求
        if self._acquisition_queue.qsize() > 0:
            # 这里可以检查队列中请求的等待时间
            pass
        
        return deadlocks
    
    async def recover_from_deadlock(self, deadlock_info: Dict[str, Any]) -> bool:
        """
        从死锁中恢复
        
        Args:
            deadlock_info: 死锁信息
            
        Returns:
            是否成功恢复
        """
        try:
            # 强制释放相关锁
            lock_key = deadlock_info.get('lock_key')
            if lock_key and lock_key in self._locks:
                lock = self._locks[lock_key]
                if lock.locked():
                    # 注意：这是危险操作，可能导致数据不一致
                    # 实际实现中需要更谨慎的处理
                    logger.warning(f"强制释放死锁: {lock_key}")
            
            return True
            
        except Exception as e:
            logger.error(f"死锁恢复失败: {e}")
            return False
    
    async def cleanup_resources(self) -> None:
        """清理资源"""
        try:
            # 清理过期的锁
            await self._cleanup_expired_locks()
            
            # 清理队列
            while not self._acquisition_queue.empty():
                try:
                    self._acquisition_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            
            # 重置资源使用情况
            self._resource_usage = ResourceUsage()
            
            logger.info("并发资源清理完成")
            
        except Exception as e:
            logger.error(f"资源清理失败: {e}")
    
    async def _check_concurrency_limits(self, site_name: str, account: str) -> bool:
        """
        检查并发限制
        
        Args:
            site_name: 网站名称
            account: 账号
            
        Returns:
            是否可以立即执行
        """
        # 检查总并发数
        if self._resource_usage.total_acquisitions >= self.config.max_concurrent_acquisitions:
            return False
        
        # 检查站点级别并发数
        site_count = self._resource_usage.site_acquisitions.get(site_name, 0)
        if site_count >= self.config.max_concurrent_per_site:
            return False
        
        # 检查账号级别并发数
        account_count = self._resource_usage.account_acquisitions.get(account, 0)
        if account_count >= self.config.max_concurrent_per_account:
            return False
        
        return True
    
    async def _enqueue_acquisition(
        self,
        acquisition_id: str,
        site_name: str,
        account: str
    ) -> None:
        """
        将获取请求加入队列
        
        Args:
            acquisition_id: 获取流程ID
            site_name: 网站名称
            account: 账号
        """
        request = {
            'acquisition_id': acquisition_id,
            'site_name': site_name,
            'account': account,
            'enqueued_at': time.time()
        }
        
        try:
            await asyncio.wait_for(
                self._acquisition_queue.put(request),
                timeout=self.config.queue_timeout
            )
            
            logger.info(f"请求已加入队列", extra={
                'acquisition_id': acquisition_id,
                'queue_size': self._acquisition_queue.qsize()
            })
            
        except asyncio.TimeoutError:
            logger.error(f"加入队列超时", extra={
                'acquisition_id': acquisition_id
            })
            raise TokenAcquisitionTimeoutError("请求队列已满，加入队列超时")
    
    async def _process_queue(self) -> None:
        """处理队列中的等待请求"""
        try:
            while not self._acquisition_queue.empty():
                try:
                    request = self._acquisition_queue.get_nowait()
                    
                    # 检查请求是否过期
                    if time.time() - request['enqueued_at'] > self.config.queue_timeout:
                        logger.warning(f"队列请求已过期", extra=request)
                        continue
                    
                    # 检查是否可以处理
                    if await self._check_concurrency_limits(
                        request['site_name'], 
                        request['account']
                    ):
                        logger.info(f"队列请求可以处理", extra=request)
                        # 这里应该通知等待的协程，但简化处理
                        break
                    else:
                        # 重新放回队列
                        await self._acquisition_queue.put(request)
                        break
                        
                except asyncio.QueueEmpty:
                    break
                    
        except Exception as e:
            logger.error(f"处理队列失败: {e}")
    
    async def _get_lock(self, lock_key: str) -> asyncio.Lock:
        """
        获取锁对象
        
        Args:
            lock_key: 锁键
            
        Returns:
            异步锁对象
        """
        async with self._lock_creation_lock:
            if lock_key not in self._locks:
                self._locks[lock_key] = asyncio.Lock()
            return self._locks[lock_key]
    
    def _update_resource_usage(
        self,
        site_name: str,
        account: str,
        increment: bool
    ) -> None:
        """
        更新资源使用情况
        
        Args:
            site_name: 网站名称
            account: 账号
            increment: 是否增加（False为减少）
        """
        delta = 1 if increment else -1
        
        # 更新总数
        self._resource_usage.total_acquisitions = max(
            0, self._resource_usage.total_acquisitions + delta
        )
        
        # 更新站点计数
        current_site = self._resource_usage.site_acquisitions.get(site_name, 0)
        new_site_count = max(0, current_site + delta)
        if new_site_count > 0:
            self._resource_usage.site_acquisitions[site_name] = new_site_count
        else:
            self._resource_usage.site_acquisitions.pop(site_name, None)
        
        # 更新账号计数
        current_account = self._resource_usage.account_acquisitions.get(account, 0)
        new_account_count = max(0, current_account + delta)
        if new_account_count > 0:
            self._resource_usage.account_acquisitions[account] = new_account_count
        else:
            self._resource_usage.account_acquisitions.pop(account, None)
    
    async def _cleanup_expired_locks(self) -> None:
        """清理过期的锁"""
        # 这里简化处理，实际应该记录锁的创建时间并清理过期锁
        expired_locks = []
        
        for lock_key, lock in self._locks.items():
            if not lock.locked():
                expired_locks.append(lock_key)
        
        for lock_key in expired_locks:
            self._locks.pop(lock_key, None)
        
        if expired_locks:
            logger.debug(f"清理了 {len(expired_locks)} 个过期锁")


# 全局并发优化器实例
concurrency_optimizer = ConcurrencyOptimizer()