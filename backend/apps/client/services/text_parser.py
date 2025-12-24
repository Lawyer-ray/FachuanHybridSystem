import re
from typing import Dict, List, Optional


def parse_client_text(text: str) -> Dict:
    """
    解析当事人文本信息
    
    支持格式：
    1. 答辩人（被申请人）：广东XX有限公司
    2. 原告：广东XXX公司
    3. 被告：徐X，男，汉族，1977年9月10日出生
    
    Args:
        text: 待解析的文本
        
    Returns:
        解析后的客户数据字典
    """
    if not text or not text.strip():
        return _empty_result()
    
    # 清理文本
    text = text.strip()
    
    # 尝试解析多个当事人
    parties = _extract_parties(text)
    
    if not parties:
        return _empty_result()
    
    # 返回第一个当事人的信息（如果有多个，用户可以选择）
    return parties[0]


def parse_multiple_clients_text(text: str) -> List[Dict]:
    """
    解析包含多个当事人的文本
    
    Args:
        text: 待解析的文本
        
    Returns:
        解析后的客户数据列表
    """
    if not text or not text.strip():
        return []
    
    return _extract_parties(text.strip())


def _extract_parties(text: str) -> List[Dict]:
    """提取所有当事人信息"""
    parties = []
    
    # 定义角色标签模式
    role_patterns = [
        r"答辩人\s*（[^）]*）\s*[:：]",
        r"被答辩人\s*（[^）]*）\s*[:：]",
        r"申请人\s*（[^）]*）\s*[:：]",
        r"被申请人\s*（[^）]*）\s*[:：]",
        r"原告\s*[:：]",
        r"被告\s*[:：]",
        r"上诉人\s*[:：]",
        r"被上诉人\s*[:：]",
        r"第三人\s*[:：]",
        r"申请人\s*[:：]",
        r"被申请人\s*[:：]",
        r"答辩人\s*[:：]",
        r"被答辩人\s*[:：]",
    ]
    
    # 找到所有角色标签的位置
    all_matches = []
    for pattern in role_patterns:
        matches = list(re.finditer(pattern, text, re.IGNORECASE))
        all_matches.extend(matches)
    
    # 按位置排序
    all_matches.sort(key=lambda x: x.start())
    
    # 提取每个当事人的信息
    for i, match in enumerate(all_matches):
        start_pos = match.end()
        
        # 确定当事人信息的结束位置
        if i + 1 < len(all_matches):
            end_pos = all_matches[i + 1].start()
        else:
            end_pos = len(text)
        
        # 提取当事人信息段落
        party_text = text[start_pos:end_pos].strip()
        
        if party_text:
            # 重新构造完整的当事人信息（包含角色标签）
            role_label = text[match.start():match.end()]
            full_party_text = role_label + party_text
            
            party_info = _parse_single_party(full_party_text)
            if party_info["name"]:  # 只有名称不为空才添加
                parties.append(party_info)
    
    # 如果没有找到角色标签，尝试直接解析
    if not parties:
        party_info = _parse_single_party(text)
        if party_info["name"]:
            parties.append(party_info)
    
    return parties


def _parse_single_party(text: str) -> Dict:
    """解析单个当事人信息"""
    result = _empty_result()
    
    # 提取名称（第一行或第一个非标签内容）
    name = _extract_name(text)
    if name:
        result["name"] = name
        result["client_type"] = _determine_client_type(name, text)
    
    # 提取统一社会信用代码
    credit_code = _extract_credit_code(text)
    if credit_code:
        result["id_number"] = credit_code
        result["client_type"] = "legal"  # 有统一社会信用代码的是法人
    
    # 提取身份证号码
    if not result["id_number"]:
        id_number = _extract_id_number(text)
        if id_number:
            result["id_number"] = id_number
            result["client_type"] = "natural"  # 有身份证号的是自然人
    
    # 提取地址
    address = _extract_address(text)
    if address:
        result["address"] = address
    
    # 提取电话
    phone = _extract_phone(text)
    if phone:
        result["phone"] = phone
    
    # 提取法定代表人
    legal_rep = _extract_legal_representative(text)
    if legal_rep:
        result["legal_representative"] = legal_rep
        if result["client_type"] == "natural":
            result["client_type"] = "legal"  # 有法定代表人的是法人
    
    return result


