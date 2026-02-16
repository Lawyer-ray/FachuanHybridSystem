#!/usr/bin/env python3
"""修复配置参数的类型问题"""
import re
from pathlib import Path


def fix_config_params(file_path: Path) -> bool:
    """修复配置参数，确保非None"""
    content = file_path.read_text(encoding='utf-8')
    original = content
    
    # 修复SteeringPerformanceConfig参数
    patterns = [
        (r'enable_monitoring=self\.config_manager\.get\("([^"]+)", ([^)]+)\)',
         r'enable_monitoring=self.config_manager.get("\1", \2) or \2'),
        (r'log_slow_loads=self\.config_manager\.get\("([^"]+)", ([^)]+)\)',
         r'log_slow_loads=self.config_manager.get("\1", \2) or \2'),
        (r'slow_load_threshold_ms=self\.config_manager\.get\("([^"]+)", ([^)]+)\)',
         r'slow_load_threshold_ms=self.config_manager.get("\1", \2) or \2'),
        (r'track_memory_usage=self\.config_manager\.get\("([^"]+)", ([^)]+)\)',
         r'track_memory_usage=self.config_manager.get("\1", \2) or \2'),
        (r'memory_warning_threshold_mb=self\.config_manager\.get\("([^"]+)", ([^)]+)\)',
         r'memory_warning_threshold_mb=self.config_manager.get("\1", \2) or \2'),
        (r'collect_statistics=self\.config_manager\.get\("([^"]+)", ([^)]+)\)',
         r'collect_statistics=self.config_manager.get("\1", \2) or \2'),
        (r'auto_resolve=self\.config_manager\.get\("([^"]+)", ([^)]+)\)',
         r'auto_resolve=self.config_manager.get("\1", \2) or \2'),
        (r'max_depth=self\.config_manager\.get\("([^"]+)", ([^)]+)\)',
         r'max_depth=self.config_manager.get("\1", \2) or \2'),
        (r'circular_dependency_action=self\.config_manager\.get\("([^"]+)", ([^)]+)\)',
         r'circular_dependency_action=self.config_manager.get("\1", \2) or \2'),
        (r'load_order_strategy=self\.config_manager\.get\("([^"]+)", ([^)]+)\)',
         r'load_order_strategy=self.config_manager.get("\1", \2) or \2'),
    ]
    
    for pattern, replacement in patterns:
        content = re.sub(pattern, replacement, content)
    
    if content != original:
        file_path.write_text(content, encoding='utf-8')
        print(f"✓ {file_path.name}")
        return True
    return False


def main() -> None:
    """主函数"""
    base = Path("apps/core/config")
    files = [
        base / "steering_integration.py",
        base / "steering/integration_provider.py",
    ]
    
    fixed = 0
    for file_path in files:
        if file_path.exists():
            if fix_config_params(file_path):
                fixed += 1
    
    print(f"\n✓ 修复了 {fixed} 个文件")


if __name__ == "__main__":
    main()
