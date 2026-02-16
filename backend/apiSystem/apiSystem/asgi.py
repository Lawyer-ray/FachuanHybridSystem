"""
ASGI config for apiSystem project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import logging
import os
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent.parent
_project_root_str = str(_project_root)
if _project_root_str not in sys.path:
    sys.path.insert(0, _project_root_str)

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")

# Initialize Django ASGI application early to ensure the AppRegistry
# is populated before importing code that may import ORM models.
django_asgi_app = get_asgi_application()

try:
    from apps.core.llm.warmup import warm_llm_system_config_cache

    _strict = (os.environ.get("DJANGO_LLM_WARMUP_STRICT", "") or "").lower().strip() in ("true", "1", "yes")
    warm_llm_system_config_cache(strict=_strict)
except Exception:
    logging.getLogger("apps.core").exception("llm_warmup_bootstrap_failed")
    if (os.environ.get("DJANGO_LLM_WARMUP_STRICT", "") or "").lower().strip() in ("true", "1", "yes"):
        raise

from apps.core.asgi_lifespan import LifespanApp
from apps.core.httpx_clients import aclose_http_clients

# Import routing after Django is initialized
from apps.litigation_ai.routing import websocket_urlpatterns

application = ProtocolTypeRouter(
    {
        "lifespan": LifespanApp(on_shutdown=aclose_http_clients),
        "http": django_asgi_app,
        "websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
    }
)
