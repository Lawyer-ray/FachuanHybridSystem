"""
Steering 缓存策略实现

本模块实现了多种缓存策略，用于优化 Steering 规范系统的性能：
- LRU (Least Recently Used) 缓存策略
- TTL (Time To Live) 缓存策略
- 基于文件修改时间的智能缓存策略
- 分层缓存策略

Requirements: 8.2
"""

import os
import time
import hashlib
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Protocol
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class CacheStrategy(Enum):
    """缓存策略枚举"""
    LRU = "lru"  # 最近最少使用
    TTL = "ttl"  # 生存时间
    SMART = "smart"  # 智能缓存（基于文件修改时间）
    LAYERED = "layered"  # 分层缓存
    ADAPTIVE = "adaptive"  # 自适应缓存


@dataclass
class CacheEntry:
    """缓存条目"""
    key: str
    data: Any
    created_at: float
    last_accessed: float
    access_count: int = 0
    file_mtime: Optional[float] = None  # 文件修改时间
    size_bytes: int = 0
    priority: int = 0
    
    def touch(self):
        """更新访问时间和次数"""
        self.last_accessed = time.time()
        self.access_count += 1
    
    def is_expired(self, ttl_seconds: float) -> bool:
        """检查是否过期"""
        if ttl_seconds <= 0:
            return False
        return time.time() - self.created_at > ttl_seconds
    
    def is_file_modified(self, file_path: str) -> bool:
        """检查文件是否被修改"""
        if self.file_mtime is None:
            return False
        
        try:
            current_mtime = os.path.getmtime(file_path)
            return current_mtime > self.file_mtime
        except (OSError, FileNotFoundError):
            return True  # 文件不存在，认为已修改


class CacheStrategyInterface(ABC):
    """缓存策略接口"""
    
    @abstractmethod
    def should_cache(self, key: str, data: Any, metadata: Dict[str, Any]) -> bool:
        """判断是否应该缓存"""
        pass
    
    @abstractmethod
    def should_evict(self, entry: CacheEntry, cache_state: Dict[str, Any]) -> bool:
        """判断是否应该淘汰"""
        pass
    
    @abstractmethod
    def get_eviction_candidates(self, entries: Dict[str, CacheEntry], 
                               target_count: int) -> List[str]:
        """获取淘汰候选项"""
        pass
    
    @abstractmethod
    def update_on_access(self, entry: CacheEntry) -> None:
        """访问时更新策略状态"""
        pass


class LRUCacheStrategy(CacheStrategyInterface):
    """LRU 缓存策略"""
    
    def __init__(self, max_entries: int = 1000):
        self.max_entries = max_entries
    
    def should_cache(self, key: str, data: Any, metadata: Dict[str, Any]) -> bool:
        """总是缓存"""
        return True
    
    def should_evict(self, entry: CacheEntry, cache_state: Dict[str, Any]) -> bool:
        """当缓存满时淘汰"""
        return cache_state.get("cache_size", 0) >= self.max_entries
    
    def get_eviction_candidates(self, entries: Dict[str, CacheEntry], 
                               target_count: int) -> List[str]:
        """按最后访问时间排序，返回最旧的条目"""
        sorted_entries = sorted(
            entries.items(),
            key=lambda x: x[1].last_accessed
        )
        return [key for key, _ in sorted_entries[:target_count]]
    
    def update_on_access(self, entry: CacheEntry) -> None:
        """更新访问时间"""
        entry.touch()


class TTLCacheStrategy(CacheStrategyInterface):
    """TTL 缓存策略"""
    
    def __init__(self, ttl_seconds: float = 3600):
        self.ttl_seconds = ttl_seconds
    
    def should_cache(self, key: str, data: Any, metadata: Dict[str, Any]) -> bool:
        """总是缓存"""
        return True
    
    def should_evict(self, entry: CacheEntry, cache_state: Dict[str, Any]) -> bool:
        """检查是否过期"""
        return entry.is_expired(self.ttl_seconds)
    
    def get_eviction_candidates(self, entries: Dict[str, CacheEntry], 
                               target_count: int) -> List[str]:
        """返回过期的条目"""
        expired_keys = []
        for key, entry in entries.items():
            if entry.is_expired(self.ttl_seconds):
                expired_keys.append(key)
        
        # 如果过期条目不够，按创建时间排序
        if len(expired_keys) < target_count:
            sorted_entries = sorted(
                entries.items(),
                key=lambda x: x[1].created_at
            )
            remaining_count = target_count - len(expired_keys)
            for key, _ in sorted_entries[:remaining_count]:
                if key not in expired_keys:
                    expired_keys.append(key)
        
        return expired_keys[:target_count]
    
    def update_on_access(self, entry: CacheEntry) -> None:
        """TTL 策略不需要在访问时更新"""
        pass


