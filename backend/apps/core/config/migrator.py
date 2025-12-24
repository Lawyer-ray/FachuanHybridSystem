"""
配置迁移器

负责将现有的 Django settings 配置迁移到统一配置管理系统，
提供向后兼容接口和迁移状态跟踪功能。
"""

import os
import json
import yaml
import shutil
import importlib
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum

from django.conf import settings as django_settings
from django.core.exceptions import ImproperlyConfigured

from .manager import ConfigManager
from .schema.schema import ConfigSchema
from .schema.field import ConfigField
from .exceptions import ConfigException, ConfigValidationError, ConfigFileError
from .migration_tracker import MigrationStateTracker, MigrationEventType


class MigrationStatus(Enum):
    """迁移状态枚举"""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class MigrationStep:
    """迁移步骤"""
    name: str
    description: str
    status: MigrationStatus = MigrationStatus.NOT_STARTED
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    def start(self) -> None:
        """开始步骤"""
        self.status = MigrationStatus.IN_PROGRESS
        self.started_at = datetime.now()
        self.error_message = None
    
    def complete(self) -> None:
        """完成步骤"""
        self.status = MigrationStatus.COMPLETED
        self.completed_at = datetime.now()
    
    def fail(self, error_message: str) -> None:
        """失败步骤"""
        self.status = MigrationStatus.FAILED
        self.error_message = error_message
        self.completed_at = datetime.now()


@dataclass
class MigrationLog:
    """迁移日志"""
    migration_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: MigrationStatus = MigrationStatus.NOT_STARTED
    steps: List[MigrationStep] = field(default_factory=list)
    total_configs: int = 0
    migrated_configs: int = 0
    error_message: Optional[str] = None
    rollback_available: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'migration_id': self.migration_id,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'status': self.status.value,
            'steps': [
                {
                    'name': step.name,
                    'description': step.description,
                    'status': step.status.value,
                    'error_message': step.error_message,
                    'started_at': step.started_at.isoformat() if step.started_at else None,
                    'completed_at': step.completed_at.isoformat() if step.completed_at else None,
                }
                for step in self.steps
            ],
            'total_configs': self.total_configs,
            'migrated_configs': self.migrated_configs,
            'error_message': self.error_message,
            'rollback_available': self.rollback_available,
        }


class DjangoSettingsCompatibilityLayer:
    """Django Settings 兼容层"""
    
    def __init__(self, config_manager: ConfigManager):
        """
        初始化兼容层
        
        Args:
            config_manager: 配置管理器实例
        """
        self.config_manager = config_manager
        self._django_to_config_mapping = self._build_mapping()
    
    def _build_mapping(self) -> Dict[str, str]:
        """
        构建 Django settings 到统一配置的映射
        
        Returns:
            Dict[str, str]: 映射字典
        """
        return {
            # Django 核心配置
            'SECRET_KEY': 'django.secret_key',
            'DEBUG': 'django.debug',
            'ALLOWED_HOSTS': 'django.allowed_hosts',
            
            # 数据库配置
            'DATABASES': 'database',
            
            # 国际化配置
            'LANGUAGE_CODE': 'django.language_code',
            'TIME_ZONE': 'django.time_zone',
            'USE_I18N': 'django.use_i18n',
            'USE_TZ': 'django.use_tz',
            
            # 静态文件配置
            'STATIC_URL': 'django.static_url',
            'MEDIA_URL': 'django.media_url',
            'MEDIA_ROOT': 'django.media_root',
            
            # CORS 配置
            'CORS_ALLOW_ALL_ORIGINS': 'cors.allow_all_origins',
            'CORS_ALLOWED_ORIGINS': 'cors.allowed_origins',
            'CORS_ALLOW_CREDENTIALS': 'cors.allow_credentials',
            'CSRF_TRUSTED_ORIGINS': 'cors.csrf_trusted_origins',
            
            # 第三方服务配置
            'MOONSHOT_BASE_URL': 'services.moonshot.base_url',
            'MOONSHOT_API_KEY': 'services.moonshot.api_key',
            'OLLAMA': 'services.ollama',
            
            # 群聊平台配置
            'FEISHU': 'chat_platforms.feishu',
            'DINGTALK': 'chat_platforms.dingtalk',
            'WECHAT_WORK': 'chat_platforms.wechat_work',
            'TELEGRAM': 'chat_platforms.telegram',
            'SLACK': 'chat_platforms.slack',
            
            # 业务功能配置
            'CASE_CHAT': 'features.case_chat',
            'COURT_SMS_PROCESSING': 'features.court_sms',
            'DOCUMENT_PROCESSING': 'features.document_processing',
            
            # 性能配置
            'Q_CLUSTER': 'performance.q_cluster',
            'RATE_LIMIT': 'performance.rate_limit',
            'CACHES': 'performance.cache',
            
            # 其他配置
            'SCRAPER_ENCRYPTION_KEY': 'security.scraper_encryption_key',
            'PERM_OPEN_ACCESS': 'security.perm_open_access',
        }
    
    def get_config_value(self, django_key: str, default: Any = None) -> Any:
        """
        获取配置值（兼容 Django settings 访问方式）
        
        Args:
            django_key: Django 配置键
            default: 默认值
            
        Returns:
            配置值
        """
        # 首先尝试从统一配置获取
        if django_key in self._django_to_config_mapping:
            config_key = self._django_to_config_mapping[django_key]
            try:
                return self.config_manager.get(config_key, default)
            except Exception:
                pass
        
        # 回退到 Django settings
        return getattr(django_settings, django_key, default)
    
    def has_config(self, django_key: str) -> bool:
        """
        检查配置是否存在
        
        Args:
            django_key: Django 配置键
            
        Returns:
            bool: 是否存在
        """
        # 检查统一配置
        if django_key in self._django_to_config_mapping:
            config_key = self._django_to_config_mapping[django_key]
            if self.config_manager.has(config_key):
                return True
        
        # 检查 Django settings
        return hasattr(django_settings, django_key)
    
    def set_config_value(self, django_key: str, value: Any) -> None:
        """
        设置配置值
        
        Args:
            django_key: Django 配置键
            value: 配置值
        """
        if django_key in self._django_to_config_mapping:
            config_key = self._django_to_config_mapping[django_key]
            self.config_manager.set(config_key, value)
        else:
            # 设置到 Django settings（如果可能）
            setattr(django_settings, django_key, value)
    
    def get_all_django_configs(self) -> Dict[str, Any]:
        """
        获取所有 Django 配置
        
        Returns:
            Dict[str, Any]: Django 配置字典
        """
        configs = {}
        
        # 获取所有 Django settings 属性
        for attr_name in dir(django_settings):
            if not attr_name.startswith('_') and attr_name.isupper():
                try:
                    configs[attr_name] = getattr(django_settings, attr_name)
                except Exception:
                    # 忽略无法获取的属性
                    continue
        
        return configs


