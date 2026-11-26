"""系统配置 Admin

提供 Django Admin 界面来管理系统配置项，包括飞书、钉钉等第三方服务配置。
"""

from typing import Any, ClassVar, cast

from django.contrib import admin, messages
from django.core.cache import cache
from django.http import HttpRequest, HttpResponseRedirect
from django.urls import path, reverse
from django.utils.html import format_html

from apps.core.models import SystemConfig
from apps.core.security.secret_codec import SecretCodec
from apps.core.security.secret_display import value_cell

from ._system_config_data import get_default_configs
from .forms import SystemConfigAdminForm

#: 代码里登记了说明的键，编辑页的「描述」行换成这个只读字段（名字见 `description_display`）。
_CODE_DESCRIPTION_FIELD = "description_display"

#: 只读说明行的提示：文案在代码里，改库没用。
#:
#: 它跟随只读值一起渲染，而不走 `help_text`：本项目的 `admin/includes/fieldset.html`
#: 有意不渲染字段 help_text 与 fieldset description，挂在那两处的提示根本看不见。
_CODE_DESCRIPTION_HELP = "本说明由代码维护，要改请改 apps/core/admin/_system_config_data/。"


def _code_description_of(obj: SystemConfig | None) -> str | None:
    """obj 对应的代码文案；新建页（无 obj）或代码里没登记这个键时返回 None。"""
    if obj is None:
        return None
    # 延迟导入：`system_config_admin_service` 反过来 import 本包的 `_system_config_data`。
    from apps.core.services.system_config_admin_service import code_description_of

    return code_description_of(str(obj.key or ""))