class SmartCacheStrategy(CacheStrategyInterface):
    """智能缓存策略（基于文件修改时间）"""
    
    def __init__(self, ttl_seconds: float = 3600, check_file_mtime: bool = True):
        self.ttl_seconds = ttl_seconds
        self.check_file_mtime = check_file_mtime
    
    def should_cache(self, key: str, data: Any, metadata: Dict[str, Any]) -> bool:
        """根据文件类型和大小决定是否缓存"""
        file_path = metadata.get("file_path")
        if not file_path:
            return True
        
        try:
            # 检查文件大小，太大的文件不缓存
            file_size = os.path.getsize(file_path)
            if file_size > 1024 * 1024:  # 1MB
                return False
            
            # 检查文件类型
            if file_path.endswith(('.tmp', '.log')):
                return False
            
            return True
        except (OSError, FileNotFoundError):
            return False
    
    def should_evict(self, entry: CacheEntry, cache_state: Dict[str, Any]) -> bool:
        """检查是否过期或文件被修改"""
        if entry.is_expired(self.ttl_seconds):
            return True
        
        if self.check_file_mtime:
            file_path = cache_state.get("file_path")
            if file_path and entry.is_file_modified(file_path):
                return True
        
        return False
    
    def get_eviction_candidates(self, entries: Dict[str, CacheEntry], 
                               target_count: int) -> List[str]:
        """优先淘汰过期和文件被修改的条目"""
        candidates = []
        
        # 首先收集过期和文件被修改的条目
        for key, entry in entries.items():
            if entry.is_expired(self.ttl_seconds):
                candidates.append((key, 0))  # 优先级 0（最高）
            elif self.check_file_mtime:
                # 这里需要文件路径信息，简化处理
                candidates.append((key, 1))  # 优先级 1
        
        # 如果不够，按访问频率排序
        if len(candidates) < target_count:
            remaining_entries = {k: v for k, v in entries.items() 
                               if k not in [c[0] for c in candidates]}
            
            sorted_remaining = sorted(
                remaining_entries.items(),
                key=lambda x: (x[1].access_count, x[1].last_accessed)
            )
            
            for key, _ in sorted_remaining[:target_count - len(candidates)]:
                candidates.append((key, 2))  # 优先级 2
        
        # 按优先级排序并返回
        candidates.sort(key=lambda x: x[1])
        return [key for key, _ in candidates[:target_count]]
    
    def update_on_access(self, entry: CacheEntry) -> None:
        """更新访问统计"""
        entry.touch()


class LayeredCacheStrategy(CacheStrategyInterface):
    """分层缓存策略"""
    
    def __init__(self, 
                 hot_cache_size: int = 100,
                 warm_cache_size: int = 500,
                 cold_cache_ttl: float = 7200):
        self.hot_cache_size = hot_cache_size
        self.warm_cache_size = warm_cache_size
        self.cold_cache_ttl = cold_cache_ttl
    
    def should_cache(self, key: str, data: Any, metadata: Dict[str, Any]) -> bool:
        """总是缓存"""
        return True
    
    def should_evict(self, entry: CacheEntry, cache_state: Dict[str, Any]) -> bool:
        """根据层级决定是否淘汰"""
        cache_size = cache_state.get("cache_size", 0)
        
        # 冷缓存层：检查 TTL
        if entry.access_count <= 1 and entry.is_expired(self.cold_cache_ttl):
            return True
        
        # 如果缓存过满，淘汰冷数据
        if cache_size > self.hot_cache_size + self.warm_cache_size:
            return entry.access_count <= 1
        
        return False
    
    def get_eviction_candidates(self, entries: Dict[str, CacheEntry], 
                               target_count: int) -> List[str]:
        """分层淘汰策略"""
        candidates = []
        
        # 按访问频率分层
        hot_entries = []
        warm_entries = []
        cold_entries = []
        
        for key, entry in entries.items():
            if entry.access_count >= 10:
                hot_entries.append((key, entry))
            elif entry.access_count >= 3:
                warm_entries.append((key, entry))
            else:
                cold_entries.append((key, entry))
        
        # 优先淘汰冷数据
        cold_entries.sort(key=lambda x: x[1].last_accessed)
        for key, _ in cold_entries[:target_count]:
            candidates.append(key)
        
        # 如果还需要更多，淘汰温数据
        if len(candidates) < target_count:
            warm_entries.sort(key=lambda x: x[1].last_accessed)
            remaining = target_count - len(candidates)
            for key, _ in warm_entries[:remaining]:
                candidates.append(key)
        
        # 最后才淘汰热数据
        if len(candidates) < target_count:
            hot_entries.sort(key=lambda x: x[1].last_accessed)
            remaining = target_count - len(candidates)
            for key, _ in hot_entries[:remaining]:
                candidates.append(key)
        
        return candidates
    
    def update_on_access(self, entry: CacheEntry) -> None:
        """更新访问统计"""
        entry.touch()


