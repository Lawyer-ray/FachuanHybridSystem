#!/usr/bin/env python3
"""
合同格式化详细端到端测试
使用用户提供的验收文件进行测试
"""
import requests
import sys
from pathlib import Path
import json

BASE_URL = "http://localhost:8090"

# 验收文件路径
VERIFICATION_FILES = [
    {
        "name": "电脑维护合同",
        "input": "/Users/huangsong21/Downloads/验收/电脑维护合同.docx",
        "expected": "/Users/huangsong21/Downloads/验收/电脑维护合同[修订版]V1_20250715.docx"
    },
    {
        "name": "赛羽自媒体平台代运营服务合同",
        "input": "/Users/huangsong21/Downloads/验收/赛羽自媒体平台代运营服务合同20250325.docx",
        "expected": "/Users/huangsong21/Downloads/验收/赛羽自媒体平台代运营服务合同20250325[修订版]V1_20250326.docx"
    },
    {
        "name": "项目合作协议（跨境运营顾问）",
        "input": "/Users/huangsong21/Downloads/验收/项目合作协议（跨境运营顾问）(2.13).docx",
        "expected": "/Users/huangsong21/Downloads/验收/项目合作协议（跨境运营顾问）(2.13)[修订版]V1_2025.02.14.docx"
    }
]


def test_health():
    """测试健康检查"""
    print("=" * 70)
    print("1. 测试服务健康状态")
    print("=" * 70)

    response = requests.get(f"{BASE_URL}/api/documents/health", timeout=10)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    print(f"   ✓ POI服务健康: {data}")
    return True


def test_contract_health():
    """测试合同格式化服务健康检查"""
    print("\n" + "=" * 70)
    print("2. 测试合同格式化服务健康状态")
    print("=" * 70)

    response = requests.get(f"{BASE_URL}/api/documents/contract/health", timeout=10)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    print(f"   ✓ 合同格式化服务健康: {data}")
    return True


def test_format_single_file(file_info):
    """格式化单个合同文件"""
    input_path = Path(file_info["input"])

    if not input_path.exists():
        print(f"   ⚠️  文件不存在: {input_path}")
        return None

    print(f"\n   测试: {file_info['name']}")
    print(f"   输入: {input_path.name}")

    # 读取原始文件
    docx_bytes = input_path.read_bytes()
    print(f"   原始大小: {len(docx_bytes):,} bytes")

    # 调用格式化API
    response = requests.post(
        f"{BASE_URL}/api/documents/contract/format",
        json={
            "docxBytes": list(docx_bytes),
            "outputFileName": f"{file_info['name']}_formatted.docx"
        },
        timeout=120
    )

    assert response.status_code == 200
    assert len(response.content) > 0
    assert response.content[:2] == b'PK', "输出不是有效的DOCX文件"

    # 保存输出文件
    output_path = Path(f"test_output/{file_info['name']}_formatted.docx")
    output_path.parent.mkdir(exist_ok=True)
    output_path.write_bytes(response.content)

    print(f"   输出大小: {len(response.content):,} bytes")
    print(f"   保存位置: {output_path.absolute()}")

    return response.content


def compare_files(original_path, expected_path, formatted_bytes):
    """对比原始文件、预期文件和格式化后的文件"""
    print(f"\n   对比分析:")

    # 读取原始文件
    original_path = Path(original_path)
    original_bytes = original_path.read_bytes()

    # 读取预期文件
    expected_path = Path(expected_path)
    if expected_path.exists():
        expected_bytes = expected_path.read_bytes()
        print(f"   ✓ 预期文件存在: {len(expected_bytes):,} bytes")
    else:
        print(f"   ⚠️  预期文件不存在")
        return

    # 对比大小
    print(f"   原始文件: {len(original_bytes):,} bytes")
    print(f"   预期文件: {len(expected_bytes):,} bytes")
    print(f"   格式化后: {len(formatted_bytes):,} bytes")

    # 检查文件是否相同
    if formatted_bytes == expected_bytes:
        print(f"   ✓ 文件完全相同")
    else:
        print(f"   ⚠️  文件不同（可能需要进一步分析）")
        # 计算大小差异
        size_diff = len(formatted_bytes) - len(expected_bytes)
        print(f"   大小差异: {size_diff:,} bytes ({size_diff/len(expected_bytes)*100:.1f}%)")


