#!/usr/bin/env python3
"""
E2E测试脚本 - poi-tl模板渲染
"""
import requests
import json
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

def test_list_templates():
    """测试列出模板端点"""
    print("\n2. 测试列出模板端点...")
    response = requests.get(f"{BASE_URL}/api/documents/templates")
    assert response.status_code == 200
    data = response.json()
    assert "templates" in data
    templates = data["templates"]
    print(f"   ✓ 列出 {len(templates)} 个模板: {templates}")
    return len(templates) > 0

def test_render_complaint():
    """测试渲染民事起诉状模板"""
    print("\n3. 测试渲染民事起诉状模板...")

    payload = {
        "templateName": "complaint/civil_complaint.docx",
        "context": {
            "plaintiff": {
                "name": "张三",
                "gender": "男",
                "birthDate": "1990-01-01",
                "nationality": "汉族",
                "address": "北京市朝阳区xxx路xxx号",
                "agent": {
                    "name": "李律师",
                    "firm": "北京律师事务所"
                }
            },
            "defendant": {
                "name": "李四",
                "gender": "男",
                "birthDate": "1985-05-15",
                "nationality": "汉族",
                "address": "上海市浦东新区xxx路xxx号"
            },
            "claims": [
                "判令被告赔偿原告经济损失人民币10万元",
                "判令被告承担本案诉讼费用"
            ],
            "facts": [
                "2023年1月，原告与被告签订服务合同",
                "被告未按约定履行义务，造成原告经济损失"
            ],
            "evidence": [
                "服务合同原件",
                "付款凭证",
                "损失证明文件"
            ],
            "court": "北京市朝阳区人民法院",
            "submitDate": "2024年06月06日"
        }
    }

    response = requests.post(
        f"{BASE_URL}/api/documents/template/render",
        json=payload,
        timeout=30
    )

    assert response.status_code == 200
    assert len(response.content) > 0

    # 验证是DOCX文件（ZIP格式，以PK开头）
    assert response.content[:2] == b'PK', "不是有效的DOCX文件"

    # 保存文件
    output_path = Path("test_complaint_output.docx")
    output_path.write_bytes(response.content)

    print(f"   ✓ 民事起诉状渲染成功")
    print(f"     - 文件大小: {len(response.content)} bytes")
    print(f"     - 保存位置: {output_path.absolute()}")

    return True

def test_render_nonexistent_template():
    """测试渲染不存在的模板"""
    print("\n4. 测试渲染不存在的模板...")

    payload = {
        "templateName": "nonexistent.docx",
        "context": {"name": "test"}
    }

    response = requests.post(
        f"{BASE_URL}/api/documents/template/render",
        json=payload,
        timeout=10
    )

    assert response.status_code == 500
    data = response.json()
    assert "error" in data
    print(f"   ✓ 不存在的模板正确返回500错误: {data['error']}")
    return True

def test_render_with_empty_context():
    """测试空context渲染"""
    print("\n5. 测试空context渲染...")

    payload = {
        "templateName": "complaint/civil_complaint.docx",
        "context": {}
    }

    response = requests.post(
        f"{BASE_URL}/api/documents/template/render",
        json=payload,
        timeout=30
    )

    assert response.status_code == 200
    assert len(response.content) > 0
    assert response.content[:2] == b'PK'

    print(f"   ✓ 空context渲染成功（占位符未被替换）")
    return True

def test_render_with_null_context():
    """测试null context渲染"""
    print("\n6. 测试null context渲染...")

    payload = {
        "templateName": "complaint/civil_complaint.docx"
    }

    response = requests.post(
        f"{BASE_URL}/api/documents/template/render",
        json=payload,
        timeout=30
    )

    assert response.status_code == 200
    assert len(response.content) > 0
    assert response.content[:2] == b'PK'

    print(f"   ✓ null context渲染成功")
    return True

def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("poi-tl E2E测试")
    print("=" * 60)

    tests = [
        test_health,
        test_list_templates,
        test_render_complaint,
        test_render_nonexistent_template,
        test_render_with_empty_context,
        test_render_with_null_context,
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