class AdaptiveCacheStrategy(CacheStrategyInterface):
    """自适应缓存策略"""
    
    def __init__(self):
        self.hit_rate_window = 100  # 命中率计算窗口
        self.recent_hits = []
        self.current_strategy = "lru"
        self.strategy_performance = {
            "lru": {"hits": 0, "misses": 0},
            "ttl": {"hits": 0, "misses": 0},
            "smart": {"hits": 0, "misses": 0}
        }
        
        # 内置策略
        self.strategies = {
            "lru": LRUCacheStrategy(),
            "ttl": TTLCacheStrategy(),
            "smart": SmartCacheStrategy()
        }
    
    def should_cache(self, key: str, data: Any, metadata: Dict[str, Any]) -> bool:
        """使用当前最佳策略"""
        return self.strategies[self.current_strategy].should_cache(key, data, metadata)
    
    def should_evict(self, entry: CacheEntry, cache_state: Dict[str, Any]) -> bool:
        """使用当前最佳策略"""
        return self.strategies[self.current_strategy].should_evict(entry, cache_state)
    
    def get_eviction_candidates(self, entries: Dict[str, CacheEntry], 
                               target_count: int) -> List[str]:
        """使用当前最佳策略"""
        return self.strategies[self.current_strategy].get_eviction_candidates(
            entries, target_count
        )
    
    def update_on_access(self, entry: CacheEntry) -> None:
        """更新访问统计并调整策略"""
        self.strategies[self.current_strategy].update_on_access(entry)
        
        # 记录命中
        self.recent_hits.append(True)
        if len(self.recent_hits) > self.hit_rate_window:
            self.recent_hits.pop(0)
        
        # 定期评估策略性能
        if len(self.recent_hits) >= self.hit_rate_window:
            self._evaluate_and_adapt()
    
    def record_miss(self):
        """记录缓存未命中"""
        self.recent_hits.append(False)
        if len(self.recent_hits) > self.hit_rate_window:
            self.recent_hits.pop(0)
    
    def _evaluate_and_adapt(self):
        """评估并调整策略"""
        current_hit_rate = sum(self.recent_hits) / len(self.recent_hits)
        
        # 如果当前命中率低于阈值，尝试切换策略
        if current_hit_rate < 0.7:  # 70% 命中率阈值
            best_strategy = self._find_best_strategy()
            if best_strategy != self.current_strategy:
                logger.info(f"自适应缓存策略切换: {self.current_strategy} -> {best_strategy}")
                self.current_strategy = best_strategy
    
    def _find_best_strategy(self) -> str:
        """找到最佳策略"""
        best_strategy = self.current_strategy
        best_hit_rate = 0.0
        
        for strategy_name, perf in self.strategy_performance.items():
            total_requests = perf["hits"] + perf["misses"]
            if total_requests > 0:
                hit_rate = perf["hits"] / total_requests
                if hit_rate > best_hit_rate:
                    best_hit_rate = hit_rate
                    best_strategy = strategy_name
        
        return best_strategy


