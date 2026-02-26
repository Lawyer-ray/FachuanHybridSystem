"""Business logic services."""

import importlib
import logging

from django.apps import apps as django_apps

logger = logging.getLogger(__name__)


def autodiscover_code_placeholders() -> list[str]:
    imported: list[str] = []

    for app_config in django_apps.get_app_configs():
        placeholders_pkg_name = app_config.name + ".placeholders"
        try:
            importlib.import_module(placeholders_pkg_name)
            imported.append(placeholders_pkg_name)
        except ModuleNotFoundError as e:
            missing = getattr(e, "name", None)
            if missing == placeholders_pkg_name or (
                isinstance(missing, str) and missing.startswith(placeholders_pkg_name + ".")
            ):
                continue
            logger.exception("操作失败")

            continue
        except Exception:
            logger.exception("操作失败")

            continue

    try:
        importlib.import_module("apps.documents.services.placeholders")
        imported.append("apps.documents.services.placeholders")
    except ModuleNotFoundError as e:
        missing = getattr(e, "name", None)
        if missing == "apps.documents.services.placeholders" or (
            isinstance(missing, str) and missing.startswith("apps.documents.services.placeholders.")
        ):
            return imported
        logger.exception("操作失败")

        return imported
    except Exception:
        logger.exception("操作失败")

        pass

    return imported
