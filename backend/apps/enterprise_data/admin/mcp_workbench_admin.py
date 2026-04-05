"""MCP 调试工作台 Admin。"""

from __future__ import annotations

import json
from typing import Any

from django.contrib import admin, messages
from django.template.response import TemplateResponse

from apps.enterprise_data.models import McpWorkbench
from apps.enterprise_data.services import McpWorkbenchService


@admin.register(McpWorkbench)
class McpWorkbenchAdmin(admin.ModelAdmin[McpWorkbench]):
    """MCP tools 调试页。"""

    def has_module_permission(self, request: object) -> bool:
        return bool(request.user and request.user.is_active and request.user.is_superuser)

    def has_view_permission(self, request: object, obj: Any | None = None) -> bool:
        return bool(request.user and request.user.is_active and request.user.is_superuser)

    def has_add_permission(self, request: object) -> bool:
        return False

    def has_change_permission(self, request: object, obj: Any | None = None) -> bool:
        return False

    def has_delete_permission(self, request: object, obj: Any | None = None) -> bool:
        return False

    def get_model_perms(self, request: object) -> dict[str, bool]:
        if not self.has_view_permission(request):
            return {}
        return {"view": True, "add": False, "change": False, "delete": False}

    def changelist_view(self, request: object, extra_context: dict[str, object] | None = None) -> TemplateResponse:
        service = McpWorkbenchService()
        providers = service.list_providers()
        provider_names = [str(item.get("name", "") or "").strip() for item in providers if item.get("name")]
        default_provider = self._pick_default_provider(providers=providers)

        selected_provider = self._pick_selected_provider(
            request=request,
            provider_names=provider_names,
            default_provider=default_provider,
        )
        selected_tool_name = self._pick_selected_tool_name(request=request)
        arguments_json = str(request.POST.get("arguments_json", "") or "").strip() if request.method == "POST" else "{}"
        execution_result: dict[str, Any] | None = None
        execution_error = ""
        actor_username = str(getattr(request.user, "username", "") or "").strip()
        actor_is_superuser = bool(getattr(request.user, "is_superuser", False))

        if request.method == "POST" and request.POST.get("_action") == "execute":
            try:
                parsed_arguments = self._parse_arguments(arguments_json)
                execution_result = service.execute_tool(
                    provider=selected_provider,
                    tool_name=selected_tool_name,
                    arguments=parsed_arguments,
                    actor_username=actor_username,
                    actor_is_superuser=actor_is_superuser,
                )
                arguments_json = self._to_pretty_json(parsed_arguments)
                messages.success(request, "工具执行成功")
            except Exception as exc:
                execution_error = str(exc).strip() or type(exc).__name__
                messages.error(request, f"工具执行失败: {execution_error}")
        elif request.method == "POST" and request.POST.get("_action") == "replay":
            execution_id = request.POST.get("execution_id", "")
            try:
                execution_result = service.replay_execution(
                    execution_id=int(str(execution_id or "").strip() or "0"),
                    actor_username=actor_username,
                    actor_is_superuser=actor_is_superuser,
                )
                selected_provider = str(
                    execution_result.get("provider", selected_provider) or selected_provider
                ).strip()
                selected_tool_name = str(execution_result.get("tool", selected_tool_name) or selected_tool_name).strip()
                arguments_payload = execution_result.get("arguments")
                if isinstance(arguments_payload, dict):
                    arguments_json = self._to_pretty_json(arguments_payload)
                messages.success(request, "重放执行成功")
            except Exception as exc:
                execution_error = str(exc).strip() or type(exc).__name__
                messages.error(request, f"重放执行失败: {execution_error}")

        load_error = ""
        tools: list[dict[str, Any]] = []
        resolved_provider = selected_provider
        try:
            described = service.describe_tools(provider=selected_provider, actor_is_superuser=actor_is_superuser)
            tools = described.get("tools", [])
            resolved_provider = str(described.get("provider", selected_provider) or selected_provider).strip()
        except Exception as exc:
            load_error = str(exc).strip() or type(exc).__name__
            messages.error(request, f"加载工具失败: {load_error}")

        selected_tool = self._pick_selected_tool(tools=tools, selected_tool_name=selected_tool_name)
        if selected_tool is None and tools:
            selected_tool = tools[0]
            selected_tool_name = str(selected_tool.get("name", "") or "").strip()
        if request.method != "POST" and selected_tool is not None:
            arguments_json = self._to_pretty_json(self._build_default_arguments(selected_tool))
        history = service.list_history(
            provider=resolved_provider,
            tool_name=selected_tool_name,
            limit=30,
            actor_is_superuser=actor_is_superuser,
        )

        context = {
            "title": "MCP 调试工作台",
            "opts": self.model._meta,
            "providers": providers,
            "selected_provider": resolved_provider,
            "tools": tools,
            "selected_tool": selected_tool,
            "arguments_json": arguments_json,
            "selected_tool_name": selected_tool_name,
            "selected_tool_schema_json": self._to_pretty_json((selected_tool or {}).get("input_schema", {})),
            "selected_tool_sample_json": self._to_pretty_json((selected_tool or {}).get("sample") or {}),
            "execution_result_json": self._to_pretty_json(execution_result or {}),
            "execution_error": execution_error,
            "load_error": load_error,
            "history": history,
            "has_view_permission": self.has_view_permission(request),
            "site_header": self.admin_site.site_header,
            "site_title": self.admin_site.site_title,
        }
        return TemplateResponse(
            request,
            "admin/enterprise_data/mcp_workbench/change_list.html",
            context,
        )

    @staticmethod
    def _pick_default_provider(*, providers: list[dict[str, Any]]) -> str:
        for item in providers:
            if item.get("is_default") and item.get("name"):
                return str(item["name"]).strip()
        for item in providers:
            if item.get("name"):
                return str(item["name"]).strip()
        return ""

    @staticmethod
    def _pick_selected_provider(*, request: Any, provider_names: list[str], default_provider: str) -> str:
        selected = str(request.POST.get("provider", "") or "").strip()
        if not selected:
            selected = str(request.GET.get("provider", "") or "").strip()
        if selected in provider_names:
            return selected
        return default_provider

    @staticmethod
    def _pick_selected_tool_name(*, request: Any) -> str:
        selected = str(request.POST.get("tool_name", "") or "").strip()
        if selected:
            return selected
        return str(request.GET.get("tool", "") or "").strip()

    @staticmethod
    def _pick_selected_tool(*, tools: list[dict[str, Any]], selected_tool_name: str) -> dict[str, Any] | None:
        if not selected_tool_name:
            return None
        for item in tools:
            if str(item.get("name", "") or "").strip() == selected_tool_name:
                return item
        return None

    @staticmethod
    def _parse_arguments(arguments_json: str) -> dict[str, Any]:
        text = str(arguments_json or "").strip() or "{}"
        try:
            payload = json.loads(text)
        except (TypeError, ValueError) as exc:
            raise ValueError("参数 JSON 格式不正确") from exc
        if not isinstance(payload, dict):
            raise ValueError("参数必须是 JSON Object")
        return payload

    @staticmethod
    def _build_default_arguments(tool: dict[str, Any]) -> dict[str, Any]:
        schema = tool.get("input_schema")
        if not isinstance(schema, dict):
            return {}
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            return {}
        required = schema.get("required")
        required_set = set(required if isinstance(required, list) else [])
        defaults: dict[str, Any] = {}
        for field_name, field_schema in properties.items():
            if not isinstance(field_name, str):
                continue
            if field_name not in required_set:
                continue
            if not isinstance(field_schema, dict):
                defaults[field_name] = ""
                continue
            if "default" in field_schema:
                defaults[field_name] = field_schema["default"]
                continue
            field_type = str(field_schema.get("type", "string") or "string")
            if field_type == "number" or field_type == "integer":
                defaults[field_name] = 0
            elif field_type == "boolean":
                defaults[field_name] = False
            elif field_type == "array":
                defaults[field_name] = []
            elif field_type == "object":
                defaults[field_name] = {}
            else:
                defaults[field_name] = ""
        return defaults

    @staticmethod
    def _to_pretty_json(payload: Any) -> str:
        try:
            return json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        except Exception:
            return str(payload)
