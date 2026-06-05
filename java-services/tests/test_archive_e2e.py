#!/usr/bin/env python3
"""
POI 归档文书端到端测试 — 使用张某某真实案件数据.

测试内容：
1. 案卷封面（POI）
2. 结案归档登记表（POI）
3. 卷内目录（POI）
4. 起诉状（POI）
5. 尽调报告（POI）

与现有 docxtpl 生成的文件对比。
"""

import json
import sys
import httpx
from pathlib import Path

BASE_URL = "http://127.0.0.1:8090/api/documents"
OUTPUT_DIR = Path(__file__).parent / "test_output_archive"


def _post(endpoint, data, filename):
    """Send POST and save DOCX to output dir."""
    resp = httpx.post(f"{BASE_URL}{endpoint}", json=data, timeout=30)
    resp.raise_for_status()
    OUTPUT_DIR.mkdir(exist_ok=True)
    path = OUTPUT_DIR / filename
    path.write_bytes(resp.content)
    return path, len(resp.content)


# ══════════════════════════════════════════════════════════════════════
# 张某某真实案件数据
# ══════════════════════════════════════════════════════════════════════

LIZITING_ARCHIVE = {
    "caseName": "李某某委托代理张某某涉嫌买卖合同纠纷一案",
    "caseType": "刑事",
    "caseNumber": "(2006)粤0106刑初155号",
    "causeOfAction": "买卖合同纠纷",
    "courtName": "广州市天河区人民法院",
    "caseStage": "一审",
    "trialResult": "被告人张某某犯买卖合同纠纷，判处拘役一个月，缓刑二个月，并处罚金人民币4000元。",
    "oaCaseNumber": "2026GZXS0003",
    "ourPartyName": "张某某",
    "opposingPartyName": "广州市天河区人民检察院",
    "leadLawyer": "王律师",
    "startDate": "2026-02-01",
    "archiveDate": "2026-04-21",
    "year": "2026",
    "contractName": "李某某委托代理张某某涉嫌买卖合同纠纷一案",
    "contractType": "刑事代理合同",
    "archiveItems": [
        {"name": "合同正本与律师办案服务质量监督卡", "pages": "1-2", "note": ""},
        {"name": "授权委托证明材料（户口本）", "pages": "3", "note": "当事人提供"},
        {"name": "所函（检察院授权）", "pages": "4", "note": "2026-03-03"},
        {"name": "赵律师律师证", "pages": "5", "note": "复印件"},
        {"name": "授权委托书（李某某→张某某）", "pages": "6", "note": "2026-02-01"},
        {"name": "所函（现场咨询）", "pages": "7", "note": "2026-02-05"},
        {"name": "王律师律师证", "pages": "8", "note": "复印件"},
        {"name": "鉴定意见通知书", "pages": "9", "note": "当事人传回"},
        {"name": "移送检察院通知", "pages": "10", "note": "2026-03-12"},
        {"name": "认罪认罚具结书", "pages": "11", "note": "2026-04-02"},
        {"name": "起诉书", "pages": "12-13", "note": "2026-04-03"},
        {"name": "开庭通知", "pages": "14", "note": "2026-04-13"},
        {"name": "刑事判决书", "pages": "15-16", "note": "2026-04-16"},
    ],
    "catalogEntries": [
        {"sequenceNumber": "1", "materialName": "委托代理合同", "pageNumbers": "1"},
        {"sequenceNumber": "2", "materialName": "律师办案服务质量监督卡", "pageNumbers": "2"},
        {"sequenceNumber": "3", "materialName": "户口本（授权委托证明）", "pageNumbers": "3"},
        {"sequenceNumber": "4", "materialName": "所函（检察院授权）", "pageNumbers": "4"},
        {"sequenceNumber": "5", "materialName": "赵律师律师证复印件", "pageNumbers": "5"},
        {"sequenceNumber": "6", "materialName": "授权委托书", "pageNumbers": "6"},
        {"sequenceNumber": "7", "materialName": "所函（现场咨询）", "pageNumbers": "7"},
        {"sequenceNumber": "8", "materialName": "王律师律师证复印件", "pageNumbers": "8"},
        {"sequenceNumber": "9", "materialName": "鉴定意见通知书", "pageNumbers": "9"},
        {"sequenceNumber": "10", "materialName": "移送检察院通知书", "pageNumbers": "10"},
        {"sequenceNumber": "11", "materialName": "认罪认罚具结书", "pageNumbers": "11"},
        {"sequenceNumber": "12", "materialName": "起诉书", "pageNumbers": "12-13"},
        {"sequenceNumber": "13", "materialName": "开庭通知书", "pageNumbers": "14"},
        {"sequenceNumber": "14", "materialName": "刑事判决书", "pageNumbers": "15-16"},
    ],
}

