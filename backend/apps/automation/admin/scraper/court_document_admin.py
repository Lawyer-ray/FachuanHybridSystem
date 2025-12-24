"""
法院文书 Admin
提供文书记录的查看、搜索、过滤功能
"""
from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils import timezone
from django.db.models import Q
from ...models import CourtDocument, DocumentDownloadStatus


def _get_court_document_admin_service():
    """工厂函数：创建法院文书管理服务"""
    from ...services.admin import CourtDocumentAdminService
    return CourtDocumentAdminService()


@admin.register(CourtDocument)
class CourtDocumentAdmin(admin.ModelAdmin):
    """
    法院文书管理 Admin
    
    功能：
    - 查看文书列表（文书名称、法院名称、下载状态、创建时间）
    - 查看文书详情（所有字段）
    - 搜索功能（文书名称、法院名称、文书编号）
    - 过滤器（下载状态、法院名称、创建时间）
    - 为已下载文书提供文件下载链接
    """
    
    list_display = [
        'id',
        'c_wsmc_display',
        'c_fymc_display',
        'download_status_display',
        'file_info_display',
        'created_at',
        'download_link',
    ]
    
    list_filter = [
        'download_status',
        'c_fymc',
        'created_at',
        'downloaded_at',
    ]
    
    search_fields = [
        'c_wsmc',
        'c_fymc',
        'c_wsbh',
        'c_sdbh',
    ]
    
    readonly_fields = [
        'id',
        'scraper_task',
        'case',
        'c_sdbh',
        'c_stbh',
        'wjlj',
        'c_wsbh',
        'c_wsmc',
        'c_fybh',
        'c_fymc',
        'c_wjgs',
        'dt_cjsj',
        'download_status',
        'local_file_path',
        'file_size',
        'file_size_display',
        'error_message',
        'created_at',
        'updated_at',
        'downloaded_at',
        'download_link_detail',
    ]
    
    fieldsets = (
        ('基本信息', {
            'fields': (
                'id',
                'scraper_task',
                'case',
            )
        }),
        ('文书信息', {
            'fields': (
                'c_wsmc',
                'c_wsbh',
                'c_sdbh',
                'c_stbh',
                'c_fymc',
                'c_fybh',
                'c_wjgs',
                'dt_cjsj',
                'wjlj',
            )
        }),
        ('下载状态', {
            'fields': (
                'download_status',
                'local_file_path',
                'file_size',
                'file_size_display',
                'error_message',
                'download_link_detail',
            )
        }),
        ('时间信息', {
            'fields': (
                'created_at',
                'updated_at',
                'downloaded_at',
            )
        }),
    )
    
    ordering = ['-created_at']
    
    date_hierarchy = 'created_at'
    
    list_per_page = 20
    
    def c_wsmc_display(self, obj):
        """格式化显示文书名称"""
        return format_html(
            '<span style="font-weight: bold;">{}</span>',
            obj.c_wsmc[:50] + '...' if len(obj.c_wsmc) > 50 else obj.c_wsmc
        )
    c_wsmc_display.short_description = "文书名称"
    
    def c_fymc_display(self, obj):
        """格式化显示法院名称"""
        return format_html(
            '<span style="color: #007bff;">{}</span>',
            obj.c_fymc
        )
    c_fymc_display.short_description = "法院名称"
    
    def download_status_display(self, obj):
        """带颜色的状态显示"""
        colors = {
            DocumentDownloadStatus.PENDING: "#ffa500",
            DocumentDownloadStatus.DOWNLOADING: "#007bff",
            DocumentDownloadStatus.SUCCESS: "#28a745",
            DocumentDownloadStatus.FAILED: "#dc3545",
        }
        icons = {
            DocumentDownloadStatus.PENDING: "⏳",
            DocumentDownloadStatus.DOWNLOADING: "⬇️",
            DocumentDownloadStatus.SUCCESS: "✅",
            DocumentDownloadStatus.FAILED: "❌",
        }
        color = colors.get(obj.download_status, "#666")
        icon = icons.get(obj.download_status, "")
        
        return format_html(
            '<span style="color: {}; font-weight: bold;">{} {}</span>',
            color,
            icon,
            obj.get_download_status_display()
        )
    download_status_display.short_description = "下载状态"
    
    def file_info_display(self, obj):
        """显示文件信息"""
        if obj.file_size:
            # 转换为易读格式
            size = obj.file_size
            if size >= 1024 * 1024:  # MB
                size_str = f'{size / (1024 * 1024):.2f} MB'
            elif size >= 1024:  # KB
                size_str = f'{size / 1024:.2f} KB'
            else:
                size_str = f'{size} B'
            
            return format_html(
                '<span style="color: #666;">{}</span>',
                size_str
            )
        return format_html('<span style="color: #999;">-</span>')
    file_info_display.short_description = "文件大小"
    
    def file_size_display(self, obj):
        """详情页显示文件大小"""
        if obj.file_size:
            size = obj.file_size
            if size >= 1024 * 1024:  # MB
                size_str = f'{size / (1024 * 1024):.2f} MB'
            elif size >= 1024:  # KB
                size_str = f'{size / 1024:.2f} KB'
            else:
                size_str = f'{size} B'
            
            return format_html(
                '<span style="color: #007bff; font-weight: bold;">{}</span> ({} 字节)',
                size_str,
                f'{size:,}'
            )
        return format_html('<span style="color: #999;">-</span>')
    file_size_display.short_description = "文件大小"
    
    def download_link(self, obj):
        """列表页的下载链接"""
        if obj.download_status == DocumentDownloadStatus.SUCCESS and obj.local_file_path:
            # 提取文件名
            import os
            filename = os.path.basename(obj.local_file_path)
            
            return format_html(
                '<a href="/media/{}" target="_blank" '
                'style="background-color: #28a745; color: white; padding: 5px 10px; '
                'border-radius: 4px; text-decoration: none; display: inline-block; font-size: 12px;">'
                '📥 下载</a>',
                obj.local_file_path
            )
        return format_html('<span style="color: #999;">-</span>')
    download_link.short_description = "文件下载"
    
    def download_link_detail(self, obj):
        """详情页的下载链接"""
        if obj.download_status == DocumentDownloadStatus.SUCCESS and obj.local_file_path:
            import os
            filename = os.path.basename(obj.local_file_path)
            
            return format_html(
                '<a href="/media/{}" target="_blank" '
                'style="background-color: #28a745; color: white; padding: 10px 20px; '
                'border-radius: 4px; text-decoration: none; display: inline-block; font-size: 14px;">'
                '📥 下载文件: {}</a>',
                obj.local_file_path,
                filename
            )
        elif obj.download_status == DocumentDownloadStatus.FAILED:
            return format_html(
                '<span style="color: #dc3545; font-weight: bold;">下载失败</span>'
            )
        elif obj.download_status == DocumentDownloadStatus.DOWNLOADING:
            return format_html(
                '<span style="color: #007bff; font-weight: bold;">下载中...</span>'
            )
        else:
            return format_html(
                '<span style="color: #ffa500; font-weight: bold;">待下载</span>'
            )
    download_link_detail.short_description = "文件下载"
    
    def has_add_permission(self, request):
        """禁用添加功能（文书记录由系统自动创建）"""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """允许删除"""
        return True
    
    # 定义批量操作
    actions = ['batch_download_documents', 'batch_delete_with_files', 'retry_failed_downloads']
    
    @admin.action(description="批量下载选中的文书")
    def batch_download_documents(self, request, queryset):
        """批量下载文书"""
        try:
            service = _get_court_document_admin_service()
            document_ids = list(queryset.values_list('id', flat=True))
            result = service.batch_download_documents(document_ids)
            
            self.message_user(
                request,
                f"✅ 已启动 {result['started_download']} 个文书的下载任务"
            )
            
            if result['already_downloaded'] > 0:
                self.message_user(
                    request,
                    f"ℹ️ {result['already_downloaded']} 个文书已经下载完成"
                )
        except Exception as e:
            self.message_user(
                request,
                f"❌ 批量下载失败: {str(e)}",
                level=messages.ERROR
            )
    
    @admin.action(description="删除选中的文书（包含文件）")
    def batch_delete_with_files(self, request, queryset):
        """批量删除文书和文件"""
        try:
            service = _get_court_document_admin_service()
            document_ids = list(queryset.values_list('id', flat=True))
            result = service.batch_delete_documents(document_ids, delete_files=True)
            
            self.message_user(
                request,
                f"✅ 已删除 {result['deleted_records']} 条记录和 {result['deleted_files']} 个文件"
            )
            
            if result['file_errors']:
                self.message_user(
                    request,
                    f"⚠️ {len(result['file_errors'])} 个文件删除失败",
                    level=messages.WARNING
                )
        except Exception as e:
            self.message_user(
                request,
                f"❌ 批量删除失败: {str(e)}",
                level=messages.ERROR
            )
    
    @admin.action(description="重试失败的下载")
    def retry_failed_downloads(self, request, queryset):
        """重试失败的下载"""
        try:
            service = _get_court_document_admin_service()
            document_ids = list(queryset.values_list('id', flat=True))
            result = service.retry_failed_downloads(document_ids)
            
            self.message_user(
                request,
                result['message']
            )
        except Exception as e:
            self.message_user(
                request,
                f"❌ 重试失败: {str(e)}",
                level=messages.ERROR
            )
    
    def get_queryset(self, request):
        """优化查询性能"""
        qs = super().get_queryset(request)
        # 预加载关联的任务和案件
        return qs.select_related('scraper_task', 'case')