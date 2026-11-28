"""Business logic services."""

import importlib
import logging

from django.apps import apps as django_apps

logger = logging.getLogger(__name__)


def autodiscover_code_placeholders() -> list[str]:
    imported: list[str] = []

    # 按应用名排序后枚举,保证各应用占位符包的注册顺序确定
    for app_config in sorted(django_apps.get_app_configs(), key=lambda config: config.name):
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
            logger.exception("autodiscover.autodiscover_code_placeholders: 扫描子包导入失败（非缺包）")

            continue
        except Exception:
            logger.exception("autodiscover.autodiscover_code_placeholders: 扫描子包导入异常")

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
        logger.exception("autodiscover.autodiscover_code_placeholders: 回退导入 placeholders 失败（非缺包）")

        return imported
    except Exception:
        logger.exception("autodiscover.autodiscover_code_placeholders: 回退导入 placeholders 异常")

        pass

    return imported
