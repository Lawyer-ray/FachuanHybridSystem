"""快速验证民事一审 & 申请执行立案流程（mock数据，不依赖Django ORM）

用法:
    cd backend/apiSystem
    source ../.venv/bin/activate
    python ../scripts/filing/test_filing.py civil
    python ../scripts/filing/test_filing.py execution
"""
import sys

sys.path.insert(0, "/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apiSystem")
sys.path.insert(0, "/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend")

import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")
django.setup()

import pathlib

from playwright.sync_api import sync_playwright

from apps.automation.services.scraper.sites.court_zxfw import CourtZxfwService
from apps.automation.services.scraper.sites.court_zxfw_filing import CourtZxfwFilingService

ACCOUNT = "18924051453"
PASSWORD = "532121wsN"

# ---- mock 材料文件 ----
mock_dir = pathlib.Path("/tmp/mock_filing_files")
mock_dir.mkdir(exist_ok=True)

def _pdf(name: str) -> str:
    p = mock_dir / name
    if not p.exists():
        p.write_bytes(b"%PDF-1.4 mock\n")
    return str(p)

CIVIL_MATERIALS = {
    "0": [_pdf("起诉状.pdf")],
    "1": [_pdf("身份证明.pdf")],
    "2": [_pdf("授权委托书.pdf")],
    "3": [_pdf("证据材料.pdf")],
    "4": [_pdf("送达地址确认书.pdf")],
}

EXEC_MATERIALS = {
    "0": [_pdf("执行申请书.pdf")],
    "1": [_pdf("执行依据文书.pdf")],
    "2": [_pdf("授权委托书.pdf")],
    "3": [_pdf("申请人身份材料.pdf")],
    "4": [_pdf("送达地址确认书.pdf")],
}

# ---- 当事人：法人 ----
LEGAL_A = {
    "client_type": "legal",
    "name": "广州某科技有限公司",
    "uscc": "915115007118234259",
    "legal_rep": "黄某某",
    "legal_rep_id_number": "61213319711212421X",
    "address": "广东省广州市天河区某街道1号",
    "phone": "13800138001",
}
LEGAL_B = {
    "client_type": "legal",
    "name": "深圳某贸易有限公司",
    "uscc": "915115007118234259",
    "legal_rep": "李某某",
    "legal_rep_id_number": "61213319711212421X",
    "address": "广东省深圳市南山区某路2号",
    "phone": "13800138002",
}

# ---- 当事人：自然人 ----
NATURAL_A = {
    "client_type": "natural",
    "name": "张三",
    "id_number": "61213319711212421X",
    "gender": "男",
    "address": "广东省广州市越秀区某路3号",
    "phone": "13800138003",
}
NATURAL_B = {
    "client_type": "natural",
    "name": "李四",
    "id_number": "61213319711212421X",
    "gender": "男",
    "address": "广东省广州市海珠区某街4号",
    "phone": "13800138004",
}

# ---- 当事人：非法人组织 ----
NON_LEGAL_ORG = {
    "client_type": "non_legal_org",
    "name": "广州某律师事务所",
    "uscc": "915115007118234259",
    "legal_rep": "王五",
    "legal_rep_id_number": "61213319711212421X",
    "address": "广东省广州市天河区某大厦5号",
    "phone": "13800138005",
}

# ---- 代理人 ----
AGENT = {
    "name": "黄崧",
    "id_number": "45120219941015001X",
    "gender": "男",
    "phone": "13768185702",
    "address": "广东省广州市天河区某律所",
    "law_firm": "北京金诚同达（广州）律师事务所",
    "bar_number": "14401202310613600",
}

# ---- 民事一审：多原告（法人+自然人）、多被告（自然人+非法人组织）、多第三人 ----
CIVIL_CASE_DATA = {
    "court_name": "广州市天河区人民法院",
    "cause_of_action": "民间借贷纠纷",
    "target_amount": "100000",
    "province": "广东省",
    "plaintiffs": [LEGAL_A, NATURAL_A],
    "defendants": [NATURAL_B, NON_LEGAL_ORG],
    "third_parties": [LEGAL_B],
    "agent": AGENT,
    "materials": CIVIL_MATERIALS,
}

# ---- 申请执行：多申请执行人（法人+自然人）、多被执行人（自然人+法人）----
EXEC_CASE_DATA = {
    "court_name": "广州市天河区人民法院",
    "province": "广东省",
    "original_case_number": "（2024）粤0106民初12345号",
    "execution_basis_type": "民商",
    "execution_reason": "申请人依据生效判决申请强制执行。",
    "execution_request": "请求执行被执行人偿还借款本金100000元及利息。",
    "plaintiffs": [LEGAL_A, NATURAL_A],   # 申请执行人
    "defendants": [NATURAL_B, LEGAL_B],   # 被执行人
    "agent": AGENT,
    "materials": EXEC_MATERIALS,
}


def run(filing_type: str) -> None:
    case_data = CIVIL_CASE_DATA if filing_type == "civil" else EXEC_CASE_DATA
    print(f"\n{'='*50}\n开始测试: {filing_type}\n{'='*50}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        try:
            login_svc = CourtZxfwService(page=page, context=context)
            result = login_svc.login(account=ACCOUNT, password=PASSWORD)
            if not result.get("success"):
                print(f"登录失败: {result}")
                return

            filing_svc = CourtZxfwFilingService(page=page, save_debug=True)
            if filing_type == "civil":
                out = filing_svc.file_case(case_data)
            else:
                out = filing_svc.file_execution(case_data)
            print(f"结果: {out}")
        except Exception as e:
            import traceback
            print(f"异常: {e}")
            traceback.print_exc()
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "civil"
    run(mode)