def _extract_name(text: str) -> Optional[str]:
    """提取名称"""
    # 定义角色标签模式
    role_patterns = [
        r'答辩人\s*（[^）]*）\s*[:：]\s*([^\n]+)',
        r'被答辩人\s*（[^）]*）\s*[:：]\s*([^\n]+)',
        r'申请人\s*（[^）]*）\s*[:：]\s*([^\n]+)',
        r'被申请人\s*（[^）]*）\s*[:：]\s*([^\n]+)',
        r'原告\s*[:：]\s*([^\n]+)',
        r'被告\s*[:：]\s*([^\n]+)',
        r'上诉人\s*[:：]\s*([^\n]+)',
        r'被上诉人\s*[:：]\s*([^\n]+)',
        r'第三人\s*[:：]\s*([^\n]+)',
        r'申请人\s*[:：]\s*([^\n]+)',
        r'被申请人\s*[:：]\s*([^\n]+)',
        r'答辩人\s*[:：]\s*([^\n]+)',
        r'被答辩人\s*[:：]\s*([^\n]+)',
    ]
    
    for pattern in role_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            name_part = match.group(1).strip()
            
            # 去除性别、民族、出生日期等个人信息
            name = re.sub(r'[，,]\s*(男|女|汉族|回族|满族|蒙古族|维吾尔族|藏族|壮族|朝鲜族|苗族|瑶族|土家族|布依族|侗族|白族|哈尼族|哈萨克族|黎族|傣族|畲族|傈僳族|仡佬族|东乡族|高山族|拉祜族|水族|佤族|纳西族|羌族|土族|仫佬族|锡伯族|柯尔克孜族|达斡尔族|景颇族|毛南族|撒拉族|布朗族|塔吉克族|阿昌族|普米族|鄂温克族|怒族|京族|基诺族|德昂族|保安族|俄罗斯族|裕固族|乌孜别克族|门巴族|鄂伦春族|独龙族|塔塔尔族|赫哲族|珞巴族).*', '', name_part)
            name = re.sub(r'[，,]\s*\d{4}年\d{1,2}月\d{1,2}日.*', '', name)
            
            if name.strip():
                return name.strip()
    
    return None


def _extract_credit_code(text: str) -> Optional[str]:
    """提取统一社会信用代码"""
    patterns = [
        r'统一社会信用代码\s*[:：]\s*([A-Z0-9]{18})',
        r'信用代码\s*[:：]\s*([A-Z0-9]{18})',
        r'社会信用代码\s*[:：]\s*([A-Z0-9]{18})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    
    return None


def _extract_id_number(text: str) -> Optional[str]:
    """提取身份证号码"""
    patterns = [
        r'身份证号码\s*[:：]\s*([0-9X]{15,18})',
        r'身份证号\s*[:：]\s*([0-9X]{15,18})',
        r'身份证\s*[:：]\s*([0-9X]{15,18})',
        r'证件号码\s*[:：]\s*([0-9X]{15,18})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    
    return None


def _extract_address(text: str) -> Optional[str]:
    """提取地址"""
    patterns = [
        r'地址\s*[:：]\s*([^\n]*?)(?=\n|$)',
        r'住址\s*[:：]\s*([^\n]*?)(?=\n|$)',
        r'住所地\s*[:：]\s*([^\n]*?)(?=\n|$)',
        r'住所\s*[:：]\s*([^\n]*?)(?=\n|$)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            address = match.group(1).strip()
            # 去除括号内的备注
            address = re.sub(r'（[^）]*）', '', address)
            address = re.sub(r'\([^)]*\)', '', address)
            return address.strip() if address.strip() else None
    
    return None


def _extract_phone(text: str) -> Optional[str]:
    """提取电话号码"""
    patterns = [
        r'联系电话\s*[:：]\s*([0-9\-\+\s]{7,20})',
        r'电话\s*[:：]\s*([0-9\-\+\s]{7,20})',
        r'联系方式\s*[:：]\s*([0-9\-\+\s]{7,20})',
        r'手机\s*[:：]\s*([0-9\-\+\s]{7,20})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            phone = match.group(1).strip()
            # 清理电话号码格式
            phone = re.sub(r'\s+', '', phone)
            return phone if phone else None
    
    return None


def _extract_legal_representative(text: str) -> Optional[str]:
    """提取法定代表人"""
    patterns = [
        r'法定代表人\s*[:：]\s*([^\n]*?)(?=\n|$)',
        r'法人代表\s*[:：]\s*([^\n]*?)(?=\n|$)',
        r'负责人\s*[:：]\s*([^\n]*?)(?=\n|$)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            legal_rep = match.group(1).strip()
            return legal_rep if legal_rep else None
    
    return None


def _determine_client_type(name: str, text: str) -> str:
    """根据名称和文本内容判断客户类型"""
    # 检查是否有统一社会信用代码
    if _extract_credit_code(text):
        return "legal"
    
    # 检查是否有法定代表人
    if _extract_legal_representative(text):
        return "legal"
    
    # 检查名称特征
    legal_keywords = [
        "有限公司", "股份公司", "集团", "企业", "厂", "店", "中心", 
        "协会", "基金会", "研究院", "学校", "医院", "银行"
    ]
    
    for keyword in legal_keywords:
        if keyword in name:
            return "legal"
    
    # 检查是否有身份证号
    if _extract_id_number(text):
        return "natural"
    
    # 默认为自然人
    return "natural"


def _empty_result() -> Dict:
    """返回空的解析结果"""
    return {
        "name": "",
        "phone": "",
        "address": "",
        "client_type": "natural",
        "id_number": "",
        "legal_representative": "",
    }
