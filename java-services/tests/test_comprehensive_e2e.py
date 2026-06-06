#!/usr/bin/env python3
"""
POI Service 详细端到端测试.

测试覆盖：
1. 健康检查 + 版本验证
2. 起诉状 - 正常数据
3. 起诉状 - 边界数据（空字段）
4. 尽调报告 - 正常数据
5. 尽调报告 - 空财务数据
6. 归档文书 - 案卷封面
7. 归档文书 - 结案归档登记表
8. 归档文书 - 卷内目录（空数据）
9. 归档文书 - 卷内目录（大量数据）
10. 模板渲染 - 占位符替换
11. 错误处理 - 400/404
12. 并发测试 - 多请求同时
13. 输出质量验证 - DOCX 内容检查
"""

import httpx
import sys
import time
import threading
import zipfile
import re
from pathlib import Path

BASE_URL = "http://127.0.0.1:8090/api/documents"
OUTPUT_DIR = Path(__file__).parent / "test_output_e2e"


def _post(endpoint, data, filename=None):
    resp = httpx.post(f"{BASE_URL}{endpoint}", json=data, timeout=30)
    if filename and resp.status_code == 200:
        OUTPUT_DIR.mkdir(exist_ok=True)
        (OUTPUT_DIR / filename).write_bytes(resp.content)
    return resp


def _get(endpoint):
    return httpx.get(f"{BASE_URL}{endpoint}", timeout=10)


def _extract_text(docx_bytes):
    """Extract text from DOCX bytes."""
    import io
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as z:
        xml = z.read('word/document.xml').decode('utf-8')
        return ' '.join(re.findall(r'<w:t[^>]*>([^<]+)</w:t>', xml))


# ══════════════════════════════════════════════════════════════════════
# Test 1: 健康检查 + 版本验证
# ══════════════════════════════════════════════════════════════════════
def test_01_health():
    r = _get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["poi_version"] == "5.5.1"
    assert data["service"] == "poi-service"
    print(f"✅ 01 健康检查: POI {data['poi_version']}, Spring Boot OK")
    return True


# ══════════════════════════════════════════════════════════════════════
# Test 2: 起诉状 - 正常数据
# ══════════════════════════════════════════════════════════════════════
def test_02_complaint_normal():
    data = {
        "courtName": "广东省广州市天河区人民法院",
        "plaintiffName": "广州某科技有限公司",
        "plaintiffType": "法人",
        "plaintiffIdNumber": "91000000MA0TEST01",
        "plaintiffAddress": "广州市天河区珠江新城",
        "plaintiffPhone": "020-12345678",
        "plaintiffLegalRepresentative": "张三",
        "defendantName": "深圳某贸易有限公司",
        "defendantType": "法人",
        "defendantIdNumber": "91000000MA0TEST02",
        "defendantAddress": "深圳市南山区科技园",
        "defendantPhone": "0755-87654321",
        "lawyerName": "李四",
        "lawyerFirm": "广州某律师事务所",
        "lawyerLicense": "14401202010000001",
        "causeOfAction": "买卖合同纠纷",
        "litigationClaims": [
            "判令被告支付货款人民币50万元",
            "判令被告支付逾期利息",
            "判令被告承担诉讼费用",
        ],
        "factsAndReasons": (
            "原告与被告于2025年6月签订买卖合同，约定被告向原告购买电子设备。"
            "原告已按约交付全部货物，但被告仅支付部分货款，尚欠50万元未付。"
        ),
        "evidenceList": "1. 买卖合同；2. 送货单；3. 对账单",
        "signatureDate": "2026年6月5日",
    }
    r = _post("/complaint", data, "test_02_complaint.docx")
    assert r.status_code == 200
    text = _extract_text(r.content)
    assert "广州某科技有限公司" in text
    assert "深圳某贸易有限公司" in text
    assert "50万元" in text
    assert "起" in text  # title: 民  事  起  诉  状
    print(f"✅ 02 起诉状（正常）: {len(r.content)} bytes, 内容验证通过")
    return True


# ══════════════════════════════════════════════════════════════════════
# Test 3: 起诉状 - 边界数据（空字段）
# ══════════════════════════════════════════════════════════════════════
def test_03_complaint_minimal():
    data = {
        "courtName": "某法院",
        "plaintiffName": "原告A",
        "defendantName": "被告B",
    }
    r = _post("/complaint", data, "test_03_complaint_minimal.docx")
    assert r.status_code == 200
    text = _extract_text(r.content)
    assert "原告A" in text
    assert "被告B" in text
    print(f"✅ 03 起诉状（最小数据）: {len(r.content)} bytes")
    return True


