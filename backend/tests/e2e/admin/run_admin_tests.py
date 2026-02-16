"""
Admin 测试运行器

运行所有 Admin 稳定性测试

用法:
    python run_admin_tests.py                    # 运行所有测试
    python run_admin_tests.py --suite smoke      # 只运行冒烟测试
    python run_admin_tests.py --suite crud       # 只运行 CRUD 测试
    python run_admin_tests.py --help             # 显示帮助
"""
import asyncio
import sys
import argparse
from datetime import datetime
from .test_smoke import TestAdminSmoke
from .test_case_admin import TestCaseAdmin


async def run_test_class(test_class, test_name: str):
    """运行单个测试类"""
    print(f"\n{'='*70}")
    print(f"📋 {test_name}")
    print(f"{'='*70}\n")
    
    test = test_class()
    results = {
        'passed': 0,
        'failed': 0,
        'skipped': 0,
        'errors': []
    }
    
    try:
        # 设置测试环境
        await test.setup()
        
        # 获取所有测试方法
        test_methods = [
            method for method in dir(test)
            if method.startswith('test_') and callable(getattr(test, method))
        ]
        
        print(f"发现 {len(test_methods)} 个测试用例\n")
        
        # 运行每个测试方法
        for i, method_name in enumerate(test_methods, 1):
            method_display = method_name.replace('test_', '').replace('_', ' ').title()
            print(f"[{i}/{len(test_methods)}] {method_display}...", end=' ')
            
            try:
                method = getattr(test, method_name)
                await method()
                print("✅ PASSED")
                results['passed'] += 1
            except AssertionError as e:
                print(f"❌ FAILED")
                print(f"      原因: {e}")
                results['failed'] += 1
                results['errors'].append({
                    'test': f"{test_class.__name__}.{method_name}",
                    'type': 'AssertionError',
                    'error': str(e)
                })
            except Exception as e:
                error_msg = str(e)
                if '跳过' in error_msg or 'skip' in error_msg.lower():
                    print(f"⏭️  SKIPPED")
                    print(f"      原因: {e}")
                    results['skipped'] += 1
                else:
                    print(f"💥 ERROR")
                    print(f"      原因: {e}")
                    results['failed'] += 1
                    results['errors'].append({
                        'test': f"{test_class.__name__}.{method_name}",
                        'type': type(e).__name__,
                        'error': str(e)
                    })
        
    finally:
        # 清理测试环境
        try:
            await test.teardown()
        except:
            pass
    
    return results


