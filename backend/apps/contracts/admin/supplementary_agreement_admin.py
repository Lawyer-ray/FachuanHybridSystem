"""
补充协议 Admin 配置
"""
from django.contrib import admin
from ..models import SupplementaryAgreement, SupplementaryAgreementParty


class SupplementaryAgreementPartyInline(admin.TabularInline):
    """补充协议当事人内联编辑"""
    model = SupplementaryAgreementParty
    extra = 1
    autocomplete_fields = ["client"]
    verbose_name = "当事人"
    verbose_name_plural = "当事人"


@admin.register(SupplementaryAgreement)
class SupplementaryAgreementAdmin(admin.ModelAdmin):
    """补充协议 Admin"""
    
    list_display = [
        "id", 
        "name", 
        "contract", 
        "party_count",
        "created_at", 
        "updated_at"
    ]
    list_filter = ["created_at", "updated_at"]
    search_fields = ["name", "contract__name"]
    readonly_fields = ["created_at", "updated_at"]
    autocomplete_fields = ["contract"]
    
    inlines = [SupplementaryAgreementPartyInline]
    
    fieldsets = (
        ("基本信息", {
            "fields": ("contract", "name")
        }),
        ("时间信息", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
    
    def party_count(self, obj):
        """当事人数量"""
        return obj.parties.count()
    party_count.short_description = "当事人数量"
    
    def get_queryset(self, request):
        """优化查询"""
        qs = super().get_queryset(request)
        return qs.select_related("contract").prefetch_related("parties")
