#!/usr/bin/env python3
"""
合同格式化端到端测试
"""
import requests
import sys
from pathlib import Path

BASE_URL = "http://localhost:8090"

def test_health():
    """测试健康检查端点"""
    print("1. 测试健康检查端点...")
    response = requests.get(f"{BASE_URL}/api/documents/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    print(f"   ✓ 健康检查通过: {data}")
    return True

def test_contract_health():
    """测试合同格式化服务健康检查"""
    print("\n2. 测试合同格式化服务健康检查...")
    response = requests.get(f"{BASE_URL}/api/documents/contract/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    print(f"   ✓ 合同格式化服务健康检查通过: {data}")
    return True

def test_format_contract():
    """测试合同格式化"""
    print("\n3. 测试合同格式化...")

    # 读取测试文件（使用验收文件）
    test_file = Path("/Users/huangsong21/Downloads/验收/电脑维护合同.docx")
    if not test_file.exists():
        print("   ⚠️  测试文件不存在，跳过")
        return True

    docx_bytes = test_file.read_bytes()

    # 调用格式化API
    response = requests.post(
        f"{BASE_URL}/api/documents/contract/format",
        json={
            "docxBytes": list(docx_bytes),
            "outputFileName": "test_formatted.docx"
        },
        timeout=60
    )

    assert response.status_code == 200
    assert len(response.content) > 0
    assert response.content[:2] == b'PK'  # DOCX文件头

    # 保存输出
    output_path = Path("test_output/电脑维护合同_formatted.docx")
    output_path.parent.mkdir(exist_ok=True)
    output_path.write_bytes(response.content)

    print(f"   ✓ 合同格式化成功")
    print(f"     - 原始大小: {len(docx_bytes)} bytes")
    print(f"     - 输出大小: {len(response.content)} bytes")
    print(f"     - 保存位置: {output_path.absolute()}")

    return True

def test_format_with_config():
    """测试带配置的合同格式化"""
    print("\n4. 测试带配置的合同格式化...")

    # 读取测试文件
    test_file = Path("/Users/huangsong21/Downloads/验收/电脑维护合同.docx")
    if not test_file.exists():
        print("   ⚠️  测试文件不存在，跳过")
        return True

    docx_bytes = test_file.read_bytes()

    # 调用格式化API（带自定义配置）
    response = requests.post(
        f"{BASE_URL}/api/documents/contract/format",
        json={
            "docxBytes": list(docx_bytes),
            "config": {
                "lineSpacing": 360,
                "bodyFont": "宋体",
                "bodyFontSize": 24,
                "headingL1Font": "黑体",
                "headingL1FontSize": 36
            },
            "outputFileName": "test_formatted_config.docx"
        },
        timeout=60
    )

    assert response.status_code == 200
    assert len(response.content) > 0
    assert response.content[:2] == b'PK'

    print(f"   ✓ 带配置的合同格式化成功")
    print(f"     - 输出大小: {len(response.content)} bytes")

    return True

def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("合同格式化 E2E 测试")
    print("=" * 60)

    tests = [
        test_health,
        test_contract_health,
        test_format_contract,
        test_format_with_config,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except AssertionError as e:
            print(f"   ✗ 测试失败: {e}")
            failed += 1
        except Exception as e:
            print(f"   ✗ 测试异常: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)

    return failed == 0

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
