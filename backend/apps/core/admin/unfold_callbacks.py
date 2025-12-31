"""
Django Unfold 回调函数

提供 Unfold Admin 主题所需的回调函数。
"""

from django.conf import settings


def environment_callback(request):
    """
    返回当前环境标识，用于 Unfold 顶部显示环境标签。
    
    Returns:
        tuple: (环境名称, 颜色类型) 或 None
    """
    if settings.DEBUG:
        return ("开发环境", "warning")
    return ("生产环境", "success")
