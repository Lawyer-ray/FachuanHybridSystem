"""
Core 应用配置

负责初始化统一配置管理系统和核心服务
"""

import logging
from django.apps import AppConfig
from django.conf import settings

logger = logging.getLogger(__name__)


class CoreConfig(AppConfig):
    """Core 应用配置类"""
    
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    verbose_name = '核心系统'
    
    def ready(self):
        """应用就绪时的初始化操作"""
        # 导入 admin 模块以注册 Admin 类
        from . import admin  # noqa: F401
        
        # 只在主进程中执行初始化
        import os
        if os.environ.get('RUN_MAIN') != 'true':
            return
        
        try:
            self._initialize_config_manager()
            self._validate_configuration()
            self._setup_config_monitoring()
            logger.info("核心系统初始化完成")
        except Exception as e:
            logger.error(f"核心系统初始化失败: {e}")
            # 在开发环境中抛出异常，生产环境中记录错误但继续运行
            if getattr(settings, 'DEBUG', False):
                raise
    
    def _initialize_config_manager(self):
        """初始化配置管理器"""
        try:
            # 检查配置管理器是否可用
            if not getattr(settings, 'CONFIG_MANAGER_AVAILABLE', False):
                logger.warning("统一配置管理器不可用，使用传统配置方式")
                return
            
            # 获取配置管理器实例
            config_manager = getattr(settings, 'UNIFIED_CONFIG_MANAGER', None)
            if not config_manager:
                logger.warning("配置管理器实例不存在")
                return
            
            # 确保配置已加载
            if not config_manager.is_loaded():
                config_manager.load()
                logger.info("配置管理器加载完成")
            
            # 启用 Steering 系统集成
            try:
                config_manager.enable_steering_integration()
                logger.info("Steering 系统集成已启用")
            except Exception as e:
                logger.warning(f"Steering 系统集成启用失败: {e}")
            
        except Exception as e:
            logger.error(f"配置管理器初始化失败: {e}")
            raise
    
    def _validate_configuration(self):
        """验证配置完整性"""
        try:
            # 检查配置管理器是否可用
            if not getattr(settings, 'CONFIG_MANAGER_AVAILABLE', False):
                return
            
            config_manager = getattr(settings, 'UNIFIED_CONFIG_MANAGER', None)
            if not config_manager:
                return
            
            # 验证关键配置项
            critical_configs = [
                'django.secret_key',
                'django.debug',
                'database.engine',
            ]
            
            missing_configs = []
            for config_key in critical_configs:
                try:
                    value = config_manager.get(config_key)
                    if value is None:
                        missing_configs.append(config_key)
                except Exception:
                    missing_configs.append(config_key)
            
            if missing_configs:
                logger.warning(f"缺少关键配置项: {', '.join(missing_configs)}")
            else:
                logger.info("配置验证通过")
            
            # 验证敏感配置（生产环境）
            if not getattr(settings, 'DEBUG', True):
                self._validate_production_config(config_manager)
            
        except Exception as e:
            logger.error(f"配置验证失败: {e}")
            raise
    
    def _validate_production_config(self, config_manager):
        """验证生产环境配置"""
        try:
            # 检查敏感配置是否从环境变量加载
            sensitive_configs = [
                'django.secret_key',
                'database.password',
                'services.moonshot.api_key',
                'chat_platforms.feishu.app_secret',
            ]
            
            env_missing = []
            for config_key in sensitive_configs:
                try:
                    # 检查配置是否存在且不为空
                    value = config_manager.get(config_key)
                    if not value:
                        env_missing.append(config_key)
                except Exception:
                    env_missing.append(config_key)
            
            if env_missing:
                logger.error(f"生产环境缺少敏感配置: {', '.join(env_missing)}")
                raise ValueError(f"生产环境必须设置敏感配置: {', '.join(env_missing)}")
            
            logger.info("生产环境配置验证通过")
            
        except Exception as e:
            logger.error(f"生产环境配置验证失败: {e}")
            raise
    
    def _setup_config_monitoring(self):
        """设置配置监控"""
        try:
            # 检查配置管理器是否可用
            if not getattr(settings, 'CONFIG_MANAGER_AVAILABLE', False):
                return
            
            config_manager = getattr(settings, 'UNIFIED_CONFIG_MANAGER', None)
            if not config_manager:
                return
            
            # 注册配置变更监听器
            from .config.listeners import ConfigChangeLogger, ConfigValidationListener
            
            # 添加日志监听器
            log_listener = ConfigChangeLogger()
            config_manager.add_listener(log_listener)
            
            # 添加验证监听器
            validation_listener = ConfigValidationListener()
            config_manager.add_listener(validation_listener)
            
            logger.info("配置监控设置完成")
            
        except ImportError:
            # 监听器类不存在，跳过
            logger.debug("配置监听器类不存在，跳过监控设置")
        except Exception as e:
            logger.warning(f"配置监控设置失败: {e}")