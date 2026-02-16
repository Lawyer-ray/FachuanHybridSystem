"""
WSGI config for apiSystem project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent.parent
_project_root_str = str(_project_root)
if _project_root_str not in sys.path:
    sys.path.insert(0, _project_root_str)

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")

application = get_wsgi_application()

try:
    from apps.core.llm.warmup import warm_llm_system_config_cache

    _strict = (os.environ.get("DJANGO_LLM_WARMUP_STRICT", "") or "").lower().strip() in ("true", "1", "yes")
    warm_llm_system_config_cache(strict=_strict)
except Exception:
    import logging

    logging.getLogger("apps.core").exception("llm_warmup_bootstrap_failed")
    if (os.environ.get("DJANGO_LLM_WARMUP_STRICT", "") or "").lower().strip() in ("true", "1", "yes"):
        raise
