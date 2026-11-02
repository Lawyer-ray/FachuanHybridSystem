"""全站 admin 配置字段校验：`search_fields` / `list_filter` / `list_display` 引用的
列必须真实存在于模型上。

**回归背景（真实 500）**：`DocumentTemplate.description` 早被迁移
`0006_remove_documenttemplate_description` 从模型删掉，但 `DocumentTemplateAdmin.search_fields`
一直没同步。表现是 admin 列表页本身正常，**只要输入关键词搜索（`?q=清单`）就**：

    FieldError: Cannot resolve keyword 'description' into field.

更糟的是当时的单测在断言 `"description" in admin.search_fields`——把 bug 固化成了
「预期」，CI 永远是绿的。所以这里不写针对某个字段的断言，而是用反射**全站扫一遍**：
以后谁删了模型字段却没改 admin，这个测试立刻红，不用等律师点搜索才发现。

口径说明（为什么只校验三类）：
- `search_fields`：Django 直接拼进 ORM `filter()`，无效字段 = FieldError 500；
- `list_filter`：同理，点侧边筛选就炸；
- `list_display`：允许放方法名/`@admin.display` 属性，所以只在「既不是模型字段、
  也不是 `admin` 上的可调用属性」时才算错。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pytest
from django.contrib import admin
from django.db.models import Model


def _registered_admins() -> list[tuple[type[Model], Any]]:
    """全站已注册的 (model, admin instance)，按 model 名排序保证失败信息稳定。"""
    items = [(model, model_admin) for model, model_admin in admin.site._registry.items()]
    return sorted(items, key=lambda pair: f"{pair[0]._meta.app_label}.{pair[0].__name__}")


def _field_names(model: type[Model]) -> set[str]:
    """模型上所有可被 ORM 解析的字段名（含外键的 `fk` 与 `fk_id`）。"""
    names: set[str] = set()
    for field in model._meta.get_fields():
        names.add(field.name)
        attname = getattr(field, "attname", None)
        if attname:
            names.add(attname)
    return names


#: Django `search_fields` 支持的 lookup 后缀（`id__icontains` 里的 `icontains`）。
#: 注意：**admin search_fields 并不支持 lookup**（那是 ORM filter 的语法），
#: 写了 `id__icontains` 会被当成「关联穿透到名为 icontains 的字段」→ FieldError。
#: 这里把已知 lookup 名当成错误而不是当成字段，正好能抓出那类误用。
_ORM_LOOKUPS: frozenset[str] = frozenset(
    {
        "exact",
        "iexact",
        "contains",
        "icontains",
        "in",
        "gt",
        "gte",
        "lt",
        "lte",
        "startswith",
        "istartswith",
        "endswith",
        "iendswith",
        "range",
        "date",
        "year",
        "month",
        "day",
        "week",
        "week_day",
        "isnull",
        "regex",
        "iregex",
        "search",
    }
)


def _resolve_path(model: type[Model], path: str) -> str | None:
    """校验一个 admin 字段路径（支持 `fk__sub_field` 关联穿透）。

    Returns:
        None = 合法；否则返回给人看的错误原因。
    """
    current: type[Model] = model
    parts = [p for p in path.split("__") if p not in {"", "pk"}]
    for index, part in enumerate(parts):
        if part in _ORM_LOOKUPS:
            # lookup 名出现在路径里 = 把 ORM filter 语法误用进 admin search_fields
            return f"{part!r} 是 ORM lookup，admin search_fields 不支持 lookup 语法"
        if part not in _field_names(current):
            return f"字段 {part!r} 不存在于 {current.__name__}"
        # 关联穿透：拿到目标模型继续校验
        try:
            field = current._meta.get_field(part)
        except Exception:
            # 非模型字段但名字合法（如 attname），后面还有段就该出错
            if index < len(parts) - 1:
                return f"{part!r} 不是关联字段，无法继续穿透到 {parts[index + 1]!r}"
            return None
        related = getattr(field, "related_model", None)
        if related is not None:
            current = related
    return None


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable):
        return [v for v in value if isinstance(v, str)]
    return []


class TestAdminFieldReferences:
    """全站 admin 配置的字段引用必须能在模型上解析。"""

    def test_search_fields_exist_on_model(self) -> None:
        errors: list[str] = []
        for model, model_admin in _registered_admins():
            for path in _as_str_list(getattr(model_admin, "search_fields", None)):
                # 搜索项允许用 `=exact` / `^startswith` / `@search` 等前缀修饰
                cleaned = path.lstrip("=^@$~")
                reason = _resolve_path(model, cleaned)
                if reason:
                    errors.append(f"{model._meta.label}.admin.search_fields: {path!r} → {reason}")
        assert not errors, "admin search_fields 引用了模型上不存在的字段（搜索即 500）：\n" + "\n".join(errors)

    def test_list_filter_exist_on_model(self) -> None:
        errors: list[str] = []
        for model, model_admin in _registered_admins():
            for path in _as_str_list(getattr(model_admin, "list_filter", None)):
                cleaned = path.lstrip("=^@$~")
                if cleaned in {"", "pk"}:
                    continue
                reason = _resolve_path(model, cleaned)
                if reason:
                    errors.append(f"{model._meta.label}.admin.list_filter: {path!r} → {reason}")
        assert not errors, "admin list_filter 引用了模型上不存在的字段（点筛选即 500）：\n" + "\n".join(errors)

    def test_list_display_entries_are_resolvable(self) -> None:
        """`list_display` 允许方法名，所以只拦「既非模型字段、也非 admin 属性」的项。"""
        errors: list[str] = []
        for model, model_admin in _registered_admins():
            for name in _as_str_list(getattr(model_admin, "list_display", None)):
                if name in {"__str__", "pk"}:
                    continue
                if _resolve_path(model, name) is None:
                    continue
                # 不是模型字段：允许是 admin/模型上的可调用属性（@admin.display 方法）
                if hasattr(model_admin, name) or hasattr(model, name):
                    continue
                errors.append(f"{model._meta.label}.admin.list_display: {name!r} 既不是模型字段，也不是 admin/模型属性")
        assert not errors, "admin list_display 有无解项（列表页即报错）：\n" + "\n".join(errors)

    def test_document_template_search_does_not_reference_removed_field(self) -> None:
        """案件级精确断言：保留对本次 500 的直接防复发哨兵。

        全站扫描已经能覆盖，但这条把「谁踩过这个坑」写死在测试里——
        失败信息一眼能看出是哪个历史 bug 又回来了。
        """
        from apps.documents.admin.document_template_admin import DocumentTemplateAdmin
        from apps.documents.models import DocumentTemplate

        model_admin = DocumentTemplateAdmin(DocumentTemplate, admin.site)
        assert "description" not in model_admin.search_fields
        assert model_admin.search_fields, "search_fields 不能为空——模板搜索是实际在用的功能"
        assert "name" in model_admin.search_fields


@pytest.mark.django_db
def test_document_template_search_actually_works(client: Any) -> None:
    """端到端：真的走一次 admin 搜索，确认不再 FieldError。

    前面的反射测试看的是配置文本；这条看的是 Django 真的能把 `?q=` 拼进 ORM。
    用 `get_changelist_instance` 而不是请求整个 admin 页面，避免依赖模板/静态资源。
    """
    from django.contrib.admin.sites import AdminSite
    from django.contrib.auth import get_user_model
    from django.test import RequestFactory

    from apps.documents.admin.document_template_admin import DocumentTemplateAdmin
    from apps.documents.models import DocumentTemplate

    DocumentTemplate.objects.create(name="清单类模板-回归样本")

    site = AdminSite()
    model_admin = DocumentTemplateAdmin(DocumentTemplate, site)
    request = RequestFactory().get("/admin/documents/documenttemplate/", {"q": "清单"})
    request.user = get_user_model().objects.create_superuser(
        username="admin_field_ref_probe", email="probe@example.com", password="x"
    )

    changelist = model_admin.get_changelist_instance(request)
    results = list(changelist.get_queryset(request))
    assert any("清单" in t.name for t in results), "搜索「清单」应能命中刚建的模板"
