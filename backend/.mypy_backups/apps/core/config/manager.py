"""
统一配置管理器

提供配置的加载、验证、访问和管理功能。
"""

import os
import threading
import time
import weakref
import yaml
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, TypeVar, Generic, Union, Callable
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from .providers.base import ConfigProvider
from .schema.schema import ConfigSchema
from .validators.base import ConfigValidator, CompositeValidator, ValidationResult
from .exceptions import (
    ConfigException, ConfigNotFoundError, ConfigTypeError, 
    ConfigValidationError, ConfigFileError
)

T = TypeVar('T')


@dataclass
class CacheEntry:
    """缓存条目"""
    value: Any
    access_time: float = field(default_factory=time.time)
    access_count: int = 0
    
    def touch(self) -> None:
        """更新访问时间和次数"""
        self.access_time = time.time()
        self.access_count += 1


class ConfigCache:
    """配置缓存管理器"""
    
    def __init__(self, max_size: int = 1000, ttl: float = 3600.0):
        """
        初始化缓存
        
        Args:
            max_size: 最大缓存条目数
            ttl: 缓存生存时间（秒）
        """
        self.max_size = max_size
        self.ttl = ttl
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
    
    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值
        
        Args:
            key: 缓存键
            
        Returns:
            缓存值或 None
        """
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            
            # 检查是否过期
            if self.ttl > 0 and time.time() - entry.access_time > self.ttl:
                del self._cache[key]
                return None
            
            entry.touch()
            return entry.value
    
    def set(self, key: str, value: Any) -> None:
        """
        设置缓存值
        
        Args:
            key: 缓存键
            value: 缓存值
        """
        with self._lock:
            # 检查缓存大小限制
            if len(self._cache) >= self.max_size and key not in self._cache:
                self._evict_lru()
            
            self._cache[key] = CacheEntry(value)
    
    def delete(self, key: str) -> bool:
        """
        删除缓存项
        
        Args:
            key: 缓存键
            
        Returns:
            bool: 是否成功删除
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()
    
    def _evict_lru(self) -> None:
        """淘汰最少使用的缓存项"""
        if not self._cache:
            return
        
        # 找到访问时间最早的项
        lru_key = min(self._cache.keys(), 
                     key=lambda k: self._cache[k].access_time)
        del self._cache[lru_key]
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        with self._lock:
            total_access = sum(entry.access_count for entry in self._cache.values())
            return {
                'size': len(self._cache),
                'max_size': self.max_size,
                'ttl': self.ttl,
                'total_access': total_access,
                'keys': list(self._cache.keys())
            }
    
    def cleanup_expired(self) -> int:
        """
        清理过期缓存项
        
        Returns:
            int: 清理的项目数
        """
        if self.ttl <= 0:
            return 0
        
        with self._lock:
            current_time = time.time()
            expired_keys = [
                key for key, entry in self._cache.items()
                if current_time - entry.access_time > self.ttl
            ]
            
            for key in expired_keys:
                del self._cache[key]
            
            return len(expired_keys)


class ConfigChangeListener(ABC):
    """配置变更监听器接口"""
    
    @abstractmethod
    def on_config_changed(self, key: str, old_value: Any, new_value: Any) -> None:
        """
        配置变更回调
        
        Args:
            key: 变更的配置键
            old_value: 旧值
            new_value: 新值
        """
        pass
    
    def on_config_added(self, key: str, value: Any) -> None:
        """
        配置添加回调（可选实现）
        
        Args:
            key: 配置键
            value: 配置值
        """
        pass
    
    def on_config_removed(self, key: str, old_value: Any) -> None:
        """
        配置移除回调（可选实现）
        
        Args:
            key: 配置键
            old_value: 旧值
        """
        pass
    
    def on_config_reloaded(self) -> None:
        """
        配置重载完成回调（可选实现）
        """
        pass


@dataclass
class ConfigChangeEvent:
    """配置变更事件"""
    key: str
    old_value: Any
    new_value: Any
    change_type: str  # 'added', 'modified', 'removed'
    timestamp: float = field(default_factory=time.time)


