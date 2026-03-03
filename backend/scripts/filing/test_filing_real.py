"""创建真实测试数据并运行民事一审立案

流程: 创建客户 → 创建合同 → 创建案件 → 关联当事人/法院/材料 → 调用立案服务

用法:
    cd backend/apiSystem
    source ../.venv/bin/activate
    python ../scripts/filing/test_filing_real.py
"""
import sys
sys.path.insert(0, "/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apiSystem")
sys.path.insert(0, "/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend")

import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apiSystem.settings")

import django
django.setup()

import pathlib
from django.core.files.base import ContentFile

# ==================== 1. 获取律师账号 ====================
from apps.organization.models import Lawyer, AccountCredential

lawyer = Lawyer.objects.filter(username="黄崧").first()
if not lawyer:
    print("ERROR: 找不到律师账号'黄崧'，请先在后台创建")
    sys.exit(1)

# 确保有一张网凭证
cred, _ = AccountCredential.objects.get_or_create(
    lawyer=lawyer,
    site_name="一张网",
    defaults={"account": "18924051453", "password": "532121wsN"},
)

# ==================== 2. 创建客户 ====================
from apps.client.models import Client

CLIENTS_DATA = [
    {
        "name": "四川省宜宾五粮液集团有限公司",
        "client_type": "legal",
        "id_number": "91511500709066998M",
        "legal_representative": "曾从钦",
        "address": "宜宾市岷江西路150号",
        "phone": "0831-3553988",
        "is_our_client": True,
    },
    {
        "name": "中国贵州茅台酒厂（集团）有限责任公司",
        "client_type": "legal",
        "id_number": "915200002149908473",
        "legal_representative": "陈华",
        "address": "贵州省贵阳市云岩区外环东路东山巷4号",
        "phone": "0851-22388183",
        "is_our_client": False,
    },
    {
        "name": "恒大地产集团有限公司",
        "client_type": "legal",
        "id_number": "91440101231245152Y",
        "legal_representative": "赵长龙",
        "address": "深圳市南山区海德三道126号卓越后海金融中心2801房",
        "phone": "020-89182147",
        "is_our_client": False,
    },
    {
        "name": "宇树科技股份有限公司",
        "client_type": "legal",
        "id_number": "91330108MA27YJ5H56",
        "legal_representative": "王兴兴",
        "address": "浙江省杭州市滨江区西兴街道东流路88号1幢306室",
        "phone": "0571-56716562",
        "is_our_client": False,
    },
]

clients = {}
for data in CLIENTS_DATA:
    obj, created = Client.objects.update_or_create(
        id_number=data["id_number"],
        defaults=data,
    )
    clients[data["name"]] = obj
    print(f"{'创建' if created else '已有'}客户: {obj.name}")

wuliangye = clients["四川省宜宾五粮液集团有限公司"]
maotai = clients["中国贵州茅台酒厂（集团）有限责任公司"]
hengda = clients["恒大地产集团有限公司"]
yushu = clients["宇树科技股份有限公司"]

# ==================== 3. 创建合同 ====================
from apps.contracts.models import Contract

contract, created = Contract.objects.get_or_create(
    name="五粮液诉茅台民间借贷纠纷代理合同",
    defaults={
        "case_type": "civil",
        "status": "active",
        "fee_mode": "fixed",
        "fixed_amount": "50000.00",
    },
)
print(f"{'创建' if created else '已有'}合同: {contract.name}")

# ==================== 4. 创建案件 ====================
from apps.cases.models import Case, CaseParty, SupervisingAuthority

case, created = Case.objects.get_or_create(
    name="五粮液诉茅台、恒大、宇树民间借贷纠纷案",
    defaults={
        "contract": contract,
        "cause_of_action": "民间借贷纠纷",
        "target_amount": "5000000.00",
        "case_type": "civil_first_instance",
    },
)
print(f"{'创建' if created else '已有'}案件: {case.name} (id={case.id})")

# ==================== 5. 关联当事人 ====================
# 原告：五粮液（我方）
# 被告：茅台、恒大
# 第三人：宇树
PARTIES = [
    (wuliangye, "plaintiff"),
    (maotai, "defendant"),
    (hengda, "defendant"),
    (yushu, "third_party"),
]
for client, status in PARTIES:
    obj, created = CaseParty.objects.get_or_create(
        case=case, client=client,
        defaults={"legal_status": status},
    )
    if not created and obj.legal_status != status:
        obj.legal_status = status
        obj.save()
    print(f"  当事人: {client.name} ({status})")

# ==================== 6. 设置管辖法院 ====================
sa, created = SupervisingAuthority.objects.get_or_create(
    case=case,
    authority_type="trial",
    defaults={"name": "广州市天河区人民法院"},
)
if not created:
    sa.name = "广州市天河区人民法院"
    sa.save()
