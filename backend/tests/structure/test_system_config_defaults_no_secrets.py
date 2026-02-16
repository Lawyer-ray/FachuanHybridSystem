import re

from apps.core.services.system_config_admin_service import SystemConfigAdminService


def test_system_config_defaults_do_not_embed_secret_values():
    defaults = SystemConfigAdminService().get_default_configs()

    violations: list[str] = []
    for item in defaults:
        key = str(item.get("key") or "")
        is_secret = bool(item.get("is_secret", False))
        value = item.get("value", None)

        if is_secret and value not in (None, ""):
            violations.append(f"{key} has default value")

        if re.search(r"(API_KEY|APP_SECRET|SECRET|TOKEN|PASSWORD)$", key) and value not in (None, ""):
            violations.append(f"{key} should not ship with default value")

    assert not violations, "Default SystemConfig contains embedded secrets:\n" + "\n".join(sorted(violations))
