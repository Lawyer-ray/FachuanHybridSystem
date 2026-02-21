"""爬虫工具 Admin 站点自定义"""

from django.contrib.admin import AdminSite


def customize_admin_index(site: AdminSite) -> None:
    """自定义 admin 首页（当前为空实现）"""
    pass