class ConfigMigrator:
    """
    配置迁移器
    
    负责将现有的 Django settings 配置迁移到统一配置管理系统。
    """
    
    def __init__(self, config_manager: ConfigManager, 
                 backup_dir: Optional[str] = None,
                 enable_auto_rollback: bool = True):
        """
        初始化配置迁移器
        
        Args:
            config_manager: 配置管理器实例
            backup_dir: 备份目录路径
            enable_auto_rollback: 是否启用自动回滚
        """
        self.config_manager = config_manager
        self.backup_dir = backup_dir or self._get_default_backup_dir()
        self.compatibility_layer = DjangoSettingsCompatibilityLayer(config_manager)
        self._migration_logs: List[MigrationLog] = []
        self._current_migration: Optional[MigrationLog] = None
        self.enable_auto_rollback = enable_auto_rollback
        
        # 初始化状态跟踪器
        self.tracker = MigrationStateTracker(
            db_path=os.path.join(self.backup_dir, 'migration_tracker.db'),
            log_file=os.path.join(self.backup_dir, 'migration.log')
        )
        
        # 回滚相关状态
        self._rollback_points: Dict[str, Dict[str, Any]] = {}
        self._rollback_stack: List[Tuple[str, str, Any, Any]] = []  # (migration_id, key, old_value, new_value)
        
        # 确保备份目录存在
        os.makedirs(self.backup_dir, exist_ok=True)
    
    def _get_default_backup_dir(self) -> str:
        """
        获取默认备份目录
        
        Returns:
            str: 备份目录路径
        """
        return os.path.join(os.getcwd(), '.config_migration_backups')
    
    def start_migration(self, migration_id: Optional[str] = None) -> str:
        """
        开始配置迁移
        
        Args:
            migration_id: 迁移ID，如果为None则自动生成
            
        Returns:
            str: 迁移ID
            
        Raises:
            ConfigException: 迁移启动失败
        """
        if self._current_migration and self._current_migration.status == MigrationStatus.IN_PROGRESS:
            raise ConfigException("已有迁移正在进行中")
        
        # 生成迁移ID
        if migration_id is None:
            migration_id = datetime.now().strftime("migration_%Y%m%d_%H%M%S")
        
        # 创建迁移日志
        self._current_migration = MigrationLog(
            migration_id=migration_id,
            started_at=datetime.now(),
            status=MigrationStatus.IN_PROGRESS
        )
        
        # 定义迁移步骤
        steps = [
            MigrationStep("backup_current_config", "备份当前配置"),
            MigrationStep("analyze_django_settings", "分析 Django Settings"),
            MigrationStep("create_config_schema", "创建配置模式"),
            MigrationStep("migrate_core_configs", "迁移核心配置"),
            MigrationStep("migrate_service_configs", "迁移服务配置"),
            MigrationStep("migrate_business_configs", "迁移业务配置"),
            MigrationStep("validate_migrated_config", "验证迁移后的配置"),
            MigrationStep("create_compatibility_layer", "创建兼容层"),
        ]
        
        self._current_migration.steps = steps
        self._migration_logs.append(self._current_migration)
        
        return migration_id
    
    def execute_migration(self) -> bool:
        """
        执行配置迁移
        
        Returns:
            bool: 是否成功
        """
        if not self._current_migration:
            raise ConfigException("未开始迁移，请先调用 start_migration()")
        
        migration_id = self._current_migration.migration_id
        
        try:
            # 开始跟踪迁移
            self.tracker.start_migration(
                migration_id, 
                len(self._current_migration.steps),
                self._current_migration.total_configs
            )
            
            # 创建初始回滚点
            self.create_rollback_point(migration_id, "migration_start")
            
            # 执行各个迁移步骤
            for step in self._current_migration.steps:
                step.start()
                self.tracker.start_step(migration_id, step.name, step.description)
                
                try:
                    if step.name == "backup_current_config":
                        self._backup_current_config()
                    elif step.name == "analyze_django_settings":
                        self._analyze_django_settings()
                    elif step.name == "create_config_schema":
                        self._create_config_schema()
                    elif step.name == "migrate_core_configs":
                        self._migrate_core_configs()
                    elif step.name == "migrate_service_configs":
                        self._migrate_service_configs()
                    elif step.name == "migrate_business_configs":
                        self._migrate_business_configs()
                    elif step.name == "validate_migrated_config":
                        self._validate_migrated_config()
                    elif step.name == "create_compatibility_layer":
                        self._create_compatibility_layer()
                    
                    step.complete()
                    self.tracker.complete_step(migration_id, step.name)
                    
                except Exception as e:
                    step.fail(str(e))
                    self.tracker.fail_step(migration_id, step.name, str(e))
                    
                    # 如果启用自动回滚，尝试回滚
                    if self.enable_auto_rollback:
                        self.auto_rollback_on_error(migration_id, e)
                    
                    raise e
            
            # 迁移完成
            self._current_migration.status = MigrationStatus.COMPLETED
            self._current_migration.completed_at = datetime.now()
            self._current_migration.rollback_available = True
            
            # 完成跟踪
            self.tracker.complete_migration(migration_id, self._current_migration.migrated_configs)
            
            # 保存迁移日志
            self._save_migration_log()
            
            return True
            
        except Exception as e:
            # 迁移失败
            self._current_migration.status = MigrationStatus.FAILED
            self._current_migration.error_message = str(e)
            self._current_migration.completed_at = datetime.now()
            
            # 失败跟踪
            self.tracker.fail_migration(migration_id, str(e))
            
            # 保存迁移日志
            self._save_migration_log()
            
            return False
    
    def _backup_current_config(self) -> None:
        """备份当前配置"""
        backup_data = {
            'backup_time': datetime.now().isoformat(),
            'django_settings': self.compatibility_layer.get_all_django_configs(),
            'config_manager_data': self.config_manager.get_all() if self.config_manager.is_loaded() else {}
        }
        
        backup_file = os.path.join(
            self.backup_dir, 
            f"{self._current_migration.migration_id}_backup.json"
        )
        
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2, default=str)
    
    def _analyze_django_settings(self) -> None:
        """分析 Django Settings"""
        django_configs = self.compatibility_layer.get_all_django_configs()
        self._current_migration.total_configs = len(django_configs)
        
        # 分析配置类型和结构
        analysis = {
            'total_configs': len(django_configs),
            'config_types': {},
            'sensitive_configs': [],
            'complex_configs': []
        }
        
        for key, value in django_configs.items():
            # 分析配置类型
            config_type = type(value).__name__
            analysis['config_types'][config_type] = analysis['config_types'].get(config_type, 0) + 1
            
            # 识别敏感配置
            if self._is_sensitive_config_key(key):
                analysis['sensitive_configs'].append(key)
            
            # 识别复杂配置
            if isinstance(value, (dict, list)) and len(str(value)) > 100:
                analysis['complex_configs'].append(key)
        
        # 保存分析结果
        analysis_file = os.path.join(
            self.backup_dir,
            f"{self._current_migration.migration_id}_analysis.json"
        )
        
        with open(analysis_file, 'w', encoding='utf-8') as f:
            json.dump(analysis, f, ensure_ascii=False, indent=2, default=str)
    
    def _is_sensitive_config_key(self, key: str) -> bool:
        """
        检查配置键是否为敏感配置
        
        Args:
            key: 配置键
            
        Returns:
            bool: 是否为敏感配置
        """
        sensitive_keywords = [
            'SECRET', 'KEY', 'PASSWORD', 'TOKEN', 'CREDENTIAL',
            'PRIVATE', 'AUTH', 'API_KEY', 'ACCESS_KEY'
        ]
        
        key_upper = key.upper()
        return any(keyword in key_upper for keyword in sensitive_keywords)
    
    def _create_config_schema(self) -> None:
        """创建配置模式"""
        schema = ConfigSchema()
        
        # 注册 Django 核心配置字段
        self._register_django_core_fields(schema)
        
        # 注册服务配置字段
        self._register_service_fields(schema)
        
        # 注册业务配置字段
        self._register_business_fields(schema)
        
        # 设置到配置管理器
        self.config_manager.set_schema(schema)
    
    def _register_django_core_fields(self, schema: ConfigSchema) -> None:
        """注册 Django 核心配置字段"""
        # Django 核心配置
        schema.register(ConfigField(
            name="django.secret_key",
            type=str,
            required=True,
            sensitive=True,
            description="Django 密钥",
            env_var="DJANGO_SECRET_KEY"
        ))
        
        schema.register(ConfigField(
            name="django.debug",
            type=bool,
            default=False,
            description="调试模式",
            env_var="DJANGO_DEBUG"
        ))
        
        schema.register(ConfigField(
            name="django.allowed_hosts",
            type=list,
            default=["localhost"],
            description="允许的主机列表",
            env_var="DJANGO_ALLOWED_HOSTS"
        ))
        
        # 数据库配置
        schema.register(ConfigField(
            name="database.engine",
            type=str,
            default="django.db.backends.sqlite3",
            description="数据库引擎"
        ))
        
        schema.register(ConfigField(
            name="database.name",
            type=str,
            required=True,
            description="数据库名称",
            env_var="DB_NAME"
        ))
    
    def _register_service_fields(self, schema: ConfigSchema) -> None:
        """注册服务配置字段"""
        # Moonshot AI 配置
        schema.register(ConfigField(
            name="services.moonshot.base_url",
            type=str,
            default="https://api.moonshot.cn/v1",
            description="Moonshot API 基础URL",
            env_var="MOONSHOT_BASE_URL"
        ))
        
        schema.register(ConfigField(
            name="services.moonshot.api_key",
            type=str,
            required=True,
            sensitive=True,
            description="Moonshot API 密钥",
            env_var="MOONSHOT_API_KEY"
        ))
        
        # Ollama 配置
        schema.register(ConfigField(
            name="services.ollama.model",
            type=str,
            default="qwen2.5:7b",
            description="Ollama 模型名称",
            env_var="OLLAMA_MODEL"
        ))
        
        schema.register(ConfigField(
            name="services.ollama.base_url",
            type=str,
            default="http://localhost:11434",
            description="Ollama 基础URL",
            env_var="OLLAMA_BASE_URL"
        ))
    
    def _register_business_fields(self, schema: ConfigSchema) -> None:
        """注册业务配置字段"""
        # 飞书配置
        schema.register(ConfigField(
            name="chat_platforms.feishu.app_id",
            type=str,
            required=True,
            sensitive=True,
            description="飞书应用ID",
            env_var="FEISHU_APP_ID"
        ))
        
        schema.register(ConfigField(
            name="chat_platforms.feishu.app_secret",
            type=str,
            required=True,
            sensitive=True,
            description="飞书应用密钥",
            env_var="FEISHU_APP_SECRET"
        ))
        
        schema.register(ConfigField(
            name="chat_platforms.feishu.timeout",
            type=int,
            default=30,
            min_value=1,
            max_value=300,
            description="飞书API超时时间(秒)",
            env_var="FEISHU_TIMEOUT"
        ))
        
        # 案件群聊配置
        schema.register(ConfigField(
            name="features.case_chat.default_platform",
            type=str,
            default="feishu",
            description="默认群聊平台"
        ))
        
        schema.register(ConfigField(
            name="features.case_chat.auto_create_on_push",
            type=bool,
            default=True,
            description="推送时自动创建群聊"
        ))
    
    def _migrate_core_configs(self) -> None:
        """迁移核心配置"""
        django_configs = self.compatibility_layer.get_all_django_configs()
        migrated_count = 0
        
        # Django 核心配置映射
        core_mappings = {
            'SECRET_KEY': 'django.secret_key',
            'DEBUG': 'django.debug',
            'ALLOWED_HOSTS': 'django.allowed_hosts',
            'LANGUAGE_CODE': 'django.language_code',
            'TIME_ZONE': 'django.time_zone',
        }
        
        for django_key, config_key in core_mappings.items():
            if django_key in django_configs:
                value = django_configs[django_key]
                old_value = self.config_manager.get(config_key) if self.config_manager.has(config_key) else None
                self.config_manager.set(config_key, value)
                self._track_config_change(self._current_migration.migration_id, config_key, old_value, value)
                migrated_count += 1
        
        # 数据库配置特殊处理
        if 'DATABASES' in django_configs:
            databases = django_configs['DATABASES']
            if 'default' in databases:
                db_config = databases['default']
                
                # 迁移数据库引擎
                engine_key = 'database.engine'
                old_engine = self.config_manager.get(engine_key) if self.config_manager.has(engine_key) else None
                new_engine = db_config.get('ENGINE')
                self.config_manager.set(engine_key, new_engine)
                self._track_config_change(self._current_migration.migration_id, engine_key, old_engine, new_engine)
                
                # 迁移数据库名称
                name_key = 'database.name'
                old_name = self.config_manager.get(name_key) if self.config_manager.has(name_key) else None
                new_name = db_config.get('NAME')
                self.config_manager.set(name_key, new_name)
                self._track_config_change(self._current_migration.migration_id, name_key, old_name, new_name)
                
                # 迁移数据库主机
                host_key = 'database.host'
                old_host = self.config_manager.get(host_key) if self.config_manager.has(host_key) else None
                new_host = db_config.get('HOST', 'localhost')
                self.config_manager.set(host_key, new_host)
                self._track_config_change(self._current_migration.migration_id, host_key, old_host, new_host)
                
                # 迁移数据库端口
                port_key = 'database.port'
                old_port = self.config_manager.get(port_key) if self.config_manager.has(port_key) else None
                new_port = db_config.get('PORT', 3306)
                self.config_manager.set(port_key, new_port)
                self._track_config_change(self._current_migration.migration_id, port_key, old_port, new_port)
                
                migrated_count += 1
        
        self._current_migration.migrated_configs += migrated_count
    
    def _migrate_service_configs(self) -> None:
        """迁移服务配置"""
        django_configs = self.compatibility_layer.get_all_django_configs()
        migrated_count = 0
        
        # Moonshot 配置
        if 'MOONSHOT_BASE_URL' in django_configs:
            config_key = 'services.moonshot.base_url'
            old_value = self.config_manager.get(config_key) if self.config_manager.has(config_key) else None
            new_value = django_configs['MOONSHOT_BASE_URL']
            self.config_manager.set(config_key, new_value)
            self._track_config_change(self._current_migration.migration_id, config_key, old_value, new_value)
            migrated_count += 1
        
        if 'MOONSHOT_API_KEY' in django_configs:
            config_key = 'services.moonshot.api_key'
            old_value = self.config_manager.get(config_key) if self.config_manager.has(config_key) else None
            new_value = django_configs['MOONSHOT_API_KEY']
            self.config_manager.set(config_key, new_value)
            self._track_config_change(self._current_migration.migration_id, config_key, old_value, new_value)
            migrated_count += 1
        
        # Ollama 配置
        if 'OLLAMA' in django_configs:
            ollama_config = django_configs['OLLAMA']
            if isinstance(ollama_config, dict):
                if 'MODEL' in ollama_config:
                    config_key = 'services.ollama.model'
                    old_value = self.config_manager.get(config_key) if self.config_manager.has(config_key) else None
                    new_value = ollama_config['MODEL']
                    self.config_manager.set(config_key, new_value)
                    self._track_config_change(self._current_migration.migration_id, config_key, old_value, new_value)
                
                if 'BASE_URL' in ollama_config:
                    config_key = 'services.ollama.base_url'
                    old_value = self.config_manager.get(config_key) if self.config_manager.has(config_key) else None
                    new_value = ollama_config['BASE_URL']
                    self.config_manager.set(config_key, new_value)
                    self._track_config_change(self._current_migration.migration_id, config_key, old_value, new_value)
                
                migrated_count += 1
        
        self._current_migration.migrated_configs += migrated_count
    
    def _migrate_business_configs(self) -> None:
        """迁移业务配置"""
        django_configs = self.compatibility_layer.get_all_django_configs()
        migrated_count = 0
        
        # 飞书配置
        if 'FEISHU' in django_configs:
            feishu_config = django_configs['FEISHU']
            if isinstance(feishu_config, dict):
                for key, value in feishu_config.items():
                    config_key = f"chat_platforms.feishu.{key.lower()}"
                    old_value = self.config_manager.get(config_key) if self.config_manager.has(config_key) else None
                    self.config_manager.set(config_key, value)
                    self._track_config_change(self._current_migration.migration_id, config_key, old_value, value)
                migrated_count += 1
        
        # 案件群聊配置
        if 'CASE_CHAT' in django_configs:
            case_chat_config = django_configs['CASE_CHAT']
            if isinstance(case_chat_config, dict):
                for key, value in case_chat_config.items():
                    config_key = f"features.case_chat.{key.lower()}"
                    old_value = self.config_manager.get(config_key) if self.config_manager.has(config_key) else None
                    self.config_manager.set(config_key, value)
                    self._track_config_change(self._current_migration.migration_id, config_key, old_value, value)
                migrated_count += 1
        
        # 法院短信配置
        if 'COURT_SMS_PROCESSING' in django_configs:
            sms_config = django_configs['COURT_SMS_PROCESSING']
            if isinstance(sms_config, dict):
                for key, value in sms_config.items():
                    config_key = f"features.court_sms.{key.lower()}"
                    old_value = self.config_manager.get(config_key) if self.config_manager.has(config_key) else None
                    self.config_manager.set(config_key, value)
                    self._track_config_change(self._current_migration.migration_id, config_key, old_value, value)
                migrated_count += 1
        
        self._current_migration.migrated_configs += migrated_count
    
    def _validate_migrated_config(self) -> None:
        """验证迁移后的配置"""
        # 重新加载配置以触发验证
        self.config_manager.load(force_reload=True)
        
        # 检查关键配置是否存在
        required_configs = [
            'django.secret_key',
            'django.debug',
            'django.allowed_hosts'
        ]
        
        missing_configs = []
        for config_key in required_configs:
            if not self.config_manager.has(config_key):
                missing_configs.append(config_key)
        
        if missing_configs:
            raise ConfigValidationError(f"缺少必需的配置项: {', '.join(missing_configs)}")
    
    def _create_compatibility_layer(self) -> None:
        """创建兼容层"""
        # 兼容层已在初始化时创建，这里可以进行额外的设置
        pass
    
    def _save_migration_log(self) -> None:
        """保存迁移日志"""
        if not self._current_migration:
            return
        
        log_file = os.path.join(
            self.backup_dir,
            f"{self._current_migration.migration_id}_log.json"
        )
        
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(self._current_migration.to_dict(), f, ensure_ascii=False, indent=2)
    
    def rollback_migration(self, migration_id: str) -> bool:
        """
        回滚迁移
        
        Args:
            migration_id: 迁移ID
            
        Returns:
            bool: 是否成功回滚
        """
        try:
            # 查找备份文件
            backup_file = os.path.join(self.backup_dir, f"{migration_id}_backup.json")
            if not os.path.exists(backup_file):
                raise ConfigException(f"找不到迁移备份文件: {backup_file}")
            
            # 加载备份数据
            with open(backup_file, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)
            
            # 恢复 Django settings（这里只能恢复部分）
            django_configs = backup_data.get('django_settings', {})
            
            # 恢复配置管理器数据
            config_data = backup_data.get('config_manager_data', {})
            if config_data:
                # 清空当前配置
                self.config_manager.clear_cache()
                
                # 恢复配置
                for key, value in config_data.items():
                    self.config_manager.set(key, value)
            
            # 更新迁移状态
            for migration_log in self._migration_logs:
                if migration_log.migration_id == migration_id:
                    migration_log.status = MigrationStatus.ROLLED_BACK
                    migration_log.completed_at = datetime.now()
                    self._save_migration_log()
                    break
            
            return True
            
        except Exception as e:
            print(f"回滚迁移失败: {e}")
            return False
    
    def get_migration_status(self, migration_id: Optional[str] = None) -> Optional[MigrationLog]:
        """
        获取迁移状态
        
        Args:
            migration_id: 迁移ID，如果为None则返回当前迁移
            
        Returns:
            Optional[MigrationLog]: 迁移日志
        """
        if migration_id is None:
            return self._current_migration
        
        for migration_log in self._migration_logs:
            if migration_log.migration_id == migration_id:
                return migration_log
        
        return None
    
    def list_migrations(self) -> List[MigrationLog]:
        """
        列出所有迁移
        
        Returns:
            List[MigrationLog]: 迁移日志列表
        """
        return self._migration_logs.copy()
    
    def get_compatibility_layer(self) -> DjangoSettingsCompatibilityLayer:
        """
        获取兼容层
        
        Returns:
            DjangoSettingsCompatibilityLayer: 兼容层实例
        """
        return self.compatibility_layer
    
    def is_migration_needed(self) -> bool:
        """
        检查是否需要迁移
        
        Returns:
            bool: 是否需要迁移
        """
        # 检查是否已有成功的迁移
        for migration_log in self._migration_logs:
            if migration_log.status == MigrationStatus.COMPLETED:
                return False
        
        # 检查是否有 Django 配置需要迁移
        django_configs = self.compatibility_layer.get_all_django_configs()
        return len(django_configs) > 0
    
    def generate_migration_report(self, migration_id: str) -> Dict[str, Any]:
        """
        生成迁移报告
        
        Args:
            migration_id: 迁移ID
            
        Returns:
            Dict[str, Any]: 迁移报告
        """
        migration_log = self.get_migration_status(migration_id)
        if not migration_log:
            raise ConfigException(f"找不到迁移: {migration_id}")
        
        report = {
            'migration_summary': migration_log.to_dict(),
            'migration_statistics': {
                'total_steps': len(migration_log.steps),
                'completed_steps': len([s for s in migration_log.steps if s.status == MigrationStatus.COMPLETED]),
                'failed_steps': len([s for s in migration_log.steps if s.status == MigrationStatus.FAILED]),
                'success_rate': 0.0
            },
            'recommendations': []
        }
        
        # 计算成功率
        if migration_log.steps:
            completed_count = len([s for s in migration_log.steps if s.status == MigrationStatus.COMPLETED])
            report['migration_statistics']['success_rate'] = completed_count / len(migration_log.steps) * 100
        
        # 生成建议
        if migration_log.status == MigrationStatus.COMPLETED:
            report['recommendations'].append("迁移成功完成，建议进行全面测试")
            report['recommendations'].append("可以考虑清理旧的 Django settings 配置")
        elif migration_log.status == MigrationStatus.FAILED:
            report['recommendations'].append("迁移失败，建议检查错误日志并修复问题")
            report['recommendations'].append("可以尝试回滚到迁移前状态")
        
        return report
    
    def create_rollback_point(self, migration_id: str, point_name: str) -> None:
        """
        创建回滚点
        
        Args:
            migration_id: 迁移ID
            point_name: 回滚点名称
        """
        rollback_point = {
            'migration_id': migration_id,
            'point_name': point_name,
            'timestamp': datetime.now().isoformat(),
            'config_state': self.config_manager.get_all() if self.config_manager.is_loaded() else {},
            'django_state': self.compatibility_layer.get_all_django_configs(),
            'rollback_stack': self._rollback_stack.copy()
        }
        
        point_key = f"{migration_id}_{point_name}"
        self._rollback_points[point_key] = rollback_point
        
        # 保存回滚点到文件
        rollback_file = os.path.join(self.backup_dir, f"{point_key}_rollback_point.json")
        with open(rollback_file, 'w', encoding='utf-8') as f:
            json.dump(rollback_point, f, ensure_ascii=False, indent=2, default=str)
        
        # 记录事件
        self.tracker.record_config_migration(
            migration_id, f"rollback_point_{point_name}", 
            None, point_name, "rollback_point"
        )
    
    def rollback_to_point(self, migration_id: str, point_name: str) -> bool:
        """
        回滚到指定回滚点
        
        Args:
            migration_id: 迁移ID
            point_name: 回滚点名称
            
        Returns:
            bool: 是否成功回滚
        """
        try:
            point_key = f"{migration_id}_{point_name}"
            
            # 从内存获取回滚点
            rollback_point = self._rollback_points.get(point_key)
            
            # 如果内存中没有，尝试从文件加载
            if not rollback_point:
                rollback_file = os.path.join(self.backup_dir, f"{point_key}_rollback_point.json")
                if os.path.exists(rollback_file):
                    with open(rollback_file, 'r', encoding='utf-8') as f:
                        rollback_point = json.load(f)
                else:
                    raise ConfigException(f"找不到回滚点: {point_name}")
            
            # 记录回滚开始
            self.tracker.record_error(
                migration_id, f"开始回滚到回滚点: {point_name}", 
                "ROLLBACK_STARTED"
            )
            
            # 恢复配置状态
            config_state = rollback_point.get('config_state', {})
            if config_state:
                # 清空当前配置
                self.config_manager.clear_cache()
                
                # 恢复配置
                for key, value in config_state.items():
                    self.config_manager.set(key, value)
            
            # 恢复回滚栈
            self._rollback_stack = rollback_point.get('rollback_stack', [])
            
            # 记录回滚完成
            self.tracker.record_config_migration(
                migration_id, f"rollback_completed_{point_name}", 
                None, point_name, "rollback"
            )
            
            return True
            
        except Exception as e:
            self.tracker.record_error(
                migration_id, f"回滚失败: {str(e)}", 
                "ROLLBACK_FAILED"
            )
            return False
    
    def auto_rollback_on_error(self, migration_id: str, error: Exception) -> bool:
        """
        错误时自动回滚
        
        Args:
            migration_id: 迁移ID
            error: 错误异常
            
        Returns:
            bool: 是否成功回滚
        """
        if not self.enable_auto_rollback:
            return False
        
        try:
            # 记录自动回滚开始
            self.tracker.record_error(
                migration_id, f"触发自动回滚: {str(error)}", 
                "AUTO_ROLLBACK_TRIGGERED"
            )
            
            # 执行回滚操作
            success = self._execute_rollback_operations(migration_id)
            
            if success:
                # 更新迁移状态
                for migration_log in self._migration_logs:
                    if migration_log.migration_id == migration_id:
                        migration_log.status = MigrationStatus.ROLLED_BACK
                        migration_log.completed_at = datetime.now()
                        migration_log.error_message = f"自动回滚: {str(error)}"
                        break
                
                # 记录自动回滚成功
                self.tracker.record_config_migration(
                    migration_id, "auto_rollback_success", 
                    None, "success", "auto_rollback"
                )
            else:
                # 记录自动回滚失败
                self.tracker.record_error(
                    migration_id, "自动回滚失败", 
                    "AUTO_ROLLBACK_FAILED"
                )
            
            return success
            
        except Exception as rollback_error:
            # 记录回滚过程中的错误
            self.tracker.record_error(
                migration_id, f"自动回滚过程中发生错误: {str(rollback_error)}", 
                "AUTO_ROLLBACK_ERROR"
            )
            return False
    
    def _execute_rollback_operations(self, migration_id: str) -> bool:
        """
        执行回滚操作
        
        Args:
            migration_id: 迁移ID
            
        Returns:
            bool: 是否成功
        """
        try:
            # 按相反顺序执行回滚操作
            rollback_operations = []
            
            # 从回滚栈中收集操作
            for operation in reversed(self._rollback_stack):
                op_migration_id, key, old_value, new_value = operation
                if op_migration_id == migration_id:
                    rollback_operations.append((key, old_value))
            
            # 执行回滚操作
            for key, old_value in rollback_operations:
                try:
                    if old_value is None:
                        # 如果旧值为 None，删除配置项
                        if self.config_manager.has(key):
                            # 这里需要实现删除功能，暂时跳过
                            pass
                    else:
                        # 恢复旧值
                        self.config_manager.set(key, old_value)
                    
                    # 记录回滚操作
                    self.tracker.record_config_migration(
                        migration_id, key, new_value, old_value, "rollback"
                    )
                    
                except Exception as e:
                    self.tracker.record_error(
                        migration_id, f"回滚配置项 {key} 失败: {str(e)}", 
                        "ROLLBACK_CONFIG_FAILED", config_key=key
                    )
                    # 继续回滚其他配置项
                    continue
            
            # 清空当前迁移的回滚栈
            self._rollback_stack = [
                op for op in self._rollback_stack 
                if op[0] != migration_id
            ]
            
            return True
            
        except Exception as e:
            self.tracker.record_error(
                migration_id, f"执行回滚操作失败: {str(e)}", 
                "EXECUTE_ROLLBACK_FAILED"
            )
            return False
    
    def _track_config_change(self, migration_id: str, key: str, 
                           old_value: Any, new_value: Any) -> None:
        """
        跟踪配置变更（用于回滚）
        
        Args:
            migration_id: 迁移ID
            key: 配置键
            old_value: 旧值
            new_value: 新值
        """
        # 添加到回滚栈
        self._rollback_stack.append((migration_id, key, old_value, new_value))
        
        # 记录到跟踪器
        self.tracker.record_config_migration(migration_id, key, old_value, new_value)
    
    def enhanced_rollback_migration(self, migration_id: str, 
                                  rollback_strategy: str = "full") -> bool:
        """
        增强的迁移回滚
        
        Args:
            migration_id: 迁移ID
            rollback_strategy: 回滚策略 ('full', 'partial', 'config_only')
            
        Returns:
            bool: 是否成功回滚
        """
        try:
            # 记录回滚开始
            self.tracker.record_error(
                migration_id, f"开始增强回滚 (策略: {rollback_strategy})", 
                "ENHANCED_ROLLBACK_STARTED"
            )
            
            if rollback_strategy == "full":
                # 完整回滚：恢复备份文件
                success = self.rollback_migration(migration_id)
            
            elif rollback_strategy == "partial":
                # 部分回滚：只回滚失败的配置项
                success = self._partial_rollback(migration_id)
            
            elif rollback_strategy == "config_only":
                # 仅配置回滚：只回滚配置管理器中的配置
                success = self._config_only_rollback(migration_id)
            
            else:
                raise ConfigException(f"不支持的回滚策略: {rollback_strategy}")
            
            if success:
                # 更新迁移状态
                for migration_log in self._migration_logs:
                    if migration_log.migration_id == migration_id:
                        migration_log.status = MigrationStatus.ROLLED_BACK
                        migration_log.completed_at = datetime.now()
                        break
                
                # 记录回滚成功
                self.tracker.record_config_migration(
                    migration_id, f"enhanced_rollback_success_{rollback_strategy}", 
                    None, "success", "enhanced_rollback"
                )
            
            return success
            
        except Exception as e:
            self.tracker.record_error(
                migration_id, f"增强回滚失败: {str(e)}", 
                "ENHANCED_ROLLBACK_FAILED"
            )
            return False
    
    def _partial_rollback(self, migration_id: str) -> bool:
        """
        部分回滚：只回滚失败的配置项
        
        Args:
            migration_id: 迁移ID
            
        Returns:
            bool: 是否成功
        """
        try:
            # 获取失败的配置项
            failed_events = self.tracker.get_migration_events(
                migration_id, 
                [MigrationEventType.ERROR_OCCURRED]
            )
            
            failed_configs = set()
            for event in failed_events:
                if event.config_key:
                    failed_configs.add(event.config_key)
            
            if not failed_configs:
                return True  # 没有失败的配置项
            
            # 从回滚栈中找到这些配置项的原始值
            rollback_operations = []
            for operation in reversed(self._rollback_stack):
                op_migration_id, key, old_value, new_value = operation
                if op_migration_id == migration_id and key in failed_configs:
                    rollback_operations.append((key, old_value))
            
            # 执行部分回滚
            for key, old_value in rollback_operations:
                try:
                    if old_value is None:
                        # 删除配置项（如果支持）
                        pass
                    else:
                        self.config_manager.set(key, old_value)
                    
                    self.tracker.record_config_migration(
                        migration_id, key, None, old_value, "partial_rollback"
                    )
                    
                except Exception as e:
                    self.tracker.record_error(
                        migration_id, f"部分回滚配置项 {key} 失败: {str(e)}", 
                        "PARTIAL_ROLLBACK_CONFIG_FAILED", config_key=key
                    )
            
            return True
            
        except Exception as e:
            self.tracker.record_error(
                migration_id, f"部分回滚失败: {str(e)}", 
                "PARTIAL_ROLLBACK_FAILED"
            )
            return False
    
    def _config_only_rollback(self, migration_id: str) -> bool:
        """
        仅配置回滚：只回滚配置管理器中的配置
        
        Args:
            migration_id: 迁移ID
            
        Returns:
            bool: 是否成功
        """
        try:
            # 查找备份文件
            backup_file = os.path.join(self.backup_dir, f"{migration_id}_backup.json")
            if not os.path.exists(backup_file):
                raise ConfigException(f"找不到迁移备份文件: {backup_file}")
            
            # 加载备份数据
            with open(backup_file, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)
            
            # 只恢复配置管理器数据
            config_data = backup_data.get('config_manager_data', {})
            if config_data:
                # 清空当前配置
                self.config_manager.clear_cache()
                
                # 恢复配置
                for key, value in config_data.items():
                    self.config_manager.set(key, value)
                    
                    self.tracker.record_config_migration(
                        migration_id, key, None, value, "config_only_rollback"
                    )
            
            return True
            
        except Exception as e:
            self.tracker.record_error(
                migration_id, f"仅配置回滚失败: {str(e)}", 
                "CONFIG_ONLY_ROLLBACK_FAILED"
            )
            return False
    
    def validate_rollback_integrity(self, migration_id: str) -> Dict[str, Any]:
        """
        验证回滚完整性
        
        Args:
            migration_id: 迁移ID
            
        Returns:
            Dict[str, Any]: 验证结果
        """
        result = {
            'migration_id': migration_id,
            'is_valid': True,
            'issues': [],
            'rollback_available': False,
            'backup_files': [],
            'rollback_points': []
        }
        
        try:
            # 检查备份文件
            backup_file = os.path.join(self.backup_dir, f"{migration_id}_backup.json")
            if os.path.exists(backup_file):
                result['rollback_available'] = True
                result['backup_files'].append(backup_file)
                
                # 验证备份文件完整性
                try:
                    with open(backup_file, 'r', encoding='utf-8') as f:
                        backup_data = json.load(f)
                    
                    required_keys = ['backup_time', 'django_settings', 'config_manager_data']
                    for key in required_keys:
                        if key not in backup_data:
                            result['issues'].append(f"备份文件缺少必需字段: {key}")
                            result['is_valid'] = False
                            
                except Exception as e:
                    result['issues'].append(f"备份文件损坏: {str(e)}")
                    result['is_valid'] = False
            else:
                result['issues'].append("找不到备份文件")
                result['is_valid'] = False
            
            # 检查回滚点
            for point_key, rollback_point in self._rollback_points.items():
                if rollback_point['migration_id'] == migration_id:
                    result['rollback_points'].append(rollback_point['point_name'])
            
            # 检查回滚栈
            rollback_operations = [
                op for op in self._rollback_stack 
                if op[0] == migration_id
            ]
            
            if rollback_operations:
                result['rollback_operations_count'] = len(rollback_operations)
            else:
                result['issues'].append("没有可用的回滚操作")
            
            # 检查迁移状态
            migration_progress = self.tracker.get_migration_progress(migration_id)
            if migration_progress:
                if migration_progress.is_failed:
                    result['migration_status'] = 'failed'
                elif migration_progress.is_completed:
                    result['migration_status'] = 'completed'
                else:
                    result['migration_status'] = 'in_progress'
            else:
                result['issues'].append("找不到迁移进度信息")
                result['is_valid'] = False
            
        except Exception as e:
            result['issues'].append(f"验证过程中发生错误: {str(e)}")
            result['is_valid'] = False
        
        return result
    
    def list_rollback_options(self, migration_id: str) -> Dict[str, Any]:
        """
        列出回滚选项
        
        Args:
            migration_id: 迁移ID
            
        Returns:
            Dict[str, Any]: 回滚选项
        """
        options = {
            'migration_id': migration_id,
            'available_strategies': [],
            'rollback_points': [],
            'backup_files': [],
            'recommended_strategy': None
        }
        
        # 检查可用的回滚策略
        validation_result = self.validate_rollback_integrity(migration_id)
        
        if validation_result['rollback_available']:
            options['available_strategies'].append({
                'name': 'full',
                'description': '完整回滚：恢复所有配置到迁移前状态',
                'risk_level': 'low'
            })
            
            options['available_strategies'].append({
                'name': 'config_only',
                'description': '仅配置回滚：只回滚配置管理器中的配置',
                'risk_level': 'medium'
            })
        
        # 检查是否有失败的配置项
        failed_events = self.tracker.get_migration_events(
            migration_id, 
            [MigrationEventType.ERROR_OCCURRED]
        )
        
        if failed_events:
            options['available_strategies'].append({
                'name': 'partial',
                'description': '部分回滚：只回滚失败的配置项',
                'risk_level': 'low'
            })
        
        # 添加回滚点信息
        options['rollback_points'] = validation_result['rollback_points']
        options['backup_files'] = validation_result['backup_files']
        
        # 推荐策略
        if failed_events and len(failed_events) < 5:
            options['recommended_strategy'] = 'partial'
        elif validation_result['rollback_available']:
            options['recommended_strategy'] = 'full'
        else:
            options['recommended_strategy'] = None
        
        return options