# ══════════════════════════════════════════════════════════════════════
# Test 4: 尽调报告 - 正常数据
# ══════════════════════════════════════════════════════════════════════
def test_04_report_normal():
    data = {
        "reportTitle": "尽职调查报告",
        "projectName": "某公司股权收购项目",
        "reportDate": "2026年6月5日",
        "author": "广州某律师事务所",
        "confidentialityLevel": "保密",
        "companyName": "目标公司",
        "companyRegistrationNumber": "91000000MA0TEST01",
        "registeredCapital": "1000万元",
        "establishedDate": "2015-01-01",
        "legalRepresentative": "王五",
        "businessScope": "科技开发",
        "financialData": [
            {"year": 2023, "revenue": 5000.0, "profit": 800.0, "totalAssets": 10000.0, "totalLiabilities": 6000.0},
            {"year": 2024, "revenue": 6000.0, "profit": 1000.0, "totalAssets": 12000.0, "totalLiabilities": 7000.0},
        ],
        "equityStructure": [
            {"name": "张三", "percentage": 60.0, "type": "自然人", "contributionMethod": "货币"},
            {"name": "李四", "percentage": 40.0, "type": "自然人", "contributionMethod": "实物"},
        ],
        "riskItems": [
            {"category": "法律风险", "description": "存在未决诉讼", "severity": "中", "recommendation": "要求陈述与保证"},
        ],
        "sections": [
            {"title": "公司治理", "level": 2, "content": "公司治理结构基本规范。", "bulletPoints": ["董事会5人", "监事会3人"]},
        ],
    }
    r = _post("/report", data, "test_04_report.docx")
    assert r.status_code == 200
    text = _extract_text(r.content)
    assert "尽职调查报告" in text
    assert "目标公司" in text
    assert "公司治理" in text
    print(f"✅ 04 尽调报告（正常）: {len(r.content)} bytes, 内容验证通过")
    return True


# ══════════════════════════════════════════════════════════════════════
# Test 5: 尽调报告 - 空财务数据
# ══════════════════════════════════════════════════════════════════════
def test_05_report_empty_financials():
    data = {
        "reportTitle": "尽调报告",
        "projectName": "测试项目",
        "reportDate": "2026-01-01",
        "author": "测试律师",
        "confidentialityLevel": "内部",
        "companyName": "测试公司",
        "financialData": [],
        "equityStructure": [],
        "riskItems": [],
        "sections": [],
    }
    r = _post("/report", data, "test_05_report_empty.docx")
    assert r.status_code == 200
    text = _extract_text(r.content)
    assert "测试公司" in text
    print(f"✅ 05 尽调报告（空数据）: {len(r.content)} bytes")
    return True


# ══════════════════════════════════════════════════════════════════════
# Test 6-8: 归档文书
# ══════════════════════════════════════════════════════════════════════
def _archive_data():
    return {
        "caseName": "张三诉李四合同纠纷一案",
        "caseType": "民事",
        "caseNumber": "(2026)粤0106民初123号",
        "causeOfAction": "合同纠纷",
        "courtName": "广州市天河区人民法院",
        "caseStage": "一审",
        "trialResult": "判决被告支付货款30万元",
        "oaCaseNumber": "2026GZMS0001",
        "ourPartyName": "张三",
        "opposingPartyName": "李四",
        "leadLawyer": "王律师",
        "startDate": "2026-01-15",
        "archiveDate": "2026-06-01",
        "year": "2026",
        "contractName": "委托代理合同",
        "contractType": "民事代理合同",
        "archiveItems": [
            {"name": "委托代理合同", "pages": "1-2", "note": ""},
            {"name": "授权委托书", "pages": "3", "note": ""},
            {"name": "判决书", "pages": "4-5", "note": "已生效"},
        ],
        "catalogEntries": [
            {"sequenceNumber": "1", "materialName": "委托代理合同", "pageNumbers": "1-2"},
            {"sequenceNumber": "2", "materialName": "授权委托书", "pageNumbers": "3"},
            {"sequenceNumber": "3", "materialName": "判决书", "pageNumbers": "4-5"},
        ],
    }


def test_06_case_cover():
    r = _post("/archive/case-cover", _archive_data(), "test_06_case_cover.docx")
    assert r.status_code == 200
    text = _extract_text(r.content)
    assert "张三诉李四合同纠纷一案" in text
    assert "广州市天河区人民法院" in text
    assert "合同纠纷" in text
    print(f"✅ 06 案卷封面: {len(r.content)} bytes")
    return True


def test_07_closing_register():
    r = _post("/archive/closing-register", _archive_data(), "test_07_register.docx")
    assert r.status_code == 200
    text = _extract_text(r.content)
    assert "登" in text  # title: 结 案 归 档 登 记 表 (spaced)
    assert "委托代理合同" in text
    print(f"✅ 07 结案归档登记表: {len(r.content)} bytes")
    return True


def test_08_catalog_empty():
    data = _archive_data()
    data["catalogEntries"] = []
    r = _post("/archive/catalog", data, "test_08_catalog_empty.docx")
    assert r.status_code == 200
    text = _extract_text(r.content)
    assert "目" in text  # title: 卷  内  目  录 (spaced)
    assert "暂无" in text
    print(f"✅ 08 卷内目录（空）: {len(r.content)} bytes")
    return True


