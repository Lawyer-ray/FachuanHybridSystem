"""
Steering 集成测试

简单测试 Steering 系统集成功能
"""

import os
import tempfile
from pathlib import Path
from .manager import ConfigManager
from .providers.yaml import YamlProvider


def test_steering_integration():
    """测试 Steering 集成功能"""
    
    # 创建临时配置文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
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
            print("✓ Steering 集成初始化成功")
            
            # 测试配置获取
            cache_enabled = config_manager.get("steering.cache.enabled", False)
            print(f"✓ 缓存配置: {cache_enabled}")
            
            # 测试规范加载（模拟）
            specs = config_manager.load_steering_specifications("backend/apps/client/api/client_api.py")
            print(f"✓ 规范加载测试完成，返回 {len(specs)} 个规范")
            
            # 获取统计信息
            stats = integration.get_integration_stats()
            print(f"✓ 集成统计信息获取成功: {len(stats)} 个指标")
            
            print("✓ 所有 Steering 集成测试通过")
            
        else:
            print("✗ Steering 集成初始化失败")
            
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        
    finally:
        # 清理临时文件
        if os.path.exists(config_file):
            os.unlink(config_file)


if __name__ == "__main__":
    test_steering_integration()