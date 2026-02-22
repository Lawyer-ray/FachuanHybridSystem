"""
证件信息提取的 Ollama 提示词模板
"""

from apps.client.models import ClientIdentityDoc

# 身份证提示词模板
ID_CARD_PROMPT = """
你是一个专业的身份证信息提取助手.请从给定的身份证OCR文字中提取以下信息,并以JSON格式返回:

需要提取的字段:
- name: 姓名
- id_number: 身份证号码(18位)
- address: 住址
- expiry_date: 有效期至(格式:YYYY-MM-DD,只取最后的到期日期,不要包含起始日期)
- gender: 性别(男/女)
- ethnicity: 民族
- birth_date: 出生日期(格式:YYYY-MM-DD)

注意事项:
1. 如果某个字段无法识别,请设置为 null
2. 日期格式必须是 YYYY-MM-DD
3. 身份证号码必须是18位
4. 有效期可能显示为"2017.03.10-2027.03.10"或"2017-03-10至2027-03-10"等格式,只需要提取最后的到期日期
5. 【重要】如果有效期包含"长期"二字(如"2020.03.22-长期"),expiry_date 必须设置为 "2099-12-31"
6. 返回纯JSON格式,不要包含其他说明文字

示例输出:
```json
{
    "name": "张三",
    "id_number": "110101199001011234",
    "address": "北京市东城区某某街道某某号",
    "expiry_date": "2030-12-31",
    "gender": "男",
    "ethnicity": "汉",
    "birth_date": "1990-01-01"
}
```

长期有效身份证示例输出:
```json
{
    "name": "李四",
    "id_number": "440101198001011234",
    "address": "广东省佛山市禅城区某某街道某某号",
    "expiry_date": "2099-12-31",
    "gender": "男",
    "ethnicity": "汉",
    "birth_date": "1980-01-01"
}
```
"""

# 护照提示词模板
PASSPORT_PROMPT = """
你是一个专业的护照信息提取助手.请从给定的护照OCR文字中提取以下信息,并以JSON格式返回:

需要提取的字段:
- name: 姓名
- passport_number: 护照号码
- nationality: 国籍
- expiry_date: 有效期至(格式:YYYY-MM-DD)
- birth_date: 出生日期(格式:YYYY-MM-DD)

注意事项:
1. 如果某个字段无法识别,请设置为 null
2. 日期格式必须是 YYYY-MM-DD
3. 返回纯JSON格式,不要包含其他说明文字

示例输出:
```json
{
    "name": "ZHANG SAN",
    "passport_number": "E12345678",
    "nationality": "CHN",
    "expiry_date": "2030-12-31",
    "birth_date": "1990-01-01"
}
```
"""

# 港澳通行证提示词模板
HK_MACAO_PERMIT_PROMPT = """
你是一个专业的港澳通行证信息提取助手.请从给定的港澳通行证OCR文字中提取以下信息,并以JSON格式返回:

需要提取的字段:
- name: 姓名
- permit_number: 通行证号码
- expiry_date: 有效期至(格式:YYYY-MM-DD)

注意事项:
1. 如果某个字段无法识别,请设置为 null
2. 日期格式必须是 YYYY-MM-DD
3. 返回纯JSON格式,不要包含其他说明文字

示例输出:
```json
{
    "name": "张三",
    "permit_number": "C12345678",
    "expiry_date": "2030-12-31"
}
```
"""

# 居住证提示词模板
RESIDENCE_PERMIT_PROMPT = """
你是一个专业的居住证信息提取助手.请从给定的居住证OCR文字中提取以下信息,并以JSON格式返回:

需要提取的字段:
- name: 姓名
- id_number: 身份证号码
- address: 居住地址
- expiry_date: 有效期至(格式:YYYY-MM-DD)

注意事项:
1. 如果某个字段无法识别,请设置为 null
2. 日期格式必须是 YYYY-MM-DD
3. 返回纯JSON格式,不要包含其他说明文字

示例输出:
```json
{
    "name": "张三",
    "id_number": "110101199001011234",
    "address": "北京市朝阳区某某街道某某号",
    "expiry_date": "2030-12-31"
}
```
"""

