"""
Model 相关的 Hypothesis 策略
"""
from hypothesis import strategies as st
from hypothesis.extra.django import from_model
from apps.organization.models import LawFirm, Lawyer
from apps.client.models import Client
from apps.contracts.models import Contract
from apps.cases.models import Case
from .common_strategies import chinese_text, phone_number, decimal_amount


@st.composite
def law_firm_strategy(draw):
    """
    生成律所数据
    
    Returns:
        dict: 律所数据字典
    """
    return {
        'name': draw(chinese_text(min_size=2, max_size=50)),
        'address': draw(chinese_text(min_size=5, max_size=100)),
        'phone': draw(phone_number()),
    }


@st.composite
def lawyer_strategy(draw, law_firm=None):
    """
    生成律师数据
    
    Args:
        law_firm: 律所对象（可选）
        
    Returns:
        dict: 律师数据字典
    """
    return {
        'username': draw(st.text(
            alphabet=st.characters(
                whitelist_categories=('Ll', 'Lu', 'Nd'),
                min_codepoint=ord('a'),
                max_codepoint=ord('z')
            ),
            min_size=3,
            max_size=20
        )),
        'real_name': draw(chinese_text(min_size=2, max_size=10)),
        'phone': draw(phone_number()),
        'is_admin': draw(st.booleans()),
    }


@st.composite
def client_strategy(draw):
    """
    生成客户数据
    
    Returns:
        dict: 客户数据字典
    """
    client_type = draw(st.sampled_from([Client.NATURAL, Client.LEGAL, Client.NON_LEGAL_ORG]))
    
    if client_type == Client.NATURAL:
        name = draw(chinese_text(min_size=2, max_size=10))
        legal_representative = ""
    else:
        name = draw(chinese_text(min_size=3, max_size=50))
        legal_representative = draw(chinese_text(min_size=2, max_size=10))
    
    return {
        'name': name,
        'phone': draw(phone_number()),
        'address': draw(chinese_text(min_size=5, max_size=100)),
        'client_type': client_type,
        'legal_representative': legal_representative,
        'is_our_client': draw(st.booleans()),
    }


@st.composite
def contract_strategy(draw):
    """
    生成合同数据
    
    Returns:
        dict: 合同数据字典
    """
    from apps.cases.models import CaseType, CaseStatus
    from apps.contracts.models import FeeMode
    
    fee_mode = draw(st.sampled_from([FeeMode.FIXED, FeeMode.SEMI_RISK, FeeMode.FULL_RISK]))
    
    data = {
        'name': draw(chinese_text(min_size=3, max_size=50)),
        'case_type': draw(st.sampled_from([c[0] for c in CaseType.choices])),
        'status': draw(st.sampled_from([c[0] for c in CaseStatus.choices])),
        'fee_mode': fee_mode,
    }
    
    # 根据收费模式添加相应字段
    if fee_mode in [FeeMode.FIXED, FeeMode.SEMI_RISK]:
        data['fixed_amount'] = draw(decimal_amount(min_value=1000, max_value=1000000))
    
    if fee_mode in [FeeMode.SEMI_RISK, FeeMode.FULL_RISK]:
        data['risk_rate'] = draw(decimal_amount(min_value=1, max_value=50, decimal_places=2))
    
    return data


@st.composite
def case_strategy(draw):
    """
    生成案件数据
    
    Returns:
        dict: 案件数据字典
    """
    from apps.cases.models import CaseStatus, CaseStage, SimpleCaseType
    
    return {
        'name': draw(chinese_text(min_size=3, max_size=100)),
        'status': draw(st.sampled_from([c[0] for c in CaseStatus.choices])),
        'cause_of_action': draw(chinese_text(min_size=2, max_size=50)),
        'target_amount': draw(decimal_amount(min_value=1000, max_value=10000000)),
        'case_type': draw(st.sampled_from([c[0] for c in SimpleCaseType.choices])),
        'current_stage': draw(st.sampled_from([c[0] for c in CaseStage.choices])),
    }


@st.composite
def court_document_api_data_strategy(draw):
    """
    生成法院文书 API 数据
    
    Returns:
        dict: 文书 API 数据字典
    """
    from django.utils import timezone
    import random
    
    # 生成文书编号
    c_wsbh = f"WS{draw(st.integers(min_value=100000, max_value=999999))}"
    c_sdbh = f"SD{draw(st.integers(min_value=100000, max_value=999999))}"
    c_stbh = f"ST{draw(st.integers(min_value=100000000, max_value=999999999))}"
    
    # 生成文书名称
    doc_types = ["民事判决书", "刑事判决书", "行政判决书", "民事裁定书", "执行通知书"]
    c_wsmc = draw(st.sampled_from(doc_types))
    
    # 生成法院信息
    c_fybh = f"{draw(st.integers(min_value=100000, max_value=999999))}"
    courts = ["广东省高级人民法院", "广州市中级人民法院", "深圳市中级人民法院", "东莞市第一人民法院"]
    c_fymc = draw(st.sampled_from(courts))
    
    # 生成文件格式
    c_wjgs = draw(st.sampled_from(["pdf", "doc", "docx"]))
    
    # 生成下载链接
    wjlj = f"https://zxfw.court.gov.cn/download/{c_wsbh}.{c_wjgs}"
    
    # 生成创建时间
    dt_cjsj = timezone.now().isoformat()
    
    return {
        'c_sdbh': c_sdbh,
        'c_stbh': c_stbh,
        'wjlj': wjlj,
        'c_wsbh': c_wsbh,
        'c_wsmc': c_wsmc,
        'c_fybh': c_fybh,
        'c_fymc': c_fymc,
        'c_wjgs': c_wjgs,
        'dt_cjsj': dt_cjsj,
    }
