"""POI Service integration test script.

Tests the POI service by calling its endpoints directly and via the Django client.
Run the POI service first: cd java-services/poi-service && ./mvnw spring-boot:run

Usage:
    cd backend
    python ../java-services/poi-service/test_poi_integration.py
"""

from __future__ import annotations

import json
import sys
import os
from pathlib import Path

# Setup Django
project_root = str(Path(__file__).resolve().parent.parent.parent)
backend_dir = os.path.join(project_root, "backend")
api_system_dir = os.path.join(project_root, "backend", "apiSystem")
sys.path.insert(0, api_system_dir)
sys.path.insert(0, backend_dir)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")

import django

django.setup()


def test_poi_health():
    """Test 1: Health check"""
    from apps.core.services.poi_client import get_poi_client

    client = get_poi_client()
    try:
        result = client.health_check()
        print(f"✅ Health check: {result}")
        return True
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return False


def test_complaint_generation():
    """Test 2: Generate 起诉状"""
    from apps.core.services.poi_client import get_poi_client

    client = get_poi_client()
    data = {
        "courtName": "广东省广州市天河区人民法院",
        "plaintiffName": "深圳市某科技有限公司",
        "plaintiffType": "法人",
        "plaintiffIdNumber": "91440600MA5XXXXXX",
        "plaintiffAddress": "广东省广州市天河区珠江新城",
        "plaintiffPhone": "0757-87778888",
        "plaintiffLegalRepresentative": "张三",
        "defendantName": "广州市某商贸有限公司",
        "defendantType": "法人",
        "defendantIdNumber": "91440600MA6YYYYYY",
        "defendantAddress": "广东省广州市天河区体育西路100号",
        "defendantPhone": "0757-82223333",
        "lawyerName": "李四",
        "lawyerFirm": "广州某律师事务所",
        "lawyerLicense": "14406202010000001",
        "causeOfAction": "金融借款合同纠纷",
        "litigationClaims": [
            "判令被告偿还借款本金人民币100万元及利息",
            "判令被告承担本案诉讼费用",
        ],
        "factsAndReasons": (
            "原告与被告于2024年1月15日签订《流动资金借款合同》，"
            "约定被告向原告借款人民币100万元，借款期限12个月，年利率6%。\n"
            "借款到期后，被告未能按期偿还本金及利息，经原告多次催告仍未履行。\n"
            "截至起诉之日，被告尚欠本金100万元，利息人民币5万元。"
        ),
        "evidenceList": "1. 流动资金借款合同；2. 放款凭证；3. 催收函及送达回证",
        "signatureDate": "2026年6月5日",
    }

    try:
        docx_bytes = client.generate_complaint(data)
        output_path = Path(__file__).parent / "test_output_complaint.docx"
        output_path.write_bytes(docx_bytes)
        print(f"✅ 起诉状 generated: {output_path} ({len(docx_bytes)} bytes)")
        return True
    except Exception as e:
        print(f"❌ 起诉状 generation failed: {e}")
        return False


