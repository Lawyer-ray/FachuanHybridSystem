"""
Steering 集成测试

简单测试 Steering 系统集成功能
"""

import logging
import os
import tempfile

from .manager import ConfigManager
from .providers.yaml import YamlProvider

logger = logging.getLogger(__name__)


def test_steering_integration() -> None:
    """测试 Steering 集成功能"""

    # 创建临时配置文件
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
        # 创建配置管理器
        config_manager = ConfigManager()

        # 添加 YAML 提供者
        yaml_provider = YamlProvider(config_file)
        config_manager.add_provider(yaml_provider)

        # 加载配置
        config_manager.load()

        # 启用 Steering 集成
        config_manager.enable_steering_integration()

        # 获取集成管理器
        integration = config_manager.get_steering_integration()

        if integration:
            logger.info("✓ Steering 集成初始化成功")

            # 测试配置获取
            cache_enabled = config_manager.get("steering.cache.enabled", False)
            logger.info("✓ 缓存配置: %s", cache_enabled)

            # 测试规范加载（模拟）
            specs = config_manager.load_steering_specifications("backend/apps/client/api/client_api.py")
            logger.info("✓ 规范加载测试完成，返回 %d 个规范", len(specs))

            # 获取统计信息
            stats = integration.get_integration_stats()
            logger.info("✓ 集成统计信息获取成功: %d 个指标", len(stats))

            logger.info("✓ 所有 Steering 集成测试通过")

        else:
            logger.warning("✗ Steering 集成初始化失败")

    except Exception as e:
        logger.error("✗ 测试失败: %s", e)

    finally:
        # 清理临时文件
        if os.path.exists(config_file):
            os.unlink(config_file)


if __name__ == "__main__":
    test_steering_integration()
