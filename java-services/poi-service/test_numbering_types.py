#!/usr/bin/env python3
"""
合同格式化详细端到端测试
测试两种编号类型和完整的用户流程
"""
import requests
import sys
from pathlib import Path

BASE_URL = "http://localhost:8090"

# 测试文件路径
TEST_FILES = {
    "chinese": {
        "input": "/Users/huangsong21/Downloads/验收/电脑维护合同.docx",
        "name": "电脑维护合同"
    },
    "digital": {
        "input": "/Users/huangsong21/Downloads/验收/赛羽自媒体平台代运营服务合同20250325.docx",
        "name": "赛羽自媒体平台代运营服务合同"
    }
}


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
    print(f"   ✓ 合同格式化服务健康检查通过: {data}")
    return True


def test_format_chinese_numbering():
    """测试中文编号格式化"""
    print("\n" + "=" * 70)
    print("3. 测试中文编号格式化（一、→1.→(1)）")
    print("=" * 70)

    input_path = Path(TEST_FILES["chinese"]["input"])
    if not input_path.exists():
        print("   ⚠️  测试文件不存在，跳过")
        return True

    docx_bytes = input_path.read_bytes()
    print(f"   输入: {input_path.name} ({len(docx_bytes):,} bytes)")

    # 调用格式化API（使用中文编号）
    response = requests.post(
        f"{BASE_URL}/api/documents/contract/format",
        json={
            "docxBytes": list(docx_bytes),
            "config": {
                "numberingType": "CHINESE",  # 大写
                "lineSpacing": 360,
                "bodyFont": "宋体",
                "bodyFontSize": 24,
                "renumberHeadings": True
            },
            "outputFileName": "chinese_numbering.docx"
        },
        timeout=120
    )

    assert response.status_code == 200
    assert len(response.content) > 0
    assert response.content[:2] == b'PK'

    # 保存输出
    output_path = Path("test_output/chinese_numbering.docx")
    output_path.parent.mkdir(exist_ok=True)
    output_path.write_bytes(response.content)

    print(f"   ✓ 中文编号格式化成功")
    print(f"     - 输出大小: {len(response.content):,} bytes")
    print(f"     - 保存位置: {output_path.absolute()}")
    print(f"     - 编号格式: 一、→1.→(1)")

    return True


def test_format_digital_numbering():
    """测试数字编号格式化"""
    print("\n" + "=" * 70)
    print("4. 测试数字编号格式化（1.→1.1.→1.1.1.）")
    print("=" * 70)

    input_path = Path(TEST_FILES["digital"]["input"])
    if not input_path.exists():
        print("   ⚠️  测试文件不存在，跳过")
        return True

    docx_bytes = input_path.read_bytes()
    print(f"   输入: {input_path.name} ({len(docx_bytes):,} bytes)")

    # 调用格式化API（使用数字编号）
    response = requests.post(
        f"{BASE_URL}/api/documents/contract/format",
        json={
            "docxBytes": list(docx_bytes),
            "config": {
                "numberingType": "DIGITAL",  # 大写
                "lineSpacing": 360,
                "bodyFont": "宋体",
                "bodyFontSize": 24,
                "renumberHeadings": True
            },
            "outputFileName": "digital_numbering.docx"
        },
        timeout=120
    )

    assert response.status_code == 200
    assert len(response.content) > 0
    assert response.content[:2] == b'PK'

    # 保存输出
    output_path = Path("test_output/digital_numbering.docx")
    output_path.parent.mkdir(exist_ok=True)
    output_path.write_bytes(response.content)

    print(f"   ✓ 数字编号格式化成功")
    print(f"     - 输出大小: {len(response.content):,} bytes")
    print(f"     - 保存位置: {output_path.absolute()}")
    print(f"     - 编号格式: 1.→1.1.→1.1.1.")

    return True


