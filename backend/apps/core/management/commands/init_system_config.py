"""
初始化系统配置命令

用于初始化系统配置项并可选地从环境变量同步配置。
"""

import os
from django.core.management.base import BaseCommand
from apps.core.models import SystemConfig


class Command(BaseCommand):
    help = '初始化系统配置项'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--sync-env',
            action='store_true',
            help='同时从环境变量同步配置值',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='强制覆盖已存在的配置',
        )
    
    def handle(self, *args, **options):
        sync_env = options['sync_env']
        force = options['force']
        
        self.stdout.write('开始初始化系统配置...')
        
        # 默认配置项
        defaults = self._get_default_configs()
        
        created_count = 0
        updated_count = 0
        
        for config in defaults:
            key = config['key']
            
            # 检查是否需要从环境变量获取值
            env_value = None
            if sync_env:
                env_value = os.environ.get(key)
            
            # 确定最终值
            value = env_value if env_value else config.get('value', '')
            
            if force:
                # 强制更新
                obj, created = SystemConfig.objects.update_or_create(
                    key=key,
                    defaults={
                        'value': value,
                        'category': config['category'],
                        'description': config['description'],
                        'is_secret': config.get('is_secret', False),
                    }
                )
                if created:
                    created_count += 1
                    self.stdout.write(f'  创建: {key}')
                else:
                    updated_count += 1
                    self.stdout.write(f'  更新: {key}')
            else:
                # 只创建不存在的
                obj, created = SystemConfig.objects.get_or_create(
                    key=key,
                    defaults={
                        'value': value,
                        'category': config['category'],
                        'description': config['description'],
                        'is_secret': config.get('is_secret', False),
                    }
                )
                if created:
                    created_count += 1
                    self.stdout.write(f'  创建: {key}')
                else:
                    self.stdout.write(f'  跳过（已存在）: {key}')
        
        self.stdout.write(self.style.SUCCESS(
            f'\n完成！创建 {created_count} 个，更新 {updated_count} 个配置项'
        ))
    
    def _get_default_configs(self):
        """获取默认配置项列表"""
        # 直接从 Admin 类获取配置，保持一致性
        from apps.core.admin.system_config_admin import SystemConfigAdmin
        admin_instance = SystemConfigAdmin(SystemConfig, None)
        return admin_instance._get_default_configs()