print(f"管辖法院: {sa.name}")

# ==================== 7. 创建 mock 材料文件 ====================
from apps.cases.models import CaseMaterial
from apps.cases.models.log import CaseLogAttachment

mock_dir = pathlib.Path("/tmp/mock_filing_files")
mock_dir.mkdir(exist_ok=True)

MATERIAL_SLOTS = [
    ("起诉状", "起诉状.pdf", "plaintiff"),
    ("当事人身份证明材料", "身份证明.pdf", "plaintiff"),
    ("授权委托书", "授权委托书.pdf", "plaintiff"),
    ("证据目录及证据材料", "证据材料.pdf", "plaintiff"),
    ("送达地址确认书", "送达地址确认书.pdf", "plaintiff"),
]

for type_name, filename, side in MATERIAL_SLOTS:
    if CaseMaterial.objects.filter(case=case, type_name=type_name).exists():
        print(f"  材料已存在: {type_name}")
        continue
    CaseMaterial.objects.create(
        case=case,
        category="submission",
        type_name=type_name,
        side=side,
        source_attachment=None,
    )
    file_path = mock_dir / filename
    file_path.write_bytes(b"%PDF-1.4 mock content for " + type_name.encode() + b"\n")
    print(f"  创建材料: {type_name}")

# ==================== 8. 构建 case_data 并立案 ====================
# 复用 API 层的 case_data 构建逻辑
from apps.automation.api.court_filing_api import _resolve_court_name, _run_filing

# 构建 case_data（参考 court_filing_api.py 的逻辑）
case_data: dict = {
    "court_name": sa.name,
    "cause_of_action": case.cause_of_action or "",
    "target_amount": str(case.target_amount) if case.target_amount else "",
    "province": "广东省",
    "case_id": case.id,
}

# 当事人
from apps.cases.models import CaseParty as CP
from apps.core.utils.id_card_utils import IdCardUtils

plaintiffs, defendants, third_parties = [], [], []
for p in CP.objects.filter(case=case).select_related("client"):
    c = p.client
    is_natural = c.client_type == "natural"
    party_data: dict = {
        "name": c.name,
        "client_type": c.client_type,
        "address": c.address or "",
        "phone": c.phone or "",
    }
    if is_natural:
        party_data["id_number"] = c.id_number or ""
        party_data["gender"] = IdCardUtils.extract_gender(c.id_number or "") or "男"
    else:
        party_data["uscc"] = c.id_number or ""
        party_data["legal_rep"] = c.legal_representative or ""
        party_data["legal_rep_id_number"] = c.legal_representative_id_number or ""

    if p.legal_status == "plaintiff":
        plaintiffs.append(party_data)
    elif p.legal_status == "defendant":
        defendants.append(party_data)
    elif p.legal_status == "third_party":
        third_parties.append(party_data)

case_data["plaintiffs"] = plaintiffs
case_data["defendants"] = defendants
if third_parties:
    case_data["third_parties"] = third_parties

# 代理人（律师自己）
case_data["agent"] = {
    "name": "黄崧",
    "id_number": "45120219941015001X",
    "gender": "男",
    "phone": "13768185702",
    "address": "广东省广州市天河区某律所",
    "law_firm": "北京金诚同达（广州）律师事务所",
    "bar_number": "14401202310613600",
}

# 材料（直接用 mock 文件路径，因为 source_attachment 为 null）
SLOT_KEYWORDS = [
    ("0", ["起诉状", "诉状"]),
    ("1", ["身份证明", "营业执照", "身份证", "户口"]),
    ("2", ["委托", "授权", "代理", "律师执业证", "执业证"]),
    ("3", ["证据目录", "证据材料", "证据"]),
    ("4", ["送达地址确认书", "送达地址"]),
]

def _match_slot(type_name: str) -> str:
    for slot, keywords in SLOT_KEYWORDS:
        if any(kw in type_name for kw in keywords):
            return slot
    return "5"

materials_map: dict = {}
for type_name, filename, _ in MATERIAL_SLOTS:
    file_path = str(mock_dir / filename)
    slot = _match_slot(type_name)
    materials_map.setdefault(slot, []).append(file_path)

case_data["materials"] = materials_map

print(f"\n案件数据构建完成:")
print(f"  原告: {[p['name'] for p in plaintiffs]}")
print(f"  被告: {[p['name'] for p in defendants]}")
print(f"  第三人: {[p['name'] for p in third_parties]}")
print(f"  材料槽位: {list(materials_map.keys())}")
print(f"\n开始立案...")

# ==================== 9. 执行立案 ====================
_run_filing(
    account=str(cred.account),
    password=str(cred.password),
    case_data=case_data,
    filing_type="civil",
)
print("立案任务完成")