LIZITING_COMPLAINT = {
    "courtName": "广州市天河区人民法院",
    "plaintiffName": "广州市天河区人民检察院",
    "plaintiffType": "机关",
    "plaintiffIdNumber": "",
    "plaintiffAddress": "广东省广州市天河区",
    "plaintiffPhone": "",
    "plaintiffLegalRepresentative": "",
    "defendantName": "张某某",
    "defendantType": "自然人",
    "defendantIdNumber": "",
    "defendantAddress": "广东省广州市",
    "defendantPhone": "",
    "lawyerName": "王律师",
    "lawyerFirm": "广州某律师事务所",
    "lawyerLicense": "14406202010000001",
    "causeOfAction": "买卖合同纠纷",
    "litigationClaims": [
        "1. 判处被告人张某某拘役一个月，缓刑二个月",
        "2. 判处被告人张某某缴纳罚金人民币4000元",
    ],
    "factsAndReasons": (
        "被告人张某某于2026年1月15日22时许，饮酒后驾驶粤EXXXXX号小型轿车行驶至广州市天河区XX路时，"
        "被执勤民警查获。经鉴定，被告人张某某血液中乙醇含量为156.3mg/100ml，已达到醉酒驾驶标准。\n"
        "被告人张某某到案后如实供述犯罪事实，且自愿认罪认罚。"
    ),
    "evidenceList": "1. 血液酒精含量鉴定报告；2. 驾驶证及行驶证复印件；3. 证人证言",
    "signatureDate": "2026年4月3日",
}


def test_case_cover():
    path, size = _post("/archive/case-cover", LIZITING_ARCHIVE, "1-案卷封面-张某某.docx")
    print(f"✅ 案卷封面: {path} ({size} bytes)")
    return True


def test_closing_register():
    path, size = _post("/archive/closing-register", LIZITING_ARCHIVE, "2-结案归档登记表-张某某.docx")
    print(f"✅ 结案归档登记表: {path} ({size} bytes)")
    return True


def test_catalog():
    path, size = _post("/archive/catalog", LIZITING_ARCHIVE, "3-卷内目录-张某某.docx")
    print(f"✅ 卷内目录: {path} ({size} bytes)")
    return True


def test_complaint():
    path, size = _post("/complaint", LIZITING_COMPLAINT, "4-起诉状-张某某.docx")
    print(f"✅ 起诉状: {path} ({size} bytes)")
    return True


def test_comparison():
    """Compare POI output with existing docxtpl output."""
    existing_archive = Path("/Users/huangsong21/Downloads/新工作/200-诉讼/4-刑事/2026.02.01-[刑事]张某某醉驾一案/归档文件夹")

    print("\n📊 POI vs docxtpl 文件对比:")
    print("-" * 70)

    comparisons = [
        ("1-案卷封面", "poi_output_archive/1-案卷封面-张某某.docx"),
        ("2-结案归档登记表", "poi_output_archive/2-结案归档登记表-张某某.docx"),
        ("3-卷内目录", "poi_output_archive/3-卷内目录-张某某.docx"),
    ]

    for label, poi_file in comparisons:
        poi_path = OUTPUT_DIR / Path(poi_file).name
        # Find matching existing file
        existing_files = list(existing_archive.glob(f"{label}*"))
        if existing_files and poi_path.exists():
            poi_size = poi_path.stat().st_size
            existing_size = existing_files[0].stat().st_size
            print(f"  {label}:")
            print(f"    POI:     {poi_size:>8,} bytes  ← 新生成")
            print(f"    docxtpl: {existing_size:>8,} bytes  ← 已有")
            ratio = poi_size / existing_size if existing_size > 0 else 0
            print(f"    比值:    {ratio:.2f}x")
        else:
            print(f"  {label}: 对比文件不存在")


def main():
    print("=" * 70)
    print("POI 归档文书端到端测试 — 张某某案件真实数据")
    print("=" * 70)

    results = []
    tests = [
        ("案卷封面", test_case_cover),
        ("结案归档登记表", test_closing_register),
        ("卷内目录", test_catalog),
        ("起诉状", test_complaint),
    ]

    for name, test_fn in tests:
        try:
            ok = test_fn()
            results.append((name, ok))
        except Exception as e:
            print(f"❌ {name}: {e}")
            results.append((name, False))

    print("\n" + "=" * 70)
    print("测试结果:")
    print("=" * 70)
    for name, ok in results:
        print(f"  {'✅' if ok else '❌'} {name}")

    test_comparison()

    passed = sum(1 for _, ok in results if ok)
    print(f"\n{passed}/{len(results)} 测试通过")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