class ConfigNotificationManager:
    """配置通知管理器"""
    
    def __init__(self):
        """初始化通知管理器"""
        self._listeners: List[ConfigChangeListener] = []
        self._key_listeners: Dict[str, List[ConfigChangeListener]] = {}
        self._prefix_listeners: Dict[str, List[ConfigChangeListener]] = {}
        self._event_history: List[ConfigChangeEvent] = []
        self._max_history = 100
        self._lock = threading.Lock()
    
    def add_listener(self, listener: ConfigChangeListener, 
                    key_filter: Optional[str] = None,
                    prefix_filter: Optional[str] = None) -> None:
        """
        添加监听器
        
        Args:
            listener: 监听器实例
            key_filter: 只监听特定键的变更
            prefix_filter: 只监听特定前缀的变更
        """
        with self._lock:
            if key_filter:
                if key_filter not in self._key_listeners:
                    self._key_listeners[key_filter] = []
                if listener not in self._key_listeners[key_filter]:
                    self._key_listeners[key_filter].append(listener)
            elif prefix_filter:
                if prefix_filter not in self._prefix_listeners:
                    self._prefix_listeners[prefix_filter] = []
                if listener not in self._prefix_listeners[prefix_filter]:
                    self._prefix_listeners[prefix_filter].append(listener)
            else:
                if listener not in self._listeners:
                    self._listeners.append(listener)
    
    def remove_listener(self, listener: ConfigChangeListener) -> None:
        """
        移除监听器
        
        Args:
            listener: 监听器实例
        """
        with self._lock:
            # 从全局监听器中移除
            if listener in self._listeners:
                self._listeners.remove(listener)
            
            # 从键监听器中移除
            for key_listeners in self._key_listeners.values():
                if listener in key_listeners:
                    key_listeners.remove(listener)
            
            # 从前缀监听器中移除
            for prefix_listeners in self._prefix_listeners.values():
                if listener in prefix_listeners:
                    prefix_listeners.remove(listener)
    
    def notify_change(self, key: str, old_value: Any, new_value: Any) -> None:
        """
        通知配置变更
        
        Args:
            key: 配置键
            old_value: 旧值
            new_value: 新值
        """
        # 确定变更类型
        if old_value is None and new_value is not None:
            change_type = 'added'
        elif old_value is not None and new_value is None:
            change_type = 'removed'
        else:
            change_type = 'modified'
        
        # 创建事件
        event = ConfigChangeEvent(key, old_value, new_value, change_type)
        
        with self._lock:
            # 添加到历史记录
            self._event_history.append(event)
            if len(self._event_history) > self._max_history:
                self._event_history.pop(0)
            
            # 收集需要通知的监听器
            listeners_to_notify = set()
            
            # 全局监听器
            listeners_to_notify.update(self._listeners)
            
            # 特定键监听器
            if key in self._key_listeners:
                listeners_to_notify.update(self._key_listeners[key])
            
            # 前缀监听器
            for prefix, prefix_listeners in self._prefix_listeners.items():
                if key.startswith(prefix):
                    listeners_to_notify.update(prefix_listeners)
        
        # 通知监听器（在锁外执行，避免死锁）
        for listener in listeners_to_notify:
            try:
                if change_type == 'added' and hasattr(listener, 'on_config_added'):
                    listener.on_config_added(key, new_value)
                elif change_type == 'removed' and hasattr(listener, 'on_config_removed'):
                    listener.on_config_removed(key, old_value)
                else:
                    listener.on_config_changed(key, old_value, new_value)
            except Exception as e:
                # 记录错误但不影响其他监听器
                print(f"配置变更通知失败 (key={key}, listener={listener.__class__.__name__}): {e}")
    
    def notify_reload(self) -> None:
        """通知配置重载完成"""
        with self._lock:
            listeners_to_notify = list(self._listeners)
            for key_listeners in self._key_listeners.values():
                listeners_to_notify.extend(key_listeners)
            for prefix_listeners in self._prefix_listeners.values():
                listeners_to_notify.extend(prefix_listeners)
        
        # 去重并通知
        for listener in set(listeners_to_notify):
            try:
                if hasattr(listener, 'on_config_reloaded'):
                    listener.on_config_reloaded()
            except Exception as e:
                print(f"配置重载通知失败 (listener={listener.__class__.__name__}): {e}")
    
    def get_event_history(self, limit: Optional[int] = None) -> List[ConfigChangeEvent]:
        """
        获取事件历史
        
        Args:
            limit: 限制返回的事件数量
            
        Returns:
            List[ConfigChangeEvent]: 事件历史列表
        """
        with self._lock:
            events = self._event_history.copy()
            if limit:
                events = events[-limit:]
            return events
    
    def clear_history(self) -> None:
        """清空事件历史"""
        with self._lock:
            self._event_history.clear()
    
    def get_listener_count(self) -> Dict[str, int]:
        """
        获取监听器统计
        
        Returns:
            Dict[str, int]: 监听器统计信息
        """
        with self._lock:
            return {
                'global': len(self._listeners),
                'key_specific': sum(len(listeners) for listeners in self._key_listeners.values()),
                'prefix_specific': sum(len(listeners) for listeners in self._prefix_listeners.values()),
                'total_keys': len(self._key_listeners),
                'total_prefixes': len(self._prefix_listeners)
            }


class ConfigFileWatcher(FileSystemEventHandler):
    """配置文件监控器"""
    
    def __init__(self, config_manager: 'ConfigManager', watched_files: List[str]):
        """
        初始化文件监控器
        
        Args:
            config_manager: 配置管理器实例
            watched_files: 监控的文件列表
        """
        self.config_manager = weakref.ref(config_manager)
        self.watched_files = set(os.path.abspath(f) for f in watched_files)
        self.last_reload_time = 0.0
        self.reload_debounce = 1.0  # 防抖时间（秒）
    
    def on_modified(self, event):
        """文件修改事件处理"""
        if event.is_directory:
            return
        
        file_path = os.path.abspath(event.src_path)
        if file_path not in self.watched_files:
            return
        
        # 防抖处理
        current_time = time.time()
        if current_time - self.last_reload_time < self.reload_debounce:
            return
        
        self.last_reload_time = current_time
        
        # 获取配置管理器实例
        manager = self.config_manager()
        if manager:
            try:
                manager.reload()
            except Exception as e:
                # 记录错误但不抛出异常
                print(f"配置热重载失败: {e}")