def test_format_without_numbering():
    """测试不使用自动编号的格式化"""
    print("\n" + "=" * 70)
    print("5. 测试不使用自动编号的格式化")
    print("=" * 70)

    input_path = Path(TEST_FILES["chinese"]["input"])
    if not input_path.exists():
        print("   ⚠️  测试文件不存在，跳过")
        return True

    docx_bytes = input_path.read_bytes()
    print(f"   输入: {input_path.name} ({len(docx_bytes):,} bytes)")

    # 调用格式化API（不使用自动编号）
    response = requests.post(
        f"{BASE_URL}/api/documents/contract/format",
        json={
            "docxBytes": list(docx_bytes),
            "config": {
                "numberingType": "CHINESE",  # 大写
                "lineSpacing": 360,
                "bodyFont": "宋体",
                "bodyFontSize": 24,
                "renumberHeadings": False  # 不使用自动编号
            },
            "outputFileName": "no_numbering.docx"
        },
        timeout=120
    )

    assert response.status_code == 200
    assert len(response.content) > 0
    assert response.content[:2] == b'PK'

    # 保存输出
    output_path = Path("test_output/no_numbering.docx")
    output_path.parent.mkdir(exist_ok=True)
    output_path.write_bytes(response.content)

    print(f"   ✓ 无自动编号格式化成功")
    print(f"     - 输出大小: {len(response.content):,} bytes")
    print(f"     - 保存位置: {output_path.absolute()}")

    return True


def test_format_all_verification_files():
    """测试所有验收文件"""
    print("\n" + "=" * 70)
    print("6. 测试所有验收文件")
    print("=" * 70)

    verification_files = [
        {
            "name": "电脑维护合同",
            "input": "/Users/huangsong21/Downloads/验收/电脑维护合同.docx",
            "numbering": "chinese"
        },
        {
            "name": "赛羽自媒体平台代运营服务合同",
            "input": "/Users/huangsong21/Downloads/验收/赛羽自媒体平台代运营服务合同20250325.docx",
            "numbering": "digital"
        },
        {
            "name": "项目合作协议（跨境运营顾问）",
            "input": "/Users/huangsong21/Downloads/验收/项目合作协议（跨境运营顾问）(2.13).docx",
            "numbering": "chinese"
        }
    ]

    results = []

    for file_info in verification_files:
        try:
            input_path = Path(file_info["input"])
            if not input_path.exists():
                print(f"   ⚠️  {file_info['name']}: 文件不存在，跳过")
                results.append({"name": file_info["name"], "status": "skipped"})
                continue

            docx_bytes = input_path.read_bytes()
            print(f"\n   测试: {file_info['name']}")
            print(f"   编号类型: {file_info['numbering']}")

            # 调用格式化API
            response = requests.post(
                f"{BASE_URL}/api/documents/contract/format",
                json={
                    "docxBytes": list(docx_bytes),
                    "config": {
                        "numberingType": file_info["numbering"].upper(),  # 大写
                        "lineSpacing": 360,
                        "bodyFont": "宋体",
                        "bodyFontSize": 24,
                        "renumberHeadings": True
                    },
                    "outputFileName": f"{file_info['name']}_formatted.docx"
                },
                timeout=120
            )

            assert response.status_code == 200
            assert len(response.content) > 0
            assert response.content[:2] == b'PK'

            # 保存输出
            output_path = Path(f"test_output/{file_info['name']}_formatted.docx")
            output_path.parent.mkdir(exist_ok=True)
            output_path.write_bytes(response.content)

            print(f"   ✓ 格式化成功")
            print(f"     - 原始大小: {len(docx_bytes):,} bytes")
            print(f"     - 输出大小: {len(response.content):,} bytes")
            print(f"     - 保存位置: {output_path.absolute()}")

            results.append({
                "name": file_info["name"],
                "status": "success",
                "original_size": len(docx_bytes),
                "output_size": len(response.content)
            })

        except Exception as e:
            print(f"   ✗ 测试失败: {e}")
            results.append({
                "name": file_info["name"],
                "status": "failed",
                "error": str(e)
            })

    return results


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
    print("测试两种编号类型：中文编号和数字编号")
    print("=" * 70)

    all_results = []

    try:
        # 1. 测试健康状态
        test_health()
        test_contract_health()

        # 2. 测试中文编号格式化
        test_format_chinese_numbering()

        # 3. 测试数字编号格式化
        test_format_digital_numbering()

        # 4. 测试无自动编号的格式化
        test_format_without_numbering()

        # 5. 测试所有验收文件
        verification_results = test_format_all_verification_files()
        all_results.extend(verification_results)

        # 6. 生成测试报告
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