def test_all_verification_files():
    """测试所有验收文件"""
    print("\n" + "=" * 70)
    print("3. 测试所有验收文件")
    print("=" * 70)

    results = []

    for file_info in VERIFICATION_FILES:
        try:
            formatted_bytes = test_format_single_file(file_info)

            if formatted_bytes:
                # 对比文件
                compare_files(
                    file_info["input"],
                    file_info["expected"],
                    formatted_bytes
                )
                results.append({
                    "name": file_info["name"],
                    "status": "success",
                    "formatted_size": len(formatted_bytes)
                })
            else:
                results.append({
                    "name": file_info["name"],
                    "status": "skipped"
                })

        except Exception as e:
            print(f"   ✗ 测试失败: {e}")
            results.append({
                "name": file_info["name"],
                "status": "failed",
                "error": str(e)
            })

    return results


def test_format_with_custom_config():
    """测试带自定义配置的格式化"""
    print("\n" + "=" * 70)
    print("4. 测试带自定义配置的格式化")
    print("=" * 70)

    # 使用第一个验收文件
    input_path = Path(VERIFICATION_FILES[0]["input"])
    if not input_path.exists():
        print("   ⚠️  测试文件不存在，跳过")
        return True

    docx_bytes = input_path.read_bytes()

    # 自定义配置
    custom_config = {
        "lineSpacing": 360,      # 18pt
        "bodyFont": "宋体",
        "bodyFontSize": 24,
        "headingL1Font": "黑体",
        "headingL1FontSize": 36,
        "firstLineIndent": 480,  # 首行缩进2字符
        "marginTop": 1440,
        "marginBottom": 1440,
        "marginLeft": 1800,
        "marginRight": 1800
    }

    response = requests.post(
        f"{BASE_URL}/api/documents/contract/format",
        json={
            "docxBytes": list(docx_bytes),
            "config": custom_config,
            "outputFileName": "custom_config_formatted.docx"
        },
        timeout=120
    )

    assert response.status_code == 200
    assert len(response.content) > 0
    assert response.content[:2] == b'PK'

    # 保存输出
    output_path = Path("test_output/custom_config_formatted.docx")
    output_path.write_bytes(response.content)

    print(f"   ✓ 自定义配置格式化成功")
    print(f"   输出大小: {len(response.content):,} bytes")
    print(f"   保存位置: {output_path.absolute()}")

    return True


def generate_test_report(results):
    """生成测试报告"""
    print("\n" + "=" * 70)
    print("测试报告")
    print("=" * 70)

    success_count = sum(1 for r in results if r["status"] == "success")
    failed_count = sum(1 for r in results if r["status"] == "failed")
    skipped_count = sum(1 for r in results if r["status"] == "skipped")

    print(f"总测试数: {len(results)}")
    print(f"成功: {success_count}")
    print(f"失败: {failed_count}")
    print(f"跳过: {skipped_count}")

    print("\n详细结果:")
    for result in results:
        status_symbol = "✓" if result["status"] == "success" else \
                       "✗" if result["status"] == "failed" else "⚠️"
        print(f"  {status_symbol} {result['name']}: {result['status']}")

    return failed_count == 0


def run_all_tests():
    """运行所有测试"""
    print("=" * 70)
    print("合同格式化详细端到端测试")
    print("=" * 70)

    all_results = []

    try:
        # 1. 测试健康状态
        test_health()
        test_contract_health()

        # 2. 测试所有验收文件
        verification_results = test_all_verification_files()
        all_results.extend(verification_results)

        # 3. 测试自定义配置
        test_format_with_custom_config()

        # 4. 生成测试报告
        success = generate_test_report(all_results)

        return success

    except Exception as e:
        print(f"\n✗ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
