#!/usr/bin/env python3
"""
扫描 automation 模块剩余子模块的类型错误（详细版本）
只统计每个子模块内部文件的错误，不包括依赖错误
"""
import subprocess
from pathlib import Path
import re


def run_mypy_on_path(path: Path) -> tuple[int, dict[str, int], str]:
    """对指定路径运行 mypy 并返回错误数、文件错误分布和输出"""
    result = subprocess.run(
        ['mypy', str(path), '--strict'],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent
    )
    
    # 统计每个文件的错误数
    file_errors = {}
    lines = result.stdout.strip().split('\n')
    
    for line in lines:
        # 匹配错误行格式: "path/to/file.py:123: error: ..."
        match = re.match(r'^(.+\.py):(\d+): error:', line)
        if match:
            file_path = match.group(1)
            # 只统计当前路径下的文件
            if str(path) in file_path or file_path.startswith('apps/automation'):
                file_errors[file_path] = file_errors.get(file_path, 0) + 1
    
    total_errors = sum(file_errors.values())
    
    return total_errors, file_errors, result.stdout


def main():
    backend_path = Path(__file__).parent.parent
    automation_path = backend_path / 'apps' / 'automation'
    
    # 定义所有需要扫描的子模块（只扫描目录，不扫描单个文件）
    submodules = {
        # services 子模块（排除已修复的 document_delivery, sms, scraper）
        'services/admin': automation_path / 'services' / 'admin',
        'services/ai': automation_path / 'services' / 'ai',
        'services/captcha': automation_path / 'services' / 'captcha',
        'services/chat': automation_path / 'services' / 'chat',
        'services/court_document_recognition': automation_path / 'services' / 'court_document_recognition',
        'services/document': automation_path / 'services' / 'document',
        'services/fee_notice': automation_path / 'services' / 'fee_notice',
        'services/image_rotation': automation_path / 'services' / 'image_rotation',
        'services/insurance': automation_path / 'services' / 'insurance',
        'services/litigation': automation_path / 'services' / 'litigation',
        'services/ocr': automation_path / 'services' / 'ocr',
        'services/preservation_date': automation_path / 'services' / 'preservation_date',
        'services/token': automation_path / 'services' / 'token',
        
        # 其他子模块
        'admin': automation_path / 'admin',
        'api': automation_path / 'api',
        'integrations': automation_path / 'integrations',
        'models': automation_path / 'models',
        'schemas': automation_path / 'schemas',
        'tasking': automation_path / 'tasking',
        'tasks_impl': automation_path / 'tasks_impl',
        'usecases': automation_path / 'usecases',
        'utils': automation_path / 'utils',
        'workers': automation_path / 'workers',
    }
    
    # 扫描每个子模块
    results = {}
    file_details = {}
    total_errors = 0
    
    print("=" * 80)
    print("扫描 automation 模块剩余子模块的类型错误（详细版本）")
    print("=" * 80)
    print()
    
    for name, path in sorted(submodules.items()):
        if not path.exists():
            print(f"⚠️  {name}: 路径不存在")
            continue
        
        print(f"正在扫描: {name}...", end=' ', flush=True)
        error_count, file_errors, output = run_mypy_on_path(path)
        results[name] = error_count
        file_details[name] = file_errors
        total_errors += error_count
        
        if error_count > 0:
            print(f"❌ {error_count:4d} 个错误")
        else:
            print(f"✅ {error_count:4d} 个错误")
    
    print()
    print("=" * 80)
    print(f"总计: {total_errors} 个错误")
    print("=" * 80)
    print()
    
    # 按错误数排序
    print("按错误数排序（降序）:")
    print("-" * 80)
    sorted_results = sorted(results.items(), key=lambda x: x[1], reverse=True)
    for name, count in sorted_results:
        if count > 0:
            print(f"  {name:50s}: {count:4d} 个错误")
    
    print()
    print("建议修复顺序（从小到大）:")
    print("-" * 80)
    sorted_asc = sorted(results.items(), key=lambda x: x[1])
    for name, count in sorted_asc:
        if count > 0:
            print(f"  {name:50s}: {count:4d} 个错误")
    
    # 显示每个子模块中错误最多的文件
    print()
    print("=" * 80)
    print("每个子模块中错误最多的前 3 个文件:")
    print("=" * 80)
    for name, file_errors in sorted(file_details.items(), key=lambda x: results[x[0]], reverse=True):
        if results[name] > 0:
            print(f"\n{name} ({results[name]} 个错误):")
            sorted_files = sorted(file_errors.items(), key=lambda x: x[1], reverse=True)[:3]
            for file_path, count in sorted_files:
                # 简化文件路径显示
                short_path = file_path.replace('apps/automation/', '')
                print(f"  - {short_path}: {count} 个错误")


if __name__ == '__main__':
    main()
