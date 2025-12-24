"""
系统配置 Admin

提供 Django Admin 界面来管理系统配置项，包括飞书、钉钉等第三方服务配置。
"""

import os
from django.contrib import admin
from django.utils.html import format_html
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.urls import path, reverse
from django.shortcuts import render
from django.core.cache import cache

from ..models import SystemConfig


@admin.register(SystemConfig)
class SystemConfigAdmin(admin.ModelAdmin):
    """系统配置 Admin"""
    
    list_display = [
        'key', 'category_display', 'masked_value', 
        'is_secret', 'is_active', 'updated_at'
    ]
    list_filter = ['category', 'is_secret', 'is_active']
    search_fields = ['key', 'description']
    list_editable = ['is_active']
    ordering = ['category', 'key']
    
    fieldsets = (
        ('基本信息', {
            'fields': ('key', 'value', 'category', 'description')
        }),
        ('安全设置', {
            'fields': ('is_secret', 'is_active'),
            'classes': ('collapse',)
        }),
        ('时间信息', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['created_at', 'updated_at']
    
    def category_display(self, obj):
        """显示分类标签"""
        colors = {
            'feishu': '#3370ff',
            'dingtalk': '#0089ff',
            'wechat_work': '#07c160',
            'court_sms': '#ff6b35',
            'ai': '#9c27b0',
            'scraper': '#ff9800',
            'general': '#607d8b',
        }
        color = colors.get(obj.category, '#607d8b')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; '
            'border-radius: 4px; font-size: 12px;">{}</span>',
            color, obj.get_category_display()
        )
    category_display.short_description = '分类'
    category_display.admin_order_field = 'category'
    
    def masked_value(self, obj):
        """显示脱敏后的值"""
        if not obj.value:
            return format_html('<span style="color: #999;">未设置</span>')
        
        if obj.is_secret:
            # 敏感信息只显示前后几位
            if len(obj.value) > 8:
                masked = obj.value[:4] + '*' * (len(obj.value) - 8) + obj.value[-4:]
            else:
                masked = '*' * len(obj.value)
            return format_html(
                '<span style="font-family: monospace;">{}</span>',
                masked
            )
        else:
            # 非敏感信息截断显示
            if len(obj.value) > 50:
                return format_html(
                    '<span title="{}">{}</span>',
                    obj.value, obj.value[:50] + '...'
                )
            return obj.value
    masked_value.short_description = '配置值'
    
    def get_urls(self):
        """添加自定义 URL"""
        urls = super().get_urls()
        custom_urls = [
            path(
                'init-defaults/',
                self.admin_site.admin_view(self.init_defaults_view),
                name='core_systemconfig_init_defaults'
            ),
            path(
                'sync-env/',
                self.admin_site.admin_view(self.sync_env_view),
                name='core_systemconfig_sync_env'
            ),
            path(
                'clear-cache/',
                self.admin_site.admin_view(self.clear_cache_view),
                name='core_systemconfig_clear_cache'
            ),
        ]
        return custom_urls + urls
    
    def changelist_view(self, request, extra_context=None):
        """自定义列表页面"""
        extra_context = extra_context or {}
        extra_context['show_init_button'] = True
        extra_context['show_sync_button'] = True
        extra_context['show_clear_cache_button'] = True
        extra_context['has_add_permission'] = self.has_add_permission(request)
        return super().changelist_view(request, extra_context=extra_context)
    
    def init_defaults_view(self, request):
        """初始化默认配置项"""
        defaults = self._get_default_configs()
        created_count = 0
        
        for config in defaults:
            obj, created = SystemConfig.objects.get_or_create(
                key=config['key'],
                defaults={
                    'value': config.get('value', ''),
                    'category': config['category'],
                    'description': config['description'],
                    'is_secret': config.get('is_secret', False),
                }
            )
            if created:
                created_count += 1
        
        if created_count > 0:
            messages.success(request, f'成功创建 {created_count} 个默认配置项')
        else:
            messages.info(request, '所有默认配置项已存在')
        
        return HttpResponseRedirect(reverse('admin:core_systemconfig_changelist'))
    
    def sync_env_view(self, request):
        """从环境变量同步配置"""
        env_mappings = self._get_env_mappings()
        synced_count = 0
        
        for env_key, config_info in env_mappings.items():
            env_value = os.environ.get(env_key)
            if env_value:
                obj, created = SystemConfig.objects.update_or_create(
                    key=config_info['key'],
                    defaults={
                        'value': env_value,
                        'category': config_info['category'],
                        'description': config_info['description'],
                        'is_secret': config_info.get('is_secret', False),
                    }
                )
                synced_count += 1
        
        if synced_count > 0:
            messages.success(request, f'成功从环境变量同步 {synced_count} 个配置项')
        else:
            messages.info(request, '没有找到可同步的环境变量')
        
        return HttpResponseRedirect(reverse('admin:core_systemconfig_changelist'))
    
    def clear_cache_view(self, request):
        """清除配置缓存"""
        # 清除所有配置缓存
        cache.delete('system_config:all')
        
        # 清除单个配置缓存
        for config in SystemConfig.objects.all():
            cache.delete(f'system_config:{config.key}')
        
        messages.success(request, '配置缓存已清除')
        return HttpResponseRedirect(reverse('admin:core_systemconfig_changelist'))
    
    def _get_default_configs(self):
        """获取默认配置项列表"""
        return [
            # ============ Django 配置 ============
            {
                'key': 'DJANGO_SECRET_KEY',
                'category': 'general',
                'description': 'Django 密钥（生产环境必须修改）',
                'is_secret': True,
            },
            {
                'key': 'DJANGO_DEBUG',
                'category': 'general',
                'description': 'Django 调试模式',
                'value': 'True',
                'is_secret': False,
            },
            {
                'key': 'DJANGO_ALLOWED_HOSTS',
                'category': 'general',
                'description': '允许的主机列表（逗号分隔）',
                'value': 'localhost,127.0.0.1',
                'is_secret': False,
            },
            {
                'key': 'SITE_NAME',
                'category': 'general',
                'description': '系统名称（显示在后台标题）',
                'value': '法律案件管理系统',
                'is_secret': False,
            },
            {
                'key': 'SITE_HEADER',
                'category': 'general',
                'description': '后台页面标题',
                'value': '案件管理后台',
                'is_secret': False,
            },
            {
                'key': 'COMPANY_NAME',
                'category': 'general',
                'description': '公司/律所名称',
                'value': '',
                'is_secret': False,
            },
            {
                'key': 'ADMIN_EMAIL',
                'category': 'general',
                'description': '管理员邮箱（用于系统通知）',
                'value': '',
                'is_secret': False,
            },
            {
                'key': 'TIMEZONE',
                'category': 'general',
                'description': '系统时区',
                'value': 'Asia/Shanghai',
                'is_secret': False,
            },
            # ============ 飞书配置 ============
            {
                'key': 'FEISHU_APP_ID',
                'category': 'feishu',
                'description': '飞书应用 App ID',
                'is_secret': False,
            },
            {
                'key': 'FEISHU_APP_SECRET',
                'category': 'feishu',
                'description': '飞书应用 App Secret',
                'is_secret': True,
            },
            {
                'key': 'FEISHU_DEFAULT_OWNER_ID',
                'category': 'feishu',
                'description': '飞书群聊默认群主 ID（open_id 格式：ou_xxxxxx）',
                'is_secret': False,
            },
            {
                'key': 'FEISHU_WEBHOOK_URL',
                'category': 'feishu',
                'description': '飞书 Webhook URL（可选，用于传统通知）',
                'is_secret': False,
            },
            {
                'key': 'FEISHU_TIMEOUT',
                'category': 'feishu',
                'description': '飞书 API 超时时间（秒）',
                'value': '30',
                'is_secret': False,
            },
            # ============ 飞书群聊配置 ============
            {
                'key': 'FEISHU_CHAT_CASE_GROUP',
                'category': 'feishu',
                'description': '案件通知群名称（用于案件相关通知）',
                'value': '案件通知群',
                'is_secret': False,
            },
            {
                'key': 'FEISHU_CHAT_DOCUMENT_GROUP',
                'category': 'feishu',
                'description': '文书通知群名称（用于法院文书通知）',
                'value': '法院文书通知群',
                'is_secret': False,
            },
            {
                'key': 'FEISHU_CHAT_SMS_GROUP',
                'category': 'feishu',
                'description': '短信通知群名称（用于法院短信通知）',
                'value': '法院短信通知群',
                'is_secret': False,
            },
            {
                'key': 'FEISHU_CHAT_ALERT_GROUP',
                'category': 'feishu',
                'description': '系统告警群名称（用于系统异常告警）',
                'value': '系统告警群',
                'is_secret': False,
            },
            {
                'key': 'FEISHU_CHAT_CONTRACT_GROUP',
                'category': 'feishu',
                'description': '合同通知群名称（用于合同相关通知）',
                'value': '合同通知群',
                'is_secret': False,
            },
            {
                'key': 'FEISHU_CHAT_FINANCE_GROUP',
                'category': 'feishu',
                'description': '财务通知群名称（用于收款、回款通知）',
                'value': '财务通知群',
                'is_secret': False,
            },
            # ============ 群聊名称模板配置 ============
            {
                'key': 'CASE_CHAT_NAME_TEMPLATE',
                'category': 'feishu',
                'description': '案件群聊名称模板，支持占位符：{stage}（案件阶段）、{case_name}（案件名称）、{case_type}（案件类型）',
                'value': '【{stage}】{case_name}',
                'is_secret': False,
            },
            {
                'key': 'CASE_CHAT_DEFAULT_STAGE',
                'category': 'feishu',
                'description': '案件阶段为空时的默认显示文本',
                'value': '待定',
                'is_secret': False,
            },
            {
                'key': 'CASE_CHAT_NAME_MAX_LENGTH',
                'category': 'feishu',
                'description': '群聊名称最大长度（飞书限制为60）',
                'value': '60',
                'is_secret': False,
            },
            # ============ 飞书高级配置 ============
            {
                'key': 'FEISHU_TEST_MODE',
                'category': 'feishu',
                'description': '飞书测试模式（启用后不会真正发送消息）',
                'value': 'false',
                'is_secret': False,
            },
            {
                'key': 'FEISHU_TEST_OWNER_ID',
                'category': 'feishu',
                'description': '飞书测试群主 ID',
                'is_secret': False,
            },
            {
                'key': 'FEISHU_OWNER_VALIDATION_ENABLED',
                'category': 'feishu',
                'description': '启用群主验证',
                'value': 'true',
                'is_secret': False,
            },
            {
                'key': 'FEISHU_OWNER_RETRY_ENABLED',
                'category': 'feishu',
                'description': '启用群主重试',
                'value': 'true',
                'is_secret': False,
            },
            {
                'key': 'FEISHU_OWNER_MAX_RETRIES',
                'category': 'feishu',
                'description': '群主设置最大重试次数',
                'value': '3',
                'is_secret': False,
            },
            {
                'key': 'FEISHU_MESSAGE_BATCH_SIZE',
                'category': 'feishu',
                'description': '飞书消息批量发送数量',
                'value': '10',
                'is_secret': False,
            },
            {
                'key': 'FEISHU_FILE_UPLOAD_MAX_SIZE',
                'category': 'feishu',
                'description': '飞书文件上传最大大小（MB）',
                'value': '30',
                'is_secret': False,
            },
            # ============ 钉钉配置 ============
            {
                'key': 'DINGTALK_APP_KEY',
                'category': 'dingtalk',
                'description': '钉钉应用 App Key',
                'is_secret': False,
            },
            {
                'key': 'DINGTALK_APP_SECRET',
                'category': 'dingtalk',
                'description': '钉钉应用 App Secret',
                'is_secret': True,
            },
            {
                'key': 'DINGTALK_AGENT_ID',
                'category': 'dingtalk',
                'description': '钉钉应用 Agent ID',
                'is_secret': False,
            },
            {
                'key': 'DINGTALK_TIMEOUT',
                'category': 'dingtalk',
                'description': '钉钉 API 超时时间（秒）',
                'value': '30',
                'is_secret': False,
            },
            {
                'key': 'DINGTALK_CHAT_CASE_GROUP',
                'category': 'dingtalk',
                'description': '钉钉案件通知群名称',
                'value': '案件通知群',
                'is_secret': False,
            },
            {
                'key': 'DINGTALK_CHAT_ALERT_GROUP',
                'category': 'dingtalk',
                'description': '钉钉系统告警群名称',
                'value': '系统告警群',
                'is_secret': False,
            },
            # ============ 企业微信配置 ============
            {
                'key': 'WECHAT_WORK_CORP_ID',
                'category': 'wechat_work',
                'description': '企业微信 Corp ID',
                'is_secret': False,
            },
            {
                'key': 'WECHAT_WORK_AGENT_ID',
                'category': 'wechat_work',
                'description': '企业微信 Agent ID',
                'is_secret': False,
            },
            {
                'key': 'WECHAT_WORK_SECRET',
                'category': 'wechat_work',
                'description': '企业微信应用 Secret',
                'is_secret': True,
            },
            {
                'key': 'WECHAT_WORK_TIMEOUT',
                'category': 'wechat_work',
                'description': '企业微信 API 超时时间（秒）',
                'value': '30',
                'is_secret': False,
            },
            {
                'key': 'WECHAT_WORK_CHAT_CASE_GROUP',
                'category': 'wechat_work',
                'description': '企业微信案件通知群名称',
                'value': '案件通知群',
                'is_secret': False,
            },
            # ============ Telegram 配置 ============
            {
                'key': 'TELEGRAM_BOT_TOKEN',
                'category': 'general',
                'description': 'Telegram Bot Token',
                'is_secret': True,
            },
            {
                'key': 'TELEGRAM_TIMEOUT',
                'category': 'general',
                'description': 'Telegram API 超时时间（秒）',
                'value': '30',
                'is_secret': False,
            },
            # ============ Slack 配置 ============
            {
                'key': 'SLACK_BOT_TOKEN',
                'category': 'general',
                'description': 'Slack Bot Token',
                'is_secret': True,
            },
            {
                'key': 'SLACK_SIGNING_SECRET',
                'category': 'general',
                'description': 'Slack Signing Secret',
                'is_secret': True,
            },
            {
                'key': 'SLACK_TIMEOUT',
                'category': 'general',
                'description': 'Slack API 超时时间（秒）',
                'value': '30',
                'is_secret': False,
            },
            # ============ 法院短信配置 ============
            {
                'key': 'COURT_SMS_ENABLED',
                'category': 'court_sms',
                'description': '启用法院短信处理功能',
                'value': 'True',
                'is_secret': False,
            },
            {
                'key': 'COURT_SMS_MAX_RETRIES',
                'category': 'court_sms',
                'description': '法院短信处理最大重试次数',
                'value': '3',
                'is_secret': False,
            },
            {
                'key': 'COURT_SMS_RETRY_DELAY',
                'category': 'court_sms',
                'description': '法院短信处理重试延迟（秒）',
                'value': '60',
                'is_secret': False,
            },
            {
                'key': 'COURT_SMS_AUTO_RECOVERY',
                'category': 'court_sms',
                'description': '法院短信自动恢复',
                'value': 'True',
                'is_secret': False,
            },
            {
                'key': 'COURT_SMS_NOTIFY_ON_SUCCESS',
                'category': 'court_sms',
                'description': '短信处理成功时发送通知',
                'value': 'True',
                'is_secret': False,
            },
            {
                'key': 'COURT_SMS_NOTIFY_ON_FAILURE',
                'category': 'court_sms',
                'description': '短信处理失败时发送通知',
                'value': 'True',
                'is_secret': False,
            },
            {
                'key': 'COURT_SMS_AUTO_MATCH_CASE',
                'category': 'court_sms',
                'description': '自动匹配案件',
                'value': 'True',
                'is_secret': False,
            },
            {
                'key': 'COURT_SMS_DOWNLOAD_TIMEOUT',
                'category': 'court_sms',
                'description': '文书下载超时时间（秒）',
                'value': '120',
                'is_secret': False,
            },
            # ============ 文书送达配置 ============
            {
                'key': 'DOCUMENT_DELIVERY_ENABLED',
                'category': 'court_sms',
                'description': '启用文书送达自动处理',
                'value': 'True',
                'is_secret': False,
            },
            {
                'key': 'DOCUMENT_DELIVERY_SCHEDULE',
                'category': 'court_sms',
                'description': '文书送达检查时间（cron 格式）',
                'value': '0 9,14,18 * * *',
                'is_secret': False,
            },
            {
                'key': 'DOCUMENT_DELIVERY_BATCH_SIZE',
                'category': 'court_sms',
                'description': '文书送达批量处理数量',
                'value': '10',
                'is_secret': False,
            },
            # ============ AI 配置 ============
            {
                'key': 'AI_ENABLED',
                'category': 'ai',
                'description': '启用 AI 功能',
                'value': 'True',
                'is_secret': False,
            },
            {
                'key': 'AI_PROVIDER',
                'category': 'ai',
                'description': 'AI 服务提供商（ollama/moonshot/openai）',
                'value': 'ollama',
                'is_secret': False,
            },
            {
                'key': 'OLLAMA_MODEL',
                'category': 'ai',
                'description': 'Ollama 模型名称',
                'value': 'qwen3:0.6b',
                'is_secret': False,
            },
            {
                'key': 'OLLAMA_BASE_URL',
                'category': 'ai',
                'description': 'Ollama API 地址',
                'value': 'http://localhost:11434',
                'is_secret': False,
            },
            {
                'key': 'MOONSHOT_API_KEY',
                'category': 'ai',
                'description': 'Moonshot AI API Key',
                'is_secret': True,
            },
            {
                'key': 'MOONSHOT_BASE_URL',
                'category': 'ai',
                'description': 'Moonshot AI API 地址',
                'value': 'https://api.moonshot.cn/v1',
                'is_secret': False,
            },
            {
                'key': 'MOONSHOT_MODEL',
                'category': 'ai',
                'description': 'Moonshot 模型名称',
                'value': 'moonshot-v1-8k',
                'is_secret': False,
            },
            {
                'key': 'OPENAI_API_KEY',
                'category': 'ai',
                'description': 'OpenAI API Key',
                'is_secret': True,
            },
            {
                'key': 'OPENAI_BASE_URL',
                'category': 'ai',
                'description': 'OpenAI API 地址（可用于代理）',
                'value': 'https://api.openai.com/v1',
                'is_secret': False,
            },
            {
                'key': 'OPENAI_MODEL',
                'category': 'ai',
                'description': 'OpenAI 模型名称',
                'value': 'gpt-3.5-turbo',
                'is_secret': False,
            },
            {
                'key': 'AI_AUTO_NAMING_ENABLED',
                'category': 'ai',
                'description': '启用 AI 自动命名功能',
                'value': 'True',
                'is_secret': False,
            },
            {
                'key': 'AI_CASE_ANALYSIS_ENABLED',
                'category': 'ai',
                'description': '启用 AI 案件分析功能',
                'value': 'False',
                'is_secret': False,
            },
            # ============ 爬虫配置 ============
            {
                'key': 'SCRAPER_ENABLED',
                'category': 'scraper',
                'description': '启用爬虫功能',
                'value': 'True',
                'is_secret': False,
            },
            {
                'key': 'SCRAPER_ENCRYPTION_KEY',
                'category': 'scraper',
                'description': '爬虫加密密钥',
                'is_secret': True,
            },
            {
                'key': 'SCRAPER_HEADLESS',
                'category': 'scraper',
                'description': '爬虫是否使用无头模式',
                'value': 'True',
                'is_secret': False,
            },
            {
                'key': 'SCRAPER_TIMEOUT',
                'category': 'scraper',
                'description': '爬虫页面加载超时时间（秒）',
                'value': '60',
                'is_secret': False,
            },
            {
                'key': 'SCRAPER_MAX_CONCURRENT',
                'category': 'scraper',
                'description': '爬虫最大并发数',
                'value': '3',
                'is_secret': False,
            },
            {
                'key': 'SCRAPER_RETRY_COUNT',
                'category': 'scraper',
                'description': '爬虫失败重试次数',
                'value': '3',
                'is_secret': False,
            },
            {
                'key': 'SCRAPER_DOWNLOAD_DIR',
                'category': 'scraper',
                'description': '爬虫下载目录',
                'value': '/tmp/scraper_downloads',
                'is_secret': False,
            },
            # ============ Token 获取配置 ============
            {
                'key': 'TOKEN_AUTO_REFRESH_ENABLED',
                'category': 'scraper',
                'description': '启用 Token 自动刷新',
                'value': 'True',
                'is_secret': False,
            },
            {
                'key': 'TOKEN_REFRESH_INTERVAL',
                'category': 'scraper',
                'description': 'Token 刷新间隔（分钟）',
                'value': '30',
                'is_secret': False,
            },
            {
                'key': 'TOKEN_CACHE_TTL',
                'category': 'scraper',
                'description': 'Token 缓存有效期（秒）',
                'value': '3600',
                'is_secret': False,
            },
            # ============ CORS 配置 ============
            {
                'key': 'CORS_ALLOWED_ORIGINS',
                'category': 'general',
                'description': 'CORS 允许的来源（逗号分隔）',
                'value': 'http://localhost:5173',
                'is_secret': False,
            },
            {
                'key': 'CSRF_TRUSTED_ORIGINS',
                'category': 'general',
                'description': 'CSRF 信任的来源（逗号分隔）',
                'value': 'http://localhost:5173',
                'is_secret': False,
            },
            # ============ 文件存储配置 ============
            {
                'key': 'FILE_STORAGE_BACKEND',
                'category': 'general',
                'description': '文件存储后端（local/s3/oss）',
                'value': 'local',
                'is_secret': False,
            },
            {
                'key': 'FILE_UPLOAD_MAX_SIZE',
                'category': 'general',
                'description': '文件上传最大大小（MB）',
                'value': '50',
                'is_secret': False,
            },
            {
                'key': 'FILE_ALLOWED_EXTENSIONS',
                'category': 'general',
                'description': '允许上传的文件扩展名（逗号分隔）',
                'value': 'pdf,doc,docx,xls,xlsx,jpg,jpeg,png,zip',
                'is_secret': False,
            },
            # ============ 日志配置 ============
            {
                'key': 'LOG_LEVEL',
                'category': 'general',
                'description': '日志级别（DEBUG/INFO/WARNING/ERROR）',
                'value': 'INFO',
                'is_secret': False,
            },
            {
                'key': 'LOG_RETENTION_DAYS',
                'category': 'general',
                'description': '日志保留天数',
                'value': '30',
                'is_secret': False,
            },
            # ============ 通知配置 ============
            {
                'key': 'NOTIFICATION_PROVIDER',
                'category': 'general',
                'description': '默认通知渠道（feishu/dingtalk/wechat_work）',
                'value': 'feishu',
                'is_secret': False,
            },
            {
                'key': 'NOTIFICATION_ENABLED',
                'category': 'general',
                'description': '启用系统通知',
                'value': 'True',
                'is_secret': False,
            },
            # ============ 数据库配置 ============
            {
                'key': 'DATABASE_URL',
                'category': 'general',
                'description': '数据库连接 URL',
                'is_secret': True,
            },
            {
                'key': 'DATABASE_POOL_SIZE',
                'category': 'general',
                'description': '数据库连接池大小',
                'value': '10',
                'is_secret': False,
            },
            # ============ Redis 配置 ============
            {
                'key': 'REDIS_URL',
                'category': 'general',
                'description': 'Redis 连接 URL',
                'value': 'redis://localhost:6379/0',
                'is_secret': False,
            },
            {
                'key': 'CACHE_TTL_DEFAULT',
                'category': 'general',
                'description': '默认缓存过期时间（秒）',
                'value': '300',
                'is_secret': False,
            },
        ]
    
    def _get_env_mappings(self):
        """获取环境变量到配置的映射"""
        return {
            # Django 配置
            'DJANGO_SECRET_KEY': {
                'key': 'DJANGO_SECRET_KEY',
                'category': 'general',
                'description': 'Django 密钥',
                'is_secret': True,
            },
            'DJANGO_DEBUG': {
                'key': 'DJANGO_DEBUG',
                'category': 'general',
                'description': 'Django 调试模式',
                'is_secret': False,
            },
            'DJANGO_ALLOWED_HOSTS': {
                'key': 'DJANGO_ALLOWED_HOSTS',
                'category': 'general',
                'description': '允许的主机列表',
                'is_secret': False,
            },
            # 飞书配置
            'FEISHU_APP_ID': {
                'key': 'FEISHU_APP_ID',
                'category': 'feishu',
                'description': '飞书应用 App ID',
                'is_secret': False,
            },
            # 群聊名称配置
            'CASE_CHAT_NAME_TEMPLATE': {
                'key': 'CASE_CHAT_NAME_TEMPLATE',
                'category': 'feishu',
                'description': '群聊名称模板',
                'is_secret': False,
            },
            'CASE_CHAT_DEFAULT_STAGE': {
                'key': 'CASE_CHAT_DEFAULT_STAGE',
                'category': 'feishu',
                'description': '默认阶段显示文本',
                'is_secret': False,
            },
            'CASE_CHAT_NAME_MAX_LENGTH': {
                'key': 'CASE_CHAT_NAME_MAX_LENGTH',
                'category': 'feishu',
                'description': '群聊名称最大长度',
                'is_secret': False,
            },
            'FEISHU_APP_SECRET': {
                'key': 'FEISHU_APP_SECRET',
                'category': 'feishu',
                'description': '飞书应用 App Secret',
                'is_secret': True,
            },
            'FEISHU_DEFAULT_OWNER_ID': {
                'key': 'FEISHU_DEFAULT_OWNER_ID',
                'category': 'feishu',
                'description': '飞书群聊默认群主 ID',
                'is_secret': False,
            },
            'FEISHU_WEBHOOK_URL': {
                'key': 'FEISHU_WEBHOOK_URL',
                'category': 'feishu',
                'description': '飞书 Webhook URL',
                'is_secret': False,
            },
            'FEISHU_TIMEOUT': {
                'key': 'FEISHU_TIMEOUT',
                'category': 'feishu',
                'description': '飞书 API 超时时间',
                'is_secret': False,
            },
            # 钉钉配置
            'DINGTALK_APP_KEY': {
                'key': 'DINGTALK_APP_KEY',
                'category': 'dingtalk',
                'description': '钉钉应用 App Key',
                'is_secret': False,
            },
            'DINGTALK_APP_SECRET': {
                'key': 'DINGTALK_APP_SECRET',
                'category': 'dingtalk',
                'description': '钉钉应用 App Secret',
                'is_secret': True,
            },
            'DINGTALK_AGENT_ID': {
                'key': 'DINGTALK_AGENT_ID',
                'category': 'dingtalk',
                'description': '钉钉应用 Agent ID',
                'is_secret': False,
            },
            'DINGTALK_TIMEOUT': {
                'key': 'DINGTALK_TIMEOUT',
                'category': 'dingtalk',
                'description': '钉钉 API 超时时间',
                'is_secret': False,
            },
            # 企业微信配置
            'WECHAT_WORK_CORP_ID': {
                'key': 'WECHAT_WORK_CORP_ID',
                'category': 'wechat_work',
                'description': '企业微信 Corp ID',
                'is_secret': False,
            },
            'WECHAT_WORK_AGENT_ID': {
                'key': 'WECHAT_WORK_AGENT_ID',
                'category': 'wechat_work',
                'description': '企业微信 Agent ID',
                'is_secret': False,
            },
            'WECHAT_WORK_SECRET': {
                'key': 'WECHAT_WORK_SECRET',
                'category': 'wechat_work',
                'description': '企业微信应用 Secret',
                'is_secret': True,
            },
            'WECHAT_WORK_TIMEOUT': {
                'key': 'WECHAT_WORK_TIMEOUT',
                'category': 'wechat_work',
                'description': '企业微信 API 超时时间',
                'is_secret': False,
            },
            # Telegram 配置
            'TELEGRAM_BOT_TOKEN': {
                'key': 'TELEGRAM_BOT_TOKEN',
                'category': 'general',
                'description': 'Telegram Bot Token',
                'is_secret': True,
            },
            # Slack 配置
            'SLACK_BOT_TOKEN': {
                'key': 'SLACK_BOT_TOKEN',
                'category': 'general',
                'description': 'Slack Bot Token',
                'is_secret': True,
            },
            'SLACK_SIGNING_SECRET': {
                'key': 'SLACK_SIGNING_SECRET',
                'category': 'general',
                'description': 'Slack Signing Secret',
                'is_secret': True,
            },
            # 法院短信配置
            'COURT_SMS_MAX_RETRIES': {
                'key': 'COURT_SMS_MAX_RETRIES',
                'category': 'court_sms',
                'description': '法院短信最大重试次数',
                'is_secret': False,
            },
            'COURT_SMS_RETRY_DELAY': {
                'key': 'COURT_SMS_RETRY_DELAY',
                'category': 'court_sms',
                'description': '法院短信重试延迟',
                'is_secret': False,
            },
            'COURT_SMS_AUTO_RECOVERY': {
                'key': 'COURT_SMS_AUTO_RECOVERY',
                'category': 'court_sms',
                'description': '法院短信自动恢复',
                'is_secret': False,
            },
            # AI 配置
            'OLLAMA_MODEL': {
                'key': 'OLLAMA_MODEL',
                'category': 'ai',
                'description': 'Ollama 模型名称',
                'is_secret': False,
            },
            'OLLAMA_BASE_URL': {
                'key': 'OLLAMA_BASE_URL',
                'category': 'ai',
                'description': 'Ollama API 地址',
                'is_secret': False,
            },
            'MOONSHOT_API_KEY': {
                'key': 'MOONSHOT_API_KEY',
                'category': 'ai',
                'description': 'Moonshot AI API Key',
                'is_secret': True,
            },
            'MOONSHOT_BASE_URL': {
                'key': 'MOONSHOT_BASE_URL',
                'category': 'ai',
                'description': 'Moonshot AI API 地址',
                'is_secret': False,
            },
            # 爬虫配置
            'SCRAPER_ENCRYPTION_KEY': {
                'key': 'SCRAPER_ENCRYPTION_KEY',
                'category': 'scraper',
                'description': '爬虫加密密钥',
                'is_secret': True,
            },
            'SCRAPER_HEADLESS': {
                'key': 'SCRAPER_HEADLESS',
                'category': 'scraper',
                'description': '爬虫无头模式',
                'is_secret': False,
            },
            # CORS 配置
            'CORS_ALLOWED_ORIGINS': {
                'key': 'CORS_ALLOWED_ORIGINS',
                'category': 'general',
                'description': 'CORS 允许的来源',
                'is_secret': False,
            },
            'CSRF_TRUSTED_ORIGINS': {
                'key': 'CSRF_TRUSTED_ORIGINS',
                'category': 'general',
                'description': 'CSRF 信任的来源',
                'is_secret': False,
            },
        }