class HotReloadManager:
    """热重载管理器"""
    
    def __init__(self, config_manager: 'ConfigManager'):
        """
        初始化热重载管理器
        
        Args:
            config_manager: 配置管理器实例
        """
        self.config_manager = config_manager
        self.observer: Optional[Observer] = None
        self.watched_files: List[str] = []
        self.enabled = False
        self._lock = threading.Lock()
    
    def add_watch_file(self, file_path: str) -> None:
        """
        添加监控文件
        
        Args:
            file_path: 文件路径
        """
        with self._lock:
            abs_path = os.path.abspath(file_path)
            if abs_path not in self.watched_files:
                self.watched_files.append(abs_path)
                
                # 如果已经启动，重新配置监控
                if self.enabled and self.observer:
                    self._restart_observer()
    
    def remove_watch_file(self, file_path: str) -> None:
        """
        移除监控文件
        
        Args:
            file_path: 文件路径
        """
        with self._lock:
            abs_path = os.path.abspath(file_path)
            if abs_path in self.watched_files:
                self.watched_files.remove(abs_path)
                
                # 如果已经启动，重新配置监控
                if self.enabled and self.observer:
                    self._restart_observer()
    
    def start(self) -> None:
        """启动热重载监控"""
        with self._lock:
            if self.enabled or not self.watched_files:
                return
            
            try:
                self.observer = Observer()
                event_handler = ConfigFileWatcher(self.config_manager, self.watched_files)
                
                # 为每个文件的目录添加监控
                watched_dirs = set()
                for file_path in self.watched_files:
                    dir_path = os.path.dirname(file_path)
                    if dir_path not in watched_dirs:
                        self.observer.schedule(event_handler, dir_path, recursive=False)
                        watched_dirs.add(dir_path)
                
                self.observer.start()
                self.enabled = True
                
            except Exception as e:
                if self.observer:
                    self.observer.stop()
                    self.observer = None
                raise ConfigException(f"启动热重载监控失败: {e}")
    
    def stop(self) -> None:
        """停止热重载监控"""
        with self._lock:
            if not self.enabled or not self.observer:
                return
            
            try:
                self.observer.stop()
                self.observer.join(timeout=5.0)
                self.observer = None
                self.enabled = False
            except Exception as e:
                print(f"停止热重载监控时出错: {e}")
    
    def _restart_observer(self) -> None:
        """重启监控器"""
        if self.enabled:
            self.stop()
            self.start()
    
    def is_enabled(self) -> bool:
        """检查是否启用热重载"""
        return self.enabled
    
    def get_watched_files(self) -> List[str]:
        """获取监控文件列表"""
        with self._lock:
            return self.watched_files.copy()