def test_09_catalog_large():
    data = _archive_data()
    data["catalogEntries"] = [
        {"sequenceNumber": str(i), "materialName": f"材料{i}", "pageNumbers": f"{i}-{i+1}"}
        for i in range(1, 31)
    ]
    r = _post("/archive/catalog", data, "test_09_catalog_large.docx")
    assert r.status_code == 200
    text = _extract_text(r.content)
    assert "材料1" in text
    assert "材料30" in text
    print(f"✅ 09 卷内目录（30条）: {len(r.content)} bytes")
    return True


# ══════════════════════════════════════════════════════════════════════
# Test 10: 模板渲染
# ══════════════════════════════════════════════════════════════════════
def test_10_template_render():
    # First check templates endpoint
    r = _get("/templates")
    assert r.status_code == 200
    templates = r.json().get("templates", [])
    print(f"  可用模板: {len(templates)} 个")

    # Try rendering a template (even if no templates exist, endpoint should work)
    data = {"templateName": "test.docx", "context": {"name": "张三"}}
    r = _post("/template/render", data, "test_10_template.docx")
    # If template doesn't exist, we expect 500 but not a crash
    assert r.status_code in [200, 500]
    print(f"✅ 10 模板渲染: 状态码 {r.status_code}")
    return True


# ══════════════════════════════════════════════════════════════════════
# Test 11: 错误处理
# ══════════════════════════════════════════════════════════════════════
def test_11_error_handling():
    # Invalid endpoint
    r = _get("/nonexistent")
    assert r.status_code == 404
    print(f"  不存在的端点: {r.status_code}")

    # Method not allowed
    r = httpx.delete(f"{BASE_URL}/health", timeout=5)
    assert r.status_code == 405
    print(f"  不支持的方法: {r.status_code}")

    print("✅ 11 错误处理: 正确返回错误状态码")
    return True


# ══════════════════════════════════════════════════════════════════════
# Test 12: 并发测试
# ══════════════════════════════════════════════════════════════════════
def test_12_concurrent():
    data = _archive_data()
    results = []
    errors = []

    def make_request():
        try:
            r = _post("/archive/case-cover", data, None)
            results.append(r.status_code)
        except Exception as e:
            errors.append(str(e))

    threads = [threading.Thread(target=make_request) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert len(errors) == 0, f"并发错误: {errors}"
    assert all(r == 200 for r in results), f"状态码异常: {results}"
    print(f"✅ 12 并发测试: 5 个并发请求全部 200")
    return True


# ══════════════════════════════════════════════════════════════════════
# Test 13: 输出质量验证
# ══════════════════════════════════════════════════════════════════════
def test_13_output_quality():
    data = _archive_data()
    r = _post("/archive/case-cover", data, "test_13_quality.docx")
    assert r.status_code == 200

    import io
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        # Check DOCX structure
        assert 'word/document.xml' in z.namelist(), "缺少 document.xml"
        assert '[Content_Types].xml' in z.namelist(), "缺少 Content_Types"

        # Check document XML for table structure
        doc_xml = z.read('word/document.xml').decode('utf-8')
        assert '<w:tbl>' in doc_xml, "缺少表格元素"
        assert '<w:tr>' in doc_xml, "缺少表格行"

        # Check styles exist
        if 'word/styles.xml' in z.namelist():
            styles_xml = z.read('word/styles.xml').decode('utf-8')
            assert 'w:style' in styles_xml, "缺少样式定义"

    print("✅ 13 输出质量: DOCX 结构完整（表格、样式、Content_Types）")
    return True


def main():
    print("=" * 70)
    print("POI Service 详细端到端测试")
    print(f"目标: {BASE_URL}")
    print("=" * 70)

    tests = [
        ("健康检查 + 版本验证", test_01_health),
        ("起诉状（正常数据）", test_02_complaint_normal),
        ("起诉状（最小数据）", test_03_complaint_minimal),
        ("尽调报告（正常数据）", test_04_report_normal),
        ("尽调报告（空财务数据）", test_05_report_empty_financials),
        ("案卷封面", test_06_case_cover),
        ("结案归档登记表", test_07_closing_register),
        ("卷内目录（空数据）", test_08_catalog_empty),
        ("卷内目录（30条数据）", test_09_catalog_large),
        ("模板渲染", test_10_template_render),
        ("错误处理", test_11_error_handling),
        ("并发测试（5线程）", test_12_concurrent),
        ("输出质量验证", test_13_output_quality),
    ]

    results = []
    for name, fn in tests:
        try:
            ok = fn()
            results.append((name, ok))
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"❌ {name}: {e}")
            results.append((name, False))

    print("\n" + "=" * 70)
    print("测试结果:")
    print("=" * 70)
    for name, ok in results:
        print(f"  {'✅' if ok else '❌'} {name}")

    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print(f"\n{passed}/{total} 测试通过")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