async def run_all_tests():
    """运行所有测试"""
    print(f"\n{'='*70}")
    print(f"🚀 Django Admin 稳定性测试")
    print(f"{'='*70}")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")
    
    # 定义测试套件
    test_suites = [
        (TestAdminSmoke, "冒烟测试 - 页面访问"),
        (TestCaseAdmin, "案件管理 - 功能测试"),
        # 可以添加更多测试类
        # (TestContractAdmin, "合同管理 - 功能测试"),
        # (TestPreservationQuoteAdmin, "财产保全询价 - 功能测试"),
    ]
    
    # 运行所有测试套件
    all_results = {
        'passed': 0,
        'failed': 0,
        'skipped': 0,
        'errors': [],
        'suites': []
    }
    
    for test_class, test_name in test_suites:
        try:
            results = await run_test_class(test_class, test_name)
            all_results['passed'] += results['passed']
            all_results['failed'] += results['failed']
            all_results['skipped'] += results['skipped']
            all_results['errors'].extend(results['errors'])
            all_results['suites'].append({
                'name': test_name,
                'results': results
            })
        except Exception as e:
            print(f"\n❌ 测试套件 '{test_name}' 执行失败: {e}\n")
            all_results['failed'] += 1
            all_results['errors'].append({
                'test': test_name,
                'type': 'SuiteError',
                'error': str(e)
            })
    
    # 打印总结
    print(f"\n{'='*70}")
    print(f"📊 测试总结")
    print(f"{'='*70}\n")
    
    total = all_results['passed'] + all_results['failed'] + all_results['skipped']
    
    print(f"总计测试: {total}")
    print(f"  ✅ 通过: {all_results['passed']}")
    print(f"  ❌ 失败: {all_results['failed']}")
    print(f"  ⏭️  跳过: {all_results['skipped']}")
    
    if all_results['passed'] > 0:
        success_rate = (all_results['passed'] / total) * 100
        print(f"\n成功率: {success_rate:.1f}%")
    
    # 打印每个测试套件的结果
    if len(all_results['suites']) > 1:
        print(f"\n{'='*70}")
        print(f"各测试套件结果:")
        print(f"{'='*70}\n")
        
        for suite in all_results['suites']:
            name = suite['name']
            results = suite['results']
            suite_total = results['passed'] + results['failed'] + results['skipped']
            
            print(f"{name}:")
            print(f"  总计: {suite_total}")
            print(f"  ✅ 通过: {results['passed']}")
            print(f"  ❌ 失败: {results['failed']}")
            print(f"  ⏭️  跳过: {results['skipped']}")
            
            if results['passed'] > 0 and suite_total > 0:
                suite_rate = (results['passed'] / suite_total) * 100
                print(f"  成功率: {suite_rate:.1f}%")
            print()
    
    # 打印失败的测试
    if all_results['errors']:
        print(f"\n{'='*70}")
        print(f"❌ 失败的测试详情:")
        print(f"{'='*70}\n")
        
        for i, error in enumerate(all_results['errors'], 1):
            print(f"{i}. {error['test']}")
            print(f"   类型: {error['type']}")
            print(f"   错误: {error['error']}")
            print()
    
    print(f"{'='*70}")
    print(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")
    
    # 返回退出码
    return 0 if all_results['failed'] == 0 else 1


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='Django Admin 稳定性测试运行器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python run_admin_tests.py                    # 运行所有测试
  python run_admin_tests.py --suite smoke      # 只运行冒烟测试
  python run_admin_tests.py --suite crud       # 只运行 CRUD 测试
  python run_admin_tests.py --all              # 运行所有测试（同默认）
        """
    )
    
    parser.add_argument(
        '--suite',
        choices=['smoke', 'crud', 'inline', 'validation', 'action', 'performance'],
        help='运行指定的测试套件'
    )
    
    parser.add_argument(
        '--all',
        action='store_true',
        help='运行所有测试（默认）'
    )
    
    parser.add_argument(
        '--verbose',
        '-v',
        action='store_true',
        help='显示详细输出'
    )
    
    return parser.parse_args()


async def run_smoke_tests():
    """运行冒烟测试"""
    return await run_test_class(TestAdminSmoke, "冒烟测试 - 页面访问")


async def run_crud_tests():
    """运行 CRUD 测试"""
    results = {
        'passed': 0,
        'failed': 0,
        'skipped': 0,
        'errors': [],
        'suites': []
    }
    
    test_suites = [
        (TestCaseAdmin, "案件管理 - CRUD 测试"),
        # 可以添加更多 CRUD 测试
    ]
    
    for test_class, test_name in test_suites:
        suite_results = await run_test_class(test_class, test_name)
        results['passed'] += suite_results['passed']
        results['failed'] += suite_results['failed']
        results['skipped'] += suite_results['skipped']
        results['errors'].extend(suite_results['errors'])
        results['suites'].append({
            'name': test_name,
            'results': suite_results
        })
    
    return results


if __name__ == '__main__':
    args = parse_args()
    
    # 根据参数选择运行的测试
    if args.suite == 'smoke':
        print("\n🔍 运行冒烟测试...")
        exit_code = asyncio.run(run_smoke_tests())
        sys.exit(0 if exit_code['failed'] == 0 else 1)
    elif args.suite == 'crud':
        print("\n📝 运行 CRUD 测试...")
        results = asyncio.run(run_crud_tests())
        sys.exit(0 if results['failed'] == 0 else 1)
    else:
        # 默认运行所有测试
        exit_code = asyncio.run(run_all_tests())
        sys.exit(exit_code)
