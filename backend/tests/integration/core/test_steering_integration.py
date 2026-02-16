"""
Steering 集成测试

简单测试 Steering 系统集成功能
"""

import os
import tempfile

from apps.core.config.manager import ConfigManager
from apps.core.config.providers.yaml import YamlProvider


def test_steering_integration():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        config_content = """
steering:
  conditional_loading:
    enabled: true
    rules:
      - pattern: "core/*.md"
        condition: "always"
        priority: 100

  cache:
    enabled: true
    strategy: "smart"
    ttl_seconds: 3600

  performance:
    enabled: true
    thresholds:
      load_time_warning_ms: 500.0

  dependencies:
    auto_resolve: true
    load_order_strategy: "dependency"
"""
        f.write(config_content)
        config_file = f.name

    try:
        config_manager = ConfigManager()

        yaml_provider = YamlProvider(config_file)
        config_manager.add_provider(yaml_provider)

        config_manager.load()
        config_manager.enable_steering_integration()

        integration = config_manager.get_steering_integration()

        if integration:
            cache_enabled = config_manager.get("steering.cache.enabled", False)
            assert cache_enabled is True

            specs = config_manager.load_steering_specifications("backend/apps/client/api/client_api.py")
            assert isinstance(specs, list)

            stats = integration.get_integration_stats()
            assert isinstance(stats, dict)

        else:
            raise AssertionError("Steering 集成初始化失败")

    finally:
        if os.path.exists(config_file):
            os.unlink(config_file)