class SteeringCacheStrategyManager:
    """Steering 缓存策略管理器"""
    
    def __init__(self, strategy_type: CacheStrategy = CacheStrategy.SMART):
        self.strategy_type = strategy_type
        self.strategy = self._create_strategy(strategy_type)
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "cache_size": 0
        }
    
    def _create_strategy(self, strategy_type: CacheStrategy) -> CacheStrategyInterface:
        """创建缓存策略实例"""
        if strategy_type == CacheStrategy.LRU:
            return LRUCacheStrategy()
        elif strategy_type == CacheStrategy.TTL:
            return TTLCacheStrategy()
        elif strategy_type == CacheStrategy.SMART:
            return SmartCacheStrategy()
        elif strategy_type == CacheStrategy.LAYERED:
            return LayeredCacheStrategy()
        elif strategy_type == CacheStrategy.ADAPTIVE:
            return AdaptiveCacheStrategy()
        else:
            return LRUCacheStrategy()  # 默认策略
    
    def get(self, key: str, file_path: Optional[str] = None) -> Optional[Any]:
        """获取缓存项"""
        with self._lock:
            if key not in self._cache:
                self._stats["misses"] += 1
                if isinstance(self.strategy, AdaptiveCacheStrategy):
                    self.strategy.record_miss()
                return None
            
            entry = self._cache[key]
            
            # 检查是否应该淘汰
            cache_state = {
                "cache_size": len(self._cache),
                "file_path": file_path
            }
            
            if self.strategy.should_evict(entry, cache_state):
                del self._cache[key]
                self._stats["evictions"] += 1
                self._stats["misses"] += 1
                return None
            
            # 更新策略状态
            self.strategy.update_on_access(entry)
            self._stats["hits"] += 1
            
            return entry.data
    
    def put(self, key: str, data: Any, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """存储缓存项"""
        if metadata is None:
            metadata = {}
        
        with self._lock:
            # 检查是否应该缓存
            if not self.strategy.should_cache(key, data, metadata):
                return False
            
            # 创建缓存条目
            current_time = time.time()
            file_path = metadata.get("file_path")
            file_mtime = None
            
            if file_path:
                try:
                    file_mtime = os.path.getmtime(file_path)
                except (OSError, FileNotFoundError):
                    pass
            
            entry = CacheEntry(
                key=key,
                data=data,
                created_at=current_time,
                last_accessed=current_time,
                access_count=1,
                file_mtime=file_mtime,
                size_bytes=self._estimate_size(data),
                priority=metadata.get("priority", 0)
            )
            
            # 检查是否需要淘汰
            cache_state = {"cache_size": len(self._cache)}
            
            # 如果缓存已满，进行淘汰
            if len(self._cache) >= 1000:  # 默认最大缓存大小
                eviction_candidates = self.strategy.get_eviction_candidates(
                    self._cache, len(self._cache) // 4  # 淘汰 25%
                )
                
                for evict_key in eviction_candidates:
                    if evict_key in self._cache:
                        del self._cache[evict_key]
                        self._stats["evictions"] += 1
            
            # 存储新条目
            self._cache[key] = entry
            self._stats["cache_size"] = len(self._cache)
            
            return True
    
    def invalidate(self, key: Optional[str] = None):
        """使缓存失效"""
        with self._lock:
            if key:
                self._cache.pop(key, None)
            else:
                self._cache.clear()
            
            self._stats["cache_size"] = len(self._cache)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        with self._lock:
            total_requests = self._stats["hits"] + self._stats["misses"]
            hit_rate = self._stats["hits"] / total_requests if total_requests > 0 else 0.0
            
            return {
                "strategy_type": self.strategy_type.value,
                "cache_size": len(self._cache),
                "hits": self._stats["hits"],
                "misses": self._stats["misses"],
                "evictions": self._stats["evictions"],
                "hit_rate": hit_rate,
                "total_memory_estimate": sum(
                    entry.size_bytes for entry in self._cache.values()
                )
            }
    
    def _estimate_size(self, data: Any) -> int:
        """估算数据大小"""
        try:
            import sys
            return sys.getsizeof(data)
        except Exception:
            return 1024  # 默认 1KB


def create_cache_strategy_from_config(config: Dict[str, Any]) -> SteeringCacheStrategyManager:
    """根据配置创建缓存策略管理器"""
    strategy_name = config.get("strategy", "smart")
    
    try:
        strategy_type = CacheStrategy(strategy_name)
    except ValueError:
        logger.warning(f"未知的缓存策略: {strategy_name}，使用默认策略")
        strategy_type = CacheStrategy.SMART
    
    return SteeringCacheStrategyManager(strategy_type)