@admin.register(SystemConfig)
class SystemConfigAdmin(admin.ModelAdmin):  # pragma: no cover
    """系统配置 Admin"""

    show_in_index = False  # 不在左侧菜单显示，通过右上角快捷入口访问

    form = SystemConfigAdminForm
    # list_display / list_filter 刻意不设：本页 `result_list` 整块重写成分组卡片，
    # 二者都不参与渲染（list_filter 的侧栏还被 CSS 隐藏），只会白跑 DISTINCT 查询。
    # 搜的是库里的副本（`description` 列），界面展示的是代码文案——两者可能不同：
    # 代码里改过说明后库里那份还是旧的，按旧措辞仍然能搜到这一行。
    search_fields = ["key", "description"]
    ordering = ["category", "key"]
    change_list_template = "admin/core/systemconfig/change_list.html"

    fieldsets = (
        ("基本信息", {"fields": ("key", "value", "category", "description")}),
        ("安全设置", {"fields": ("is_secret", "is_active"), "classes": ("collapse",)}),
        ("时间信息", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    readonly_fields: ClassVar[list[str]] = ["created_at", "updated_at"]

    def get_readonly_fields(self, request: Any, obj: Any = None) -> Any:
        """代码里登记了这个键 → 「描述」只读。

        库里那份 `description` 此时是兜底/部署备注，不再展示（`get_fieldsets` 把它换成
        只读的代码文案行），也就不该让人在表单里改一个不会生效的副本。
        """
        readonly = list(self.readonly_fields)
        if _code_description_of(obj) is not None:
            readonly.extend(["description", _CODE_DESCRIPTION_FIELD])
        return readonly

    def get_fieldsets(self, request: Any, obj: Any = None) -> Any:
        """代码里登记了这个键 → 「描述」行换成只读的代码文案。

        只读字段的展示值取自实例的属性（`AdminReadonlyField.contents`），所以要真的
        显示代码文案，必须把该行换成一个由 `description_display` 供值的字段；
        留在原字段上只能渲染出库里那句旧话。
        """
        fieldsets = super().get_fieldsets(request, obj)
        if _code_description_of(obj) is None:
            return fieldsets
        return [
            (
                name,
                {
                    **options,
                    "fields": tuple(
                        _CODE_DESCRIPTION_FIELD if field == "description" else field for field in options["fields"]
                    ),
                },
            )
            for name, options in fieldsets
        ]

    @admin.display(description="描述")
    def description_display(self, obj: SystemConfig) -> Any:
        """编辑页「描述」的展示值：代码文案优先，库里的只在这个键不在代码里时兜底。"""
        code = _code_description_of(obj)
        if code is None:
            return str(obj.description or "")
        return format_html('{}<div class="help">{}</div>', code, _CODE_DESCRIPTION_HELP)

    def get_urls(self) -> list[Any]:  # pragma: no cover
        """添加自定义 URL"""
        urls = super().get_urls()
        custom_urls = [
            path(
                "init-defaults/",
                self.admin_site.admin_view(self.init_defaults_view),
                name="core_systemconfig_init_defaults",
            ),
            path(
                "clear-cache/",
                self.admin_site.admin_view(self.clear_cache_view),
                name="core_systemconfig_clear_cache",
            ),
            path(
                "trigger-update/",
                self.admin_site.admin_view(self.trigger_update_view),
                name="core_systemconfig_trigger_update",
            ),
        ]
        return custom_urls + urls

    def changelist_view(self, request: Any, extra_context: Any = None) -> Any:  # pragma: no cover
        """自定义列表页面：按分类分组的卡片列表。

        分组数据取自 `changelist.queryset`（已应用搜索框条件），所以搜索是真的能用——
        早先这里直接 `SystemConfig.objects.all()`，搜索框等于摆设。
        敏感项的值在这里就算成「已配置 N 个值」，模板不再写死 `••••••••`。
        """
        extra_context = extra_context or {}
        extra_context["show_init_button"] = True
        extra_context["show_clear_cache_button"] = True

        changelist = self.get_changelist_instance(request)
        grouped: dict[str, list[dict[str, Any]]] = {}
        for config in changelist.queryset.order_by("category", "key"):
            value_text, value_title = value_cell(config.value, is_secret=bool(config.is_secret))
            grouped.setdefault(config.category, []).append(
                {
                    "config": config,
                    "value_text": value_text,
                    "value_title": value_title,
                    # 卡片上的说明同样以代码为准；库里的副本只在代码没登记这个键时兜底。
                    "effective_description": _code_description_of(config) or str(config.description or ""),
                }
            )

        # 遍历「枚举顺序 + 库里实际出现但枚举里没有的分类」：
        # 只认枚举会让脏分类值（如 0038 误删 onlyoffice 后留存的 3 条 ONLYOFFICE_*）
        # 在页面上凭空消失——数据还在库里，用户却看不见、也点不进去改。
        category_labels = dict(SystemConfig.Category.choices)
        unknown_categories = sorted(name for name in grouped if name not in category_labels)
        groups = []
        for category in [*SystemConfig.Category.values, *unknown_categories]:
            rows = grouped.get(category, [])
            if rows:
                groups.append(
                    {
                        "category": category,
                        "label": category_labels.get(category, f"{category}（未知分类）"),
                        "count": len(rows),
                        "rows": rows,
                    }
                )

        extra_context["grouped_configs"] = groups
        return super().changelist_view(request, extra_context=extra_context)

    def save_model(self, request: Any, obj: SystemConfig, form: Any, change: bool) -> None:  # pragma: no cover
        previous_key = ""
        if change and obj.pk:
            previous = SystemConfig.objects.filter(pk=obj.pk).only("key").first()
            previous_key = str(previous.key or "") if previous else ""
        super().save_model(request, obj, form, change)
        self._clear_config_cache(obj.key, previous_key=previous_key)

    def init_defaults_view(self, request: Any) -> HttpResponseRedirect:  # pragma: no cover
        """初始化默认配置项（AI 服务由「AI 平台」管理页负责、文档解析由「解析平台」管理页负责，此处跳过）"""
        defaults = self._get_default_configs()
        created_count = 0

        for config in defaults:
            if config.get("category") in ("ai", "document_parsing"):
                continue
            _, created = SystemConfig.objects.get_or_create(
                key=config["key"],
                defaults={
                    "value": config.get("value", ""),
                    "category": config["category"],
                    "description": config["description"],
                    "is_secret": config.get("is_secret", False),
                },
            )
            if created:
                created_count += 1

        if created_count > 0:
            messages.success(request, f"成功创建 {created_count} 个默认配置项")
        else:
            messages.info(request, "所有默认配置项已存在")

        return HttpResponseRedirect(reverse("admin:core_systemconfig_changelist"))

    def clear_cache_view(self, request: Any) -> HttpResponseRedirect:  # pragma: no cover
        """清除配置缓存"""
        cache.delete("system_config:all")
        for config in SystemConfig.objects.all():
            cache.delete(f"system_config:{config.key}")
        messages.success(request, "配置缓存已清除")
        return HttpResponseRedirect(reverse("admin:core_systemconfig_changelist"))

    def trigger_update_view(self, request: HttpRequest) -> HttpResponseRedirect:  # pragma: no cover
        """触发系统更新任务。"""
        if request.method != "POST":
            messages.error(request, "仅支持 POST 请求")
            return HttpResponseRedirect(reverse("admin:core_systemconfig_changelist"))

        if not self.has_change_permission(request):
            messages.error(request, "无权限执行系统更新")
            return HttpResponseRedirect(reverse("admin:core_systemconfig_changelist"))

        raw_enable_post_update_setup = str(request.POST.get("enable_post_update_setup", "")).strip().lower()
        enable_post_update_setup = raw_enable_post_update_setup in {"1", "true", "on", "yes"}

        username = str(request.user.get_username() or request.user.pk or "")
        result = self._get_system_update_service().trigger_update(
            triggered_by=username,
            enable_post_update_setup=enable_post_update_setup,
        )
        if bool(result.get("accepted")):
            if enable_post_update_setup:
                messages.success(request, "更新任务已提交，将自动执行 uv sync 与 migrate。")
            else:
                messages.success(request, "更新任务已提交，请稍后刷新查看状态")
        else:
            message_text = str(result.get("message") or "更新任务提交失败")
            messages.warning(request, message_text)
        return HttpResponseRedirect(reverse("admin:core_systemconfig_changelist"))

    def _get_default_configs(self) -> list[dict[str, Any]]:  # pragma: no cover
        """委托给模块级函数"""
        return get_default_configs()

    @staticmethod
    def _clear_config_cache(key: str, *, previous_key: str = "") -> None:  # pragma: no cover
        if previous_key and previous_key != key:
            cache.delete(f"system_config:{previous_key}")
        cache.delete(f"system_config:{key}")

    @staticmethod
    def _get_system_update_service() -> Any:  # pragma: no cover
        from apps.core.dependencies import build_system_update_service

        return build_system_update_service()