# 户口本提示词模板
HOUSEHOLD_REGISTER_PROMPT = """
你是一个专业的户口本信息提取助手.请从给定的户口本OCR文字中提取以下信息,并以JSON格式返回:

需要提取的字段:
- name: 姓名
- id_number: 身份证号码
- address: 户籍地址
- household_head: 户主姓名

注意事项:
1. 如果某个字段无法识别,请设置为 null
2. 返回纯JSON格式,不要包含其他说明文字

示例输出:
```json
{
    "name": "张三",
    "id_number": "110101199001011234",
    "address": "北京市东城区某某街道某某号",
    "household_head": "张某某"
}
```
"""

# 营业执照提示词模板
BUSINESS_LICENSE_PROMPT = """
你是一个专业的营业执照信息提取助手.请从给定的营业执照OCR文字中提取以下信息,并以JSON格式返回:

需要提取的字段:
- company_name: 企业名称
- credit_code: 统一社会信用代码
- legal_representative: 法定代表人
- address: 住所
- business_scope: 经营范围
- registration_date: 成立日期(格式:YYYY-MM-DD)

注意事项:
1. 如果某个字段无法识别,请设置为 null
2. 日期格式必须是 YYYY-MM-DD
3. 返回纯JSON格式,不要包含其他说明文字

示例输出:
```json
{
    "company_name": "北京某某科技有限公司",
    "credit_code": "91110000123456789X",
    "legal_representative": "张三",
    "address": "北京市朝阳区某某街道某某号",
    "business_scope": "技术开发、技术咨询",
    "registration_date": "2020-01-01"
}
```
"""

# 法定代表人身份证提示词模板(与普通身份证相同)
LEGAL_REP_ID_CARD_PROMPT = ID_CARD_PROMPT


# 提示词映射表
PROMPT_MAPPING: dict[str, str] = {
    ClientIdentityDoc.ID_CARD: ID_CARD_PROMPT,
    ClientIdentityDoc.PASSPORT: PASSPORT_PROMPT,
    ClientIdentityDoc.HK_MACAO_PERMIT: HK_MACAO_PERMIT_PROMPT,
    ClientIdentityDoc.RESIDENCE_PERMIT: RESIDENCE_PERMIT_PROMPT,
    ClientIdentityDoc.HOUSEHOLD_REGISTER: HOUSEHOLD_REGISTER_PROMPT,
    ClientIdentityDoc.BUSINESS_LICENSE: BUSINESS_LICENSE_PROMPT,
    ClientIdentityDoc.LEGAL_REP_ID_CARD: LEGAL_REP_ID_CARD_PROMPT,
}


def get_prompt_for_doc_type(doc_type: str, raw_text: str = "") -> str:
    """
    根据证件类型获取对应的提示词模板

    Args:
        doc_type: 证件类型
        raw_text: OCR 原始文字(可选,用于上下文)

    Returns:
        str: 提示词模板

    Raises:
        ValidationException: 不支持的证件类型
    """
    if doc_type not in PROMPT_MAPPING:
        from apps.core.exceptions import ValidationException
        from django.utils.translation import gettext_lazy as _

        supported_types = list(PROMPT_MAPPING.keys())
        raise ValidationException(
            message=_("不支持的证件类型"),
            code="UNSUPPORTED_DOC_TYPE",
            errors={"doc_type": f"不支持: {doc_type},支持: {supported_types}"},
        )

    return PROMPT_MAPPING[doc_type]


def get_supported_doc_types() -> list[str]:
    """
    获取支持的证件类型列表

    Returns:
        list[str]: 支持的证件类型列表
    """
    return list(PROMPT_MAPPING.keys())
