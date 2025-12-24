"""
自动化工具二级菜单配置
通过自定义 app_list 实现分组显示和侧边栏排序

自动化工具栏目：文书送达定时任务、法院短信、财产保全询价、测试法院系统
自动化记录栏目：Token管理、Token获取历史、文书查询历史、法院文书、任务管理

侧边栏顺序：
1. Client CRM（当事人管理）
2. Contracts（合同管理）
3. CASES（案件管理）
4. 自动化工具
5. 自动化记录
6. 核心系统
7. ORGANIZATION（组织管理）
8. DJANGO Q
9. 认证和授权
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

# 侧边栏排序配置
APP_ORDER = [
    'client',              # 1. Client CRM（当事人管理）
    'contracts',           # 2. Contracts（合同管理）
    'cases',               # 3. CASES（案件管理）
    'automation',          # 4. 自动化工具
    'automation_records',  # 5. 自动化记录（虚拟分组）
    'core',                # 6. 核心系统
    'organization',        # 7. ORGANIZATION（组织管理）
    'django_q',            # 8. DJANGO Q
    'auth',                # 9. 认证和授权
]


def customize_admin_index(admin_site):
    """
    自定义 admin 首页：
    1. 将 automation 模型分为两个分组（自动化工具、自动化记录）
    2. 按指定顺序排列侧边栏
    """
    original_app_list = admin_site.get_app_list
    
    def custom_app_list(request, app_label=None):
        # 获取原始的 app_list
        app_list = original_app_list(request, app_label)
        
        # 找到 automation app 并分离
        automation_app = None
        automation_index = None
        
        for idx, app in enumerate(app_list):
            if app.get('app_label') == 'automation':
                automation_app = app
                automation_index = idx
                break
        
        if automation_app and automation_index is not None:
            # 分离模型到两个分组
            tool_models = []      # 自动化工具
            record_models = []    # 自动化记录
            
            for model in automation_app.get('models', []):
                model_name = model.get('object_name', '')
                model_verbose_name = model.get('name', '')
                
                # 自动化工具：文书送达定时任务、法院短信、财产保全询价、测试法院系统
                is_tool_model = (
                    'DocumentDeliverySchedule' in model_name or
                    'CourtSMS' in model_name or
                    'PreservationQuote' in model_name or
                    'InsuranceQuote' in model_name or
                    'TestCourt' in model_name or
                    '文书送达定时任务' in model_verbose_name or
                    '法院短信' in model_verbose_name or
                    '财产保全询价' in model_verbose_name or
                    '测试法院' in model_verbose_name
                )
                
                # 自动化记录：Token管理、Token获取历史、文书查询历史、法院文书、任务管理
                is_record_model = (
                    'CourtToken' in model_name or
                    'TokenAcquisitionHistory' in model_name or
                    'DocumentQueryHistory' in model_name or
                    'CourtDocument' in model_name or
                    'ScraperTask' in model_name or
                    'Token管理' in model_verbose_name or
                    'Token获取历史' in model_verbose_name or
                    '文书查询历史' in model_verbose_name or
                    '法院文书' in model_verbose_name or
                    '任务管理' in model_verbose_name or
                    '爬虫任务' in model_verbose_name
                )
                
                if is_tool_model:
                    tool_models.append(model)
                elif is_record_model:
                    record_models.append(model)
                # 其他模型不显示（如快速下载、文档处理等）
            
            # 创建自动化记录分组
            if record_models:
                record_group = {
                    'name': '自动化记录',
                    'app_label': 'automation_records',
                    'app_url': '/admin/automation/',
                    'has_module_perms': True,
                    'models': record_models
                }
                
                # 更新 automation app 只包含工具模型
                if tool_models:
                    automation_app['models'] = tool_models
                    # 在 automation 后面插入记录分组
                    app_list.insert(automation_index + 1, record_group)
                else:
                    # 如果没有工具模型，用记录分组替换
                    app_list[automation_index] = record_group
            elif tool_models:
                # 只有工具模型
                automation_app['models'] = tool_models
            else:
                # 没有任何模型，移除 automation app
                app_list.pop(automation_index)
        
        # 按指定顺序排序 app_list
        def get_app_order(app):
            app_label = app.get('app_label', '')
            try:
                return APP_ORDER.index(app_label)
            except ValueError:
                # 未在列表中的 app 放到最后
                return len(APP_ORDER)
        
        app_list.sort(key=get_app_order)
        
        return app_list
    
    admin_site.get_app_list = custom_app_list