class ConfigManager:
    """
    统一配置管理器
    
    负责从多个来源加载配置，提供统一的访问接口，支持配置验证、
    热重载和变更通知等功能。
    """
    
    def __init__(self, cache_max_size: int = 1000, cache_ttl: float = 3600.0):
        """
        初始化配置管理器
        
        Args:
            cache_max_size: 缓存最大条目数
            cache_ttl: 缓存生存时间（秒）
        """
        self._providers: List[ConfigProvider] = []
        self._cache = ConfigCache(cache_max_size, cache_ttl)
        self._raw_config: Dict[str, Any] = {}  # 原始配置数据
        self._schema: ConfigSchema = ConfigSchema()
        self._validator: ConfigValidator = CompositeValidator([])
        self._notification_manager = ConfigNotificationManager()
        self._lock = threading.RLock()
        self._loaded = False
        self._last_reload_time = 0.0
        self._hot_reload_manager = HotReloadManager(self)
        self._auto_reload_enabled = False
        
        # Steering 集成管理器（延迟初始化）
        self._steering_integration = None
        
    def add_provider(self, provider: ConfigProvider) -> None:
        """
        添加配置提供者
        
        Args:
            provider: 配置提供者实例
        """
        with self._lock:
            self._providers.append(provider)
            # 按优先级排序，优先级高的在前
            self._providers.sort(key=lambda p: p.priority, reverse=True)
    
    def remove_provider(self, provider_class: type) -> None:
        """
        移除指定类型的配置提供者
        
        Args:
            provider_class: 提供者类型
        """
        with self._lock:
            self._providers = [p for p in self._providers if not isinstance(p, provider_class)]
    
    def set_schema(self, schema: ConfigSchema) -> None:
        """
        设置配置模式
        
        Args:
            schema: 配置模式实例
        """
        with self._lock:
            self._schema = schema
    
    def set_validator(self, validator: ConfigValidator) -> None:
        """
        设置配置验证器
        
        Args:
            validator: 验证器实例
        """
        with self._lock:
            self._validator = validator
    
    def load(self, force_reload: bool = False) -> None:
        """
        加载配置
        
        Args:
            force_reload: 是否强制重新加载
            
        Raises:
            ConfigException: 配置加载失败
        """
        with self._lock:
            if self._loaded and not force_reload:
                return
            
            # 清空缓存
            old_raw_config = self._raw_config.copy()
            self._raw_config.clear()
            self._cache.clear()
            
            try:
                # 从所有提供者加载配置
                for provider in self._providers:
                    try:
                        provider_config = provider.load()
                        if provider_config:
                            self._merge_config(provider_config)
                            
                        # 如果提供者支持热重载，添加到监控列表
                        if provider.supports_reload() and hasattr(provider, 'get_file_path'):
                            file_path = provider.get_file_path()
                            if file_path and os.path.exists(file_path):
                                self._hot_reload_manager.add_watch_file(file_path)
                                
                    except Exception as e:
                        raise ConfigException(f"从 {provider.get_name()} 加载配置失败: {e}")
                
                # 验证配置
                self._validate_config()
                
                # 标记为已加载
                self._loaded = True
                self._last_reload_time = time.time()
                
                # 启动热重载（如果启用）
                if self._auto_reload_enabled and not self._hot_reload_manager.is_enabled():
                    try:
                        self._hot_reload_manager.start()
                    except Exception as e:
                        print(f"启动热重载失败: {e}")
                
                # 通知配置变更
                self._notify_changes(old_raw_config, self._raw_config)
                
                # 通知重载完成
                self._notification_manager.notify_reload()
                
            except Exception as e:
                # 恢复旧配置
                self._raw_config = old_raw_config
                self._cache.clear()
                raise e
    
    def _merge_config(self, config: Dict[str, Any], prefix: str = "") -> None:
        """
        合并配置到缓存中
        
        Args:
            config: 要合并的配置字典
            prefix: 键前缀
        """
        for key, value in config.items():
            full_key = f"{prefix}.{key}" if prefix else key
            
            if isinstance(value, dict):
                # 递归处理嵌套字典
                self._merge_config(value, full_key)
            else:
                # 直接设置值（高优先级覆盖低优先级）
                if full_key not in self._raw_config:
                    self._raw_config[full_key] = value
    
    def _validate_config(self) -> None:
        """
        验证配置
        
        Raises:
            ConfigValidationError: 验证失败
        """
        if self._schema:
            self._schema.validate_and_raise(self._raw_config)
        
        # 使用验证器进行额外验证
        if self._validator:
            for key, value in self._raw_config.items():
                field_def = self._schema.get_field(key) if self._schema else None
                result = self._validator.validate(key, value, field_def, self._raw_config)
                if not result.is_valid:
                    raise ConfigValidationError(result.errors)
    
    def get(self, key: str, default: T = None) -> T:
        """
        获取配置项
        
        Args:
            key: 配置键，支持点号路径访问
            default: 默认值
            
        Returns:
            配置值或默认值
            
        Raises:
            ConfigNotFoundError: 配置项不存在且无默认值
        """
        # 确保配置已加载
        if not self._loaded:
            self.load()
        
        with self._lock:
            # 先从缓存查找
            cached_value = self._cache.get(key)
            if cached_value is not None:
                return cached_value
            
            # 从原始配置查找
            if key in self._raw_config:
                value = self._raw_config[key]
                self._cache.set(key, value)
                return value
            
            # 尝试嵌套查找
            value = self._get_nested_value(key)
            if value is not None:
                self._cache.set(key, value)
                return value
            
            # 检查模式中是否有默认值
            if self._schema:
                field = self._schema.get_field(key)
                if field and field.default is not None:
                    return field.default
            
            # 返回传入的默认值
            if default is not None:
                return default
            
            # 生成建议并抛出异常
            suggestions = self._schema.get_suggestions(key) if self._schema else []
            raise ConfigNotFoundError(key, suggestions)
    
    def _get_nested_value(self, key: str) -> Any:
        """
        获取嵌套配置值
        
        Args:
            key: 点号分隔的键路径
            
        Returns:
            配置值或 None
        """
        keys = key.split('.')
        
        # 尝试从扁平化的原始配置中查找
        for i in range(len(keys)):
            partial_key = '.'.join(keys[:i+1])
            if partial_key in self._raw_config:
                if i == len(keys) - 1:
                    return self._raw_config[partial_key]
                # 继续查找更深层的键
                continue
        
        return None
    
    def get_typed(self, key: str, type_: type[T], default: T = None) -> T:
        """
        获取类型化的配置项
        
        Args:
            key: 配置键
            type_: 期望的类型
            default: 默认值
            
        Returns:
            类型化的配置值
            
        Raises:
            ConfigTypeError: 类型转换失败
        """
        value = self.get(key, default)
        
        if value is None:
            return value
        
        # 如果已经是期望类型，直接返回
        if isinstance(value, type_):
            return value
        
        # 尝试类型转换
        try:
            return self._convert_type(value, type_)
        except (ValueError, TypeError) as e:
            raise ConfigTypeError(key, type_, type(value)) from e
    
    def _convert_type(self, value: Any, target_type: type) -> Any:
        """
        类型转换
        
        Args:
            value: 原始值
            target_type: 目标类型
            
        Returns:
            转换后的值
            
        Raises:
            ValueError: 转换失败
        """
        if target_type == bool:
            if isinstance(value, str):
                return value.lower() in ('true', '1', 'yes', 'on')
            return bool(value)
        elif target_type == int:
            return int(value)
        elif target_type == float:
            return float(value)
        elif target_type == str:
            return str(value)
        elif target_type == list:
            if isinstance(value, str):
                # 简单的逗号分隔解析
                return [item.strip() for item in value.split(',') if item.strip()]
            return list(value)
        else:
            # 尝试直接转换
            return target_type(value)
    
    def set(self, key: str, value: Any) -> None:
        """
        设置配置项
        
        Args:
            key: 配置键
            value: 配置值
        """
        with self._lock:
            old_value = self._raw_config.get(key)
            self._raw_config[key] = value
            
            # 更新缓存
            self._cache.set(key, value)
            
            # 通知监听器
            self._notification_manager.notify_change(key, old_value, value)
    
    def has(self, key: str) -> bool:
        """
        检查配置项是否存在
        
        Args:
            key: 配置键
            
        Returns:
            bool: 是否存在
        """
        if not self._loaded:
            self.load()
        
        with self._lock:
            return key in self._raw_config or self._get_nested_value(key) is not None
    
    def get_all(self) -> Dict[str, Any]:
        """
        获取所有配置
        
        Returns:
            Dict[str, Any]: 所有配置的副本
        """
        if not self._loaded:
            self.load()
        
        with self._lock:
            return self._raw_config.copy()
    
    def get_by_prefix(self, prefix: str) -> Dict[str, Any]:
        """
        获取指定前缀的配置
        
        Args:
            prefix: 配置键前缀
            
        Returns:
            Dict[str, Any]: 匹配的配置字典
        """
        if not self._loaded:
            self.load()
        
        with self._lock:
            result = {}
            prefix_with_dot = f"{prefix}."
            
            for key, value in self._raw_config.items():
                if key.startswith(prefix_with_dot):
                    # 移除前缀
                    relative_key = key[len(prefix_with_dot):]
                    result[relative_key] = value
                elif key == prefix:
                    result[key] = value
            
            return result
    
    def reload(self) -> bool:
        """
        重新加载配置
        
        Returns:
            bool: 是否成功重载
        """
        try:
            self.load(force_reload=True)
            return True
        except Exception:
            return False
    
    def add_listener(self, listener: ConfigChangeListener, 
                    key_filter: Optional[str] = None,
                    prefix_filter: Optional[str] = None) -> None:
        """
        添加配置变更监听器
        
        Args:
            listener: 监听器实例
            key_filter: 只监听特定键的变更
            prefix_filter: 只监听特定前缀的变更
        """
        self._notification_manager.add_listener(listener, key_filter, prefix_filter)
    
    def remove_listener(self, listener: ConfigChangeListener) -> None:
        """
        移除配置变更监听器
        
        Args:
            listener: 监听器实例
        """
        self._notification_manager.remove_listener(listener)
    
    def _notify_changes(self, old_config: Dict[str, Any], new_config: Dict[str, Any]) -> None:
        """
        通知配置变更
        
        Args:
            old_config: 旧配置
            new_config: 新配置
        """
        # 找出变更的键
        all_keys = set(old_config.keys()) | set(new_config.keys())
        
        for key in all_keys:
            old_value = old_config.get(key)
            new_value = new_config.get(key)
            
            if old_value != new_value:
                self._notification_manager.notify_change(key, old_value, new_value)
    
    def is_loaded(self) -> bool:
        """
        检查配置是否已加载
        
        Returns:
            bool: 是否已加载
        """
        return self._loaded
    
    def get_last_reload_time(self) -> float:
        """
        获取最后重载时间
        
        Returns:
            float: 时间戳
        """
        return self._last_reload_time
    
    def get_provider_count(self) -> int:
        """
        获取提供者数量
        
        Returns:
            int: 提供者数量
        """
        return len(self._providers)
    
    def get_listener_count(self) -> Dict[str, int]:
        """
        获取监听器统计
        
        Returns:
            Dict[str, int]: 监听器统计信息
        """
        return self._notification_manager.get_listener_count()
    
    def get_change_history(self, limit: Optional[int] = None) -> List[ConfigChangeEvent]:
        """
        获取配置变更历史
        
        Args:
            limit: 限制返回的事件数量
            
        Returns:
            List[ConfigChangeEvent]: 变更历史
        """
        return self._notification_manager.get_event_history(limit)
    
    def clear_change_history(self) -> None:
        """清空配置变更历史"""
        self._notification_manager.clear_history()
    
    def clear_cache(self) -> None:
        """清空配置缓存"""
        with self._lock:
            self._cache.clear()
            self._loaded = False
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            Dict[str, Any]: 缓存统计信息
        """
        with self._lock:
            return self._cache.get_stats()
    
    def cleanup_cache(self) -> int:
        """
        清理过期缓存项
        
        Returns:
            int: 清理的项目数
        """
        with self._lock:
            return self._cache.cleanup_expired()
    
    def enable_auto_reload(self) -> None:
        """启用自动热重载"""
        with self._lock:
            self._auto_reload_enabled = True
            if self._loaded:
                try:
                    self._hot_reload_manager.start()
                except Exception as e:
                    raise ConfigException(f"启用自动热重载失败: {e}")
    
    def disable_auto_reload(self) -> None:
        """禁用自动热重载"""
        with self._lock:
            self._auto_reload_enabled = False
            self._hot_reload_manager.stop()
    
    def is_auto_reload_enabled(self) -> bool:
        """检查是否启用自动热重载"""
        return self._auto_reload_enabled
    
    def add_watch_file(self, file_path: str) -> None:
        """
        添加监控文件
        
        Args:
            file_path: 文件路径
        """
        self._hot_reload_manager.add_watch_file(file_path)
    
    def remove_watch_file(self, file_path: str) -> None:
        """
        移除监控文件
        
        Args:
            file_path: 文件路径
        """
        self._hot_reload_manager.remove_watch_file(file_path)
    
    def get_watched_files(self) -> List[str]:
        """
        获取监控文件列表
        
        Returns:
            List[str]: 监控文件列表
        """
        return self._hot_reload_manager.get_watched_files()
    
    def force_reload_from_file(self, file_path: str) -> bool:
        """
        强制从指定文件重新加载配置
        
        Args:
            file_path: 文件路径
            
        Returns:
            bool: 是否成功重载
        """
        try:
            # 找到对应的提供者
            for provider in self._providers:
                if (hasattr(provider, 'get_file_path') and 
                    provider.get_file_path() == file_path and 
                    provider.supports_reload()):
                    
                    # 重新加载该提供者的配置
                    with self._lock:
                        old_config = self._raw_config.copy()
                        
                        # 清除该提供者的配置
                        # 这里简化处理，实际应该只清除该提供者的配置
                        provider_config = provider.load()
                        if provider_config:
                            # 合并新配置
                            for key, value in provider_config.items():
                                self._raw_config[key] = value
                        
                        # 重新验证
                        self._validate_config()
                        
                        # 清空缓存
                        self._cache.clear()
                        
                        # 通知变更
                        self._notify_changes(old_config, self._raw_config)
                        
                        return True
            
            return False
            
        except Exception:
            return False
    
    def export(self, path: str, format: str = 'yaml', mask_sensitive: bool = True, 
               include_metadata: bool = True) -> None:
        """
        导出配置到文件
        
        Args:
            path: 导出文件路径
            format: 导出格式 ('yaml', 'json')
            mask_sensitive: 是否对敏感信息进行脱敏处理
            include_metadata: 是否包含元数据信息
            
        Raises:
            ConfigException: 导出失败
        """
        if not self._loaded:
            self.load()
        
        try:
            with self._lock:
                # 准备导出数据
                export_data = self._prepare_export_data(mask_sensitive, include_metadata)
                
                # 确保目录存在
                os.makedirs(os.path.dirname(path), exist_ok=True)
                
                # 根据格式导出
                if format.lower() == 'yaml':
                    self._export_yaml(path, export_data)
                elif format.lower() == 'json':
                    self._export_json(path, export_data)
                else:
                    raise ConfigException(f"不支持的导出格式: {format}")
                    
        except Exception as e:
            raise ConfigException(f"导出配置失败: {e}")
    
    def _prepare_export_data(self, mask_sensitive: bool, include_metadata: bool) -> Dict[str, Any]:
        """
        准备导出数据
        
        Args:
            mask_sensitive: 是否脱敏敏感信息
            include_metadata: 是否包含元数据
            
        Returns:
            Dict[str, Any]: 准备好的导出数据
        """
        export_data = {}
        
        # 添加元数据
        if include_metadata:
            export_data['_metadata'] = {
                'export_time': datetime.now().isoformat(),
                'config_manager_version': '1.0.0',
                'total_configs': len(self._raw_config),
                'masked_sensitive': mask_sensitive
            }
        
        # 处理配置数据
        config_data = {}
        for key, value in self._raw_config.items():
            # 检查是否为敏感配置
            is_sensitive = self._is_sensitive_config(key)
            
            if is_sensitive and mask_sensitive:
                # 脱敏处理
                config_data[key] = self._mask_sensitive_value(value)
            else:
                config_data[key] = value
        
        # 将扁平化的配置转换为嵌套结构
        export_data['config'] = self._flatten_to_nested(config_data)
        
        return export_data
    
    def _is_sensitive_config(self, key: str) -> bool:
        """
        检查配置项是否为敏感配置
        
        Args:
            key: 配置键
            
        Returns:
            bool: 是否为敏感配置
        """
        if self._schema:
            field = self._schema.get_field(key)
            if field and field.sensitive:
                return True
        
        # 基于键名的启发式判断
        sensitive_keywords = [
            'password', 'secret', 'key', 'token', 'credential',
            'private', 'auth', 'api_key', 'access_key'
        ]
        
        key_lower = key.lower()
        return any(keyword in key_lower for keyword in sensitive_keywords)
    
    def _mask_sensitive_value(self, value: Any) -> str:
        """
        对敏感值进行脱敏处理
        
        Args:
            value: 原始值
            
        Returns:
            str: 脱敏后的值
        """
        if value is None:
            return None
        
        str_value = str(value)
        if len(str_value) <= 4:
            return "***"
        elif len(str_value) <= 8:
            return str_value[:2] + "***" + str_value[-1:]
        else:
            return str_value[:3] + "***" + str_value[-2:]
    
    def _flatten_to_nested(self, flat_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        将扁平化配置转换为嵌套结构
        
        Args:
            flat_config: 扁平化的配置字典
            
        Returns:
            Dict[str, Any]: 嵌套结构的配置字典
        """
        nested = {}
        
        for key, value in flat_config.items():
            keys = key.split('.')
            current = nested
            
            # 构建嵌套结构
            for i, k in enumerate(keys[:-1]):
                if k not in current:
                    current[k] = {}
                current = current[k]
            
            # 设置最终值
            current[keys[-1]] = value
        
        return nested
    
    def _export_yaml(self, path: str, data: Dict[str, Any]) -> None:
        """
        导出为YAML格式
        
        Args:
            path: 文件路径
            data: 导出数据
        """
        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, 
                     sort_keys=False, indent=2)
    
    def _export_json(self, path: str, data: Dict[str, Any]) -> None:
        """
        导出为JSON格式
        
        Args:
            path: 文件路径
            data: 导出数据
        """
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=False)
    
    def import_config(self, path: str, format: Optional[str] = None, 
                     validate: bool = True, merge: bool = True) -> None:
        """
        从文件导入配置
        
        Args:
            path: 导入文件路径
            format: 文件格式 ('yaml', 'json')，如果为None则根据文件扩展名自动检测
            validate: 是否验证导入的配置
            merge: 是否与现有配置合并，False则完全替换
            
        Raises:
            ConfigException: 导入失败
            ConfigFileError: 文件读取失败
            ConfigValidationError: 配置验证失败
        """
        if not os.path.exists(path):
            raise ConfigFileError(path, message="文件不存在")
        
        try:
            # 自动检测格式
            if format is None:
                format = self._detect_file_format(path)
            
            # 读取文件数据
            import_data = self._load_import_file(path, format)
            
            # 验证导入数据结构
            self._validate_import_data(import_data)
            
            # 提取配置数据
            config_data = self._extract_config_data(import_data)
            
            # 验证配置完整性和有效性
            if validate:
                self._validate_imported_config(config_data)
            
            # 应用配置
            with self._lock:
                old_config = self._raw_config.copy()
                
                if merge:
                    # 合并配置
                    self._merge_imported_config(config_data)
                else:
                    # 完全替换配置
                    self._raw_config = config_data.copy()
                
                # 清空缓存
                self._cache.clear()
                
                # 重新验证整体配置
                if validate:
                    self._validate_config()
                
                # 通知配置变更
                self._notify_changes(old_config, self._raw_config)
                
        except Exception as e:
            if isinstance(e, (ConfigException, ConfigFileError, ConfigValidationError)):
                raise
            else:
                raise ConfigException(f"导入配置失败: {e}")
    
    def _detect_file_format(self, path: str) -> str:
        """
        根据文件扩展名检测格式
        
        Args:
            path: 文件路径
            
        Returns:
            str: 文件格式
        """
        ext = os.path.splitext(path)[1].lower()
        if ext in ['.yaml', '.yml']:
            return 'yaml'
        elif ext == '.json':
            return 'json'
        else:
            raise ConfigException(f"无法检测文件格式: {path}")
    
    def _load_import_file(self, path: str, format: str) -> Dict[str, Any]:
        """
        加载导入文件
        
        Args:
            path: 文件路径
            format: 文件格式
            
        Returns:
            Dict[str, Any]: 文件数据
        """
        try:
            with open(path, 'r', encoding='utf-8') as f:
                if format == 'yaml':
                    return yaml.safe_load(f) or {}
                elif format == 'json':
                    return json.load(f) or {}
                else:
                    raise ConfigException(f"不支持的文件格式: {format}")
        except yaml.YAMLError as e:
            raise ConfigFileError(path, message=f"YAML格式错误: {e}")
        except json.JSONDecodeError as e:
            raise ConfigFileError(path, line=e.lineno, message=f"JSON格式错误: {e.msg}")
        except Exception as e:
            raise ConfigFileError(path, message=f"文件读取失败: {e}")
    
    def _validate_import_data(self, data: Dict[str, Any]) -> None:
        """
        验证导入数据结构
        
        Args:
            data: 导入的数据
            
        Raises:
            ConfigValidationError: 数据结构无效
        """
        if not isinstance(data, dict):
            raise ConfigValidationError(["导入数据必须是字典格式"])
        
        # 检查是否包含配置数据
        if 'config' not in data and '_metadata' not in data:
            # 可能是直接的配置数据
            return
        
        if 'config' in data and not isinstance(data['config'], dict):
            raise ConfigValidationError(["配置数据必须是字典格式"])
    
    def _extract_config_data(self, import_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        从导入数据中提取配置
        
        Args:
            import_data: 导入的数据
            
        Returns:
            Dict[str, Any]: 扁平化的配置数据
        """
        if 'config' in import_data:
            # 标准格式，包含元数据
            config_data = import_data['config']
        else:
            # 直接的配置数据
            config_data = import_data
        
        # 将嵌套结构转换为扁平化
        return self._nested_to_flatten(config_data)
    
    def _nested_to_flatten(self, nested_config: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
        """
        将嵌套配置转换为扁平化结构
        
        Args:
            nested_config: 嵌套的配置字典
            prefix: 键前缀
            
        Returns:
            Dict[str, Any]: 扁平化的配置字典
        """
        flat_config = {}
        
        for key, value in nested_config.items():
            full_key = f"{prefix}.{key}" if prefix else key
            
            if isinstance(value, dict):
                # 递归处理嵌套字典
                flat_config.update(self._nested_to_flatten(value, full_key))
            else:
                flat_config[full_key] = value
        
        return flat_config
    
    def _validate_imported_config(self, config_data: Dict[str, Any]) -> None:
        """
        验证导入的配置
        
        Args:
            config_data: 配置数据
            
        Raises:
            ConfigValidationError: 验证失败
        """
        errors = []
        
        # 使用模式验证
        if self._schema:
            for key, value in config_data.items():
                field = self._schema.get_field(key)
                if field:
                    if not field.is_valid_value(value):
                        errors.append(f"配置项 '{key}' 值无效: {value}")
        
        # 使用验证器验证
        if self._validator:
            for key, value in config_data.items():
                field_def = self._schema.get_field(key) if self._schema else None
                result = self._validator.validate(key, value, field_def, config_data)
                if not result.is_valid:
                    errors.extend(result.errors)
        
        if errors:
            raise ConfigValidationError(errors)
    
    def _merge_imported_config(self, config_data: Dict[str, Any]) -> None:
        """
        合并导入的配置
        
        Args:
            config_data: 要合并的配置数据
        """
        for key, value in config_data.items():
            self._raw_config[key] = value
    
    def create_snapshot(self, name: Optional[str] = None, description: str = "") -> str:
        """
        创建配置快照
        
        Args:
            name: 快照名称，如果为None则自动生成
            description: 快照描述
            
        Returns:
            str: 快照ID
            
        Raises:
            ConfigException: 创建快照失败
        """
        if not self._loaded:
            self.load()
        
        try:
            # 生成快照ID和名称
            timestamp = datetime.now()
            snapshot_id = timestamp.strftime("%Y%m%d_%H%M%S")
            if name:
                snapshot_name = f"{snapshot_id}_{name}"
            else:
                snapshot_name = snapshot_id
            
            # 创建快照数据
            snapshot_data = {
                'id': snapshot_id,
                'name': snapshot_name,
                'description': description,
                'created_at': timestamp.isoformat(),
                'config_count': len(self._raw_config),
                'config': self._raw_config.copy()
            }
            
            # 确保快照目录存在
            snapshot_dir = self._get_snapshot_directory()
            os.makedirs(snapshot_dir, exist_ok=True)
            
            # 保存快照
            snapshot_path = os.path.join(snapshot_dir, f"{snapshot_name}.yaml")
            with open(snapshot_path, 'w', encoding='utf-8') as f:
                yaml.dump(snapshot_data, f, default_flow_style=False, 
                         allow_unicode=True, sort_keys=False, indent=2)
            
            return snapshot_id
            
        except Exception as e:
            raise ConfigException(f"创建配置快照失败: {e}")
    
    def restore_snapshot(self, snapshot_id: str, validate: bool = True) -> None:
        """
        从快照恢复配置
        
        Args:
            snapshot_id: 快照ID或名称
            validate: 是否验证恢复的配置
            
        Raises:
            ConfigException: 恢复失败
            ConfigFileError: 快照文件不存在
            ConfigValidationError: 配置验证失败
        """
        try:
            # 查找快照文件
            snapshot_path = self._find_snapshot_file(snapshot_id)
            if not snapshot_path:
                raise ConfigFileError(snapshot_id, message="快照不存在")
            
            # 加载快照数据
            with open(snapshot_path, 'r', encoding='utf-8') as f:
                snapshot_data = yaml.safe_load(f)
            
            # 验证快照数据
            self._validate_snapshot_data(snapshot_data)
            
            # 提取配置数据
            config_data = snapshot_data['config']
            
            # 验证配置
            if validate:
                self._validate_imported_config(config_data)
            
            # 恢复配置
            with self._lock:
                old_config = self._raw_config.copy()
                self._raw_config = config_data.copy()
                
                # 清空缓存
                self._cache.clear()
                
                # 重新验证整体配置
                if validate:
                    self._validate_config()
                
                # 通知配置变更
                self._notify_changes(old_config, self._raw_config)
                
        except Exception as e:
            if isinstance(e, (ConfigException, ConfigFileError, ConfigValidationError)):
                raise
            else:
                raise ConfigException(f"恢复配置快照失败: {e}")
    
    def list_snapshots(self) -> List[Dict[str, Any]]:
        """
        列出所有快照
        
        Returns:
            List[Dict[str, Any]]: 快照信息列表
        """
        snapshots = []
        snapshot_dir = self._get_snapshot_directory()
        
        if not os.path.exists(snapshot_dir):
            return snapshots
        
        try:
            for filename in os.listdir(snapshot_dir):
                if filename.endswith('.yaml'):
                    snapshot_path = os.path.join(snapshot_dir, filename)
                    try:
                        with open(snapshot_path, 'r', encoding='utf-8') as f:
                            snapshot_data = yaml.safe_load(f)
                        
                        # 提取快照信息
                        snapshot_info = {
                            'id': snapshot_data.get('id', ''),
                            'name': snapshot_data.get('name', ''),
                            'description': snapshot_data.get('description', ''),
                            'created_at': snapshot_data.get('created_at', ''),
                            'config_count': snapshot_data.get('config_count', 0),
                            'file_path': snapshot_path
                        }
                        snapshots.append(snapshot_info)
                        
                    except Exception:
                        # 忽略损坏的快照文件
                        continue
            
            # 按创建时间排序
            snapshots.sort(key=lambda x: x['created_at'], reverse=True)
            
        except Exception as e:
            raise ConfigException(f"列出快照失败: {e}")
        
        return snapshots
    
    def delete_snapshot(self, snapshot_id: str) -> bool:
        """
        删除快照
        
        Args:
            snapshot_id: 快照ID或名称
            
        Returns:
            bool: 是否成功删除
        """
        try:
            snapshot_path = self._find_snapshot_file(snapshot_id)
            if snapshot_path and os.path.exists(snapshot_path):
                os.remove(snapshot_path)
                return True
            return False
        except Exception:
            return False
    
    def _get_snapshot_directory(self) -> str:
        """
        获取快照目录路径
        
        Returns:
            str: 快照目录路径
        """
        # 默认在当前工作目录下的 .config_snapshots 目录
        return os.path.join(os.getcwd(), '.config_snapshots')
    
    def _find_snapshot_file(self, snapshot_id: str) -> Optional[str]:
        """
        查找快照文件
        
        Args:
            snapshot_id: 快照ID或名称
            
        Returns:
            Optional[str]: 快照文件路径，如果不存在则返回None
        """
        snapshot_dir = self._get_snapshot_directory()
        if not os.path.exists(snapshot_dir):
            return None
        
        # 尝试直接匹配文件名
        direct_path = os.path.join(snapshot_dir, f"{snapshot_id}.yaml")
        if os.path.exists(direct_path):
            return direct_path
        
        # 搜索包含ID的文件
        for filename in os.listdir(snapshot_dir):
            if filename.endswith('.yaml') and snapshot_id in filename:
                return os.path.join(snapshot_dir, filename)
        
        return None
    
    def _validate_snapshot_data(self, snapshot_data: Dict[str, Any]) -> None:
        """
        验证快照数据
        
        Args:
            snapshot_data: 快照数据
            
        Raises:
            ConfigValidationError: 快照数据无效
        """
        required_fields = ['id', 'name', 'created_at', 'config']
        errors = []
        
        for field in required_fields:
            if field not in snapshot_data:
                errors.append(f"快照数据缺少必需字段: {field}")
        
        if 'config' in snapshot_data and not isinstance(snapshot_data['config'], dict):
            errors.append("快照配置数据必须是字典格式")
        
        if errors:
            raise ConfigValidationError(errors)

    def __getitem__(self, key: str) -> Any:
        """支持字典式访问"""
        return self.get(key)
    
    def __setitem__(self, key: str, value: Any) -> None:
        """支持字典式设置"""
        self.set(key, value)
    
    def __contains__(self, key: str) -> bool:
        """支持 in 操作符"""
        return self.has(key)
    
    def __len__(self) -> int:
        """获取配置项数量"""
        if not self._loaded:
            self.load()
        return len(self._raw_config)
    
    def enable_steering_integration(self) -> None:
        """启用 Steering 系统集成"""
        if self._steering_integration is None:
            try:
                from .steering_integration import SteeringIntegrationManager
                self._steering_integration = SteeringIntegrationManager(self)
                logger.info("Steering 系统集成已启用")
            except ImportError as e:
                logger.warning(f"无法启用 Steering 集成: {e}")
    
    def get_steering_integration(self):
        """获取 Steering 集成管理器"""
        if self._steering_integration is None:
            self.enable_steering_integration()
        return self._steering_integration
    
    def load_steering_specifications(self, target_file_path: str) -> List[Any]:
        """为指定文件加载 Steering 规范"""
        integration = self.get_steering_integration()
        if integration:
            return integration.load_specifications_for_file(target_file_path)
        return []