def test_report_generation():
    """Test 3: Generate 尽调报告 (due diligence report)"""
    import apps.core.services.poi_client as poi_mod
    from apps.core.services.poi_client import POIServiceClient

    poi_mod._default_client = None  # Reset singleton
    client = POIServiceClient()
    data = {
        "reportTitle": "尽职调查报告",
        "projectName": "广州市某商贸有限公司股权收购项目",
        "reportDate": "2026年6月5日",
        "author": "广州某律师事务所",
        "confidentialityLevel": "机密",
        "companyName": "广州市某商贸有限公司",
        "companyRegistrationNumber": "91440600MA6YYYYYY",
        "registeredCapital": "5000万元人民币",
        "establishedDate": "2010年3月15日",
        "legalRepresentative": "王五",
        "businessScope": "日用百货、服装鞋帽、家用电器的批发零售；商业管理服务",
        "financialData": [
            {"year": 2023, "revenue": 8500.5, "profit": 1200.3, "totalAssets": 15000.0, "totalLiabilities": 9500.0},
            {"year": 2024, "revenue": 9200.8, "profit": 1500.6, "totalAssets": 17500.0, "totalLiabilities": 10200.0},
            {"year": 2025, "revenue": 10100.2, "profit": 1800.4, "totalAssets": 20000.0, "totalLiabilities": 11000.0},
        ],
        "equityStructure": [
            {"name": "张三", "percentage": 40.0, "type": "自然人", "contributionMethod": "货币"},
            {"name": "李四", "percentage": 30.0, "type": "自然人", "contributionMethod": "货币"},
            {"name": "深圳市某投资有限公司", "percentage": 20.0, "type": "法人", "contributionMethod": "实物"},
            {"name": "员工持股平台", "percentage": 10.0, "type": "法人", "contributionMethod": "货币"},
        ],
        "riskItems": [
            {
                "category": "法律风险",
                "description": "存在3起未决诉讼，涉及金额约200万元",
                "severity": "中",
                "recommendation": "要求卖方在交易文件中作出陈述与保证，并设置赔偿机制",
            },
            {
                "category": "财务风险",
                "description": "应收账款周转天数偏长（90天），存在坏账风险",
                "severity": "中",
                "recommendation": "对前十大应收账户进行逐一核查，评估回收可能性",
            },
            {
                "category": "合规风险",
                "description": "部分经营场所消防验收手续不完善",
                "severity": "低",
                "recommendation": "要求卖方在交割前完成消防验收整改",
            },
        ],
        "sections": [
            {
                "title": "公司治理",
                "level": 2,
                "content": (
                    "目标公司设有董事会，由5名董事组成，其中独立董事1名。\n"
                    "监事会由3名监事组成。公司章程规定重大事项需经董事会三分之二以上董事同意。\n"
                    "经核查，公司治理结构基本规范，议事规则执行情况良好。"
                ),
                "tableData": [
                    {"职务": "姓名", "任职情况": "任期"},
                    {"职务": "董事长", "姓名": "张三", "任职情况": "2024-2027"},
                    {"职务": "董事", "姓名": "李四", "任职情况": "2024-2027"},
                    {"职务": "董事", "姓名": "赵六", "任职情况": "2024-2027"},
                    {"职务": "独立董事", "姓名": "钱七", "任职情况": "2024-2027"},
                    {"职务": "监事", "姓名": "孙八", "任职情况": "2024-2027"},
                ],
            },
            {
                "title": "知识产权",
                "level": 2,
                "content": "目标公司持有注册商标12项，专利权5项（其中发明专利2项，实用新型3项）。所有知识产权均在有效期内，权属清晰，不存在权属争议。",
                "bulletPoints": [
                    "注册商标：某商贸（第35类）、某优选（第35类）等12项",
                    "发明专利：一种智能仓储管理系统（专利号：ZL20201XXXXXX.X）",
                    "实用新型：3项（均为物流设备相关）",
                    "软件著作权：3项（ERP系统、会员管理系统、供应链管理系统）",
                ],
            },
            {
                "title": "劳动用工",
                "level": 2,
                "content": (
                    "目标公司现有员工450人，其中正式员工380人，劳务派遣人员70人。\n"
                    "全部员工均已签订书面劳动合同，社会保险和住房公积金缴纳比例符合法律规定。\n"
                    "经核查，不存在重大劳动争议或群体性事件风险。"
                ),
            },
        ],
    }

    try:
        docx_bytes = client.generate_report(data)
        output_path = Path(__file__).parent / "test_output_report.docx"
        output_path.write_bytes(docx_bytes)
        print(f"✅ 尽调报告 generated: {output_path} ({len(docx_bytes)} bytes)")
        return True
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ 尽调报告 generation failed: {e}")
        return False


def test_ninja_api_health():
    """Test 4: Django Ninja API health endpoint"""
    from django.test import RequestFactory
    from apps.core.api.poi_api import poi_health

    factory = RequestFactory()
    request = factory.get("/api/v1/poi/health")
    response = poi_health(request)
    print(f"✅ Ninja API health: {response}")
    return True


def main():
    print("=" * 60)
    print("POI Service Integration Tests")
    print("=" * 60)

    results = []

    results.append(("Health Check", test_poi_health()))
    results.append(("起诉状生成", test_complaint_generation()))
    results.append(("尽调报告生成", test_report_generation()))
    results.append(("Ninja API Health", test_ninja_api_health()))

    print("\n" + "=" * 60)
    print("Results:")
    print("=" * 60)
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {name}")

    passed = sum(1 for _, p in results if p)
    total = len(results)
    print(f"\n{passed}/{total} tests passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
