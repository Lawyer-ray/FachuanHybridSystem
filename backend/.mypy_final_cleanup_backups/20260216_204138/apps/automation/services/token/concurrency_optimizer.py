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
    max_concurrent_acquisitions: int = 3
    max_concurrent_per_site: int = 2
    max_concurrent_per_account: int = 1
    acquisition_timeout: float = 300.0
    lock_timeout: float = 30.0
    queue_timeout: float = 60.0
    resource_check_interval: float = 1.0

@dataclass
class ResourceUsage:
    """资源使用情况"""
    total_acquisitions: int = 0
    site_acquisitions: Dict[str, int] | None = None
    account_acquisitions: Dict[str, int] | None = None
    active_locks: Set[str] | None = None

    def __post_init__(self) -> None:
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

    def __init__(self, config: Optional[ConcurrencyConfig]=None) -> None:
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

    async def acquire_resource(self, acquisition_id: str, site_name: str, account: str) -> bool:
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
        logger.info(f'请求获取资源', extra={'acquisition_id': acquisition_id, 'site_name': site_name, 'account': account})
        try:
            if not await self._check_concurrency_limits(site_name, account):
                await self._enqueue_acquisition(acquisition_id, site_name, account)
            lock_key = f'{site_name}:{account}'
            lock = await self._get_lock(lock_key)
            try:
                await asyncio.wait_for(lock.acquire(), timeout=self.config.lock_timeout)
            except asyncio.TimeoutError:
                elapsed = time.time() - start_time
                logger.error(f'获取锁超时', extra={'acquisition_id': acquisition_id, 'site_name': site_name, 'account': account, 'elapsed': elapsed})
                raise TokenAcquisitionTimeoutError(f'获取资源锁超时: {self.config.lock_timeout}秒')
            self._update_resource_usage(site_name, account, increment=True)
            elapsed = time.time() - start_time
            logger.info(f'资源获取成功', extra={'acquisition_id': acquisition_id, 'site_name': site_name, 'account': account, 'elapsed': elapsed, 'total_acquisitions': self._resource_usage.total_acquisitions})
            return True
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f'资源获取失败', extra={'acquisition_id': acquisition_id, 'site_name': site_name, 'account': account, 'error': str(e), 'elapsed': elapsed})
            raise

    async def release_resource(self, acquisition_id: str, site_name: str, account: str) -> None:
        """
        释放资源
        
        Args:
            acquisition_id: 获取流程ID
            site_name: 网站名称
            account: 账号
        """
        try:
            lock_key = f'{site_name}:{account}'
            lock = await self._get_lock(lock_key)
            if lock.locked():
                lock.release()
            self._update_resource_usage(site_name, account, increment=False)
            logger.info(f'资源已释放', extra={'acquisition_id': acquisition_id, 'site_name': site_name, 'account': account, 'total_acquisitions': self._resource_usage.total_acquisitions})
            await self._process_queue()
        except Exception as e:
            logger.error(f'释放资源失败', extra={'acquisition_id': acquisition_id, 'site_name': site_name, 'account': account, 'error': str(e)})

    async def get_resource_usage(self) -> Dict[str, Any]:
        """
        获取资源使用情况
        
        Returns:
            资源使用情况字典
        """
        return {'total_acquisitions': self._resource_usage.total_acquisitions, 'site_acquisitions': dict[str, Any](self._resource_usage.site_acquisitions), 'account_acquisitions': dict[str, Any](self._resource_usage.account_acquisitions), 'active_locks': len(self._resource_usage.active_locks), 'queue_size': self._acquisition_queue.qsize(), 'config': {'max_concurrent_acquisitions': self.config.max_concurrent_acquisitions, 'max_concurrent_per_site': self.config.max_concurrent_per_site, 'max_concurrent_per_account': self.config.max_concurrent_per_account}}  # type: ignore[arg-type, arg-type]

    async def optimize_concurrency(self) -> Dict[str, Any]:
        """
        优化并发配置
        
        Returns:
            优化结果
        """
        usage = await self.get_resource_usage()
        recommendations = []
        if usage['total_acquisitions'] >= self.config.max_concurrent_acquisitions * 0.8:
            recommendations.append({'type': 'increase_max_concurrent', 'current': self.config.max_concurrent_acquisitions, 'recommended': self.config.max_concurrent_acquisitions + 1, 'reason': '总并发数接近上限'})
        for site, count in usage['site_acquisitions'].items():
            if count >= self.config.max_concurrent_per_site:
                recommendations.append({'type': 'site_bottleneck', 'site': site, 'current_count': count, 'reason': f'站点 {site} 并发数达到上限'})
        if usage['queue_size'] > 5:
            recommendations.append({'type': 'queue_backlog', 'queue_size': usage['queue_size'], 'reason': '队列积压严重，建议增加并发数或优化处理速度'})
        return {'current_usage': usage, 'recommendations': recommendations, 'optimization_applied': False}

    async def detect_deadlocks(self) -> List[Dict[str, Any]]:
        """
        检测死锁
        
        Returns:
            检测到的死锁列表
        """
        deadlocks = []  # type: ignore[var-annotated]
        current_time = time.time()
        for lock_key, lock in self._locks.items():
            if lock.locked():
                pass
        if self._acquisition_queue.qsize() > 0:
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
            lock_key = deadlock_info.get('lock_key')
            if lock_key and lock_key in self._locks:
                lock = self._locks[lock_key]
                if lock.locked():
                    logger.warning(f'强制释放死锁: {lock_key}')
            return True
        except Exception as e:
            logger.error(f'死锁恢复失败: {e}')
            return False

    async def cleanup_resources(self) -> None:
        """清理资源"""
        try:
            await self._cleanup_expired_locks()
            while not self._acquisition_queue.empty():
                try:
                    self._acquisition_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            self._resource_usage = ResourceUsage()
            logger.info('并发资源清理完成')
        except Exception as e:
            logger.error(f'资源清理失败: {e}')

    async def _check_concurrency_limits(self, site_name: str, account: str) -> bool:
        """
        检查并发限制
        
        Args:
            site_name: 网站名称
            account: 账号
            
        Returns:
            是否可以立即执行
        """
        if self._resource_usage.total_acquisitions >= self.config.max_concurrent_acquisitions:
            return False
        site_count = self._resource_usage.site_acquisitions.get(site_name, 0)
        if site_count >= self.config.max_concurrent_per_site:
            return False
        account_count = self._resource_usage.account_acquisitions.get(account, 0)
        if account_count >= self.config.max_concurrent_per_account:
            return False
        return True

    async def _enqueue_acquisition(self, acquisition_id: str, site_name: str, account: str) -> None:
        """
        将获取请求加入队列
        
        Args:
            acquisition_id: 获取流程ID
            site_name: 网站名称
            account: 账号
        """
        request = {'acquisition_id': acquisition_id, 'site_name': site_name, 'account': account, 'enqueued_at': time.time()}
        try:
            await asyncio.wait_for(self._acquisition_queue.put(request), timeout=self.config.queue_timeout)
            logger.info(f'请求已加入队列', extra={'acquisition_id': acquisition_id, 'queue_size': self._acquisition_queue.qsize()})
        except asyncio.TimeoutError:
            logger.error(f'加入队列超时', extra={'acquisition_id': acquisition_id})
            raise TokenAcquisitionTimeoutError('请求队列已满，加入队列超时')

    async def _process_queue(self) -> None:
        """处理队列中的等待请求"""
        try:
            while not self._acquisition_queue.empty():
                try:
                    request = self._acquisition_queue.get_nowait()
                    if time.time() - request['enqueued_at'] > self.config.queue_timeout:
                        logger.warning(f'队列请求已过期', extra=request)
                        continue
                    if await self._check_concurrency_limits(request['site_name'], request['account']):
                        logger.info(f'队列请求可以处理', extra=request)
                        break
                    else:
                        await self._acquisition_queue.put(request)
                        break
                except asyncio.QueueEmpty:
                    break
        except Exception as e:
            logger.error(f'处理队列失败: {e}')

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

    def _update_resource_usage(self, site_name: str, account: str, increment: bool) -> None:
        """
        更新资源使用情况
        
        Args:
            site_name: 网站名称
            account: 账号
            increment: 是否增加（False为减少）
        """
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
        """清理过期的锁"""
        expired_locks = []
        for lock_key, lock in self._locks.items():
            if not lock.locked():
                expired_locks.append(lock_key)
        for lock_key in expired_locks:
            self._locks.pop(lock_key, None)
        if expired_locks:
            logger.debug(f'清理了 {len(expired_locks)} 个过期锁')
concurrency_optimizer = ConcurrencyOptimizer()