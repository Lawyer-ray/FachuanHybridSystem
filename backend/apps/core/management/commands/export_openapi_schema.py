"""导出 api_v1 的 OpenAPI schema 为 JSON 文件，供前端 openapi-typescript 生成类型。

前端 ``src/types/api-schema.d.ts`` 由本命令的产物生成（再生成流程见该文件头部注释）：

1. ``cd backend && .venv/bin/python apiSystem/manage.py export_openapi_schema``
   （默认写 ``backend/openapi.json``，可用 ``--out`` 覆盖）
2. ``cd frontend && pnpm gen:api``

schema 生成依赖路由已注册：``apiSystem.api`` 模块导入即执行
``_ensure_routers_registered()``（含 apps/* 与 plugins 的全部 add_router），
因此导入 ``api_v1`` 后再调 ``get_openapi_schema()`` 即为全量路由。
``path_prefix`` 显式传 ``/api/v1``，与 urls.py 的挂载前缀一致，不依赖
URL 反解析（无请求上下文时 reverse 可能失败）。

用法::

    python apiSystem/manage.py export_openapi_schema
    python apiSystem/manage.py export_openapi_schema --out /tmp/openapi.json
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand

from apiSystem.api import api_v1


class Command(BaseCommand):
    help = "导出 api_v1 OpenAPI JSON（默认 backend/openapi.json），供前端 openapi-typescript 生成类型"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--out",
            type=Path,
            default=None,
            help="输出文件路径（默认 backend/openapi.json）",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        out_option: object = options.get("out")
        # settings.BASE_DIR = backend/apiSystem，其 parent 即 backend/
        # （BASE_DIR 为 settings 模块自定义属性，django-stubs 不识别，同 apps/documents/storage.py 口径）
        target = out_option if isinstance(out_option, Path) else Path(str(settings.BASE_DIR)).parent / "openapi.json"  # type: ignore[misc]

        # 尾斜杠不可省：BoundRouter.prefix 不带前导斜杠，schema 拼接为
        # "/" + path_prefix + f"{prefix}/{path}"，缺尾斜杠会把 router 路径
        # 拼成 /api/v1social/...（实时 schema 因 reverse() 自带尾斜杠而不受影响）
        schema = api_v1.get_openapi_schema(path_prefix="/api/v1/")

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(schema, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )

        path_count = len(schema.get("paths", {}))
        self.stdout.write(self.style.SUCCESS(f"OpenAPI schema 已导出：{target}（paths={path_count}）"))
