"""金诚同达 OA 立案脚本 —— 数据模型。"""

from __future__ import annotations

from dataclasses import dataclass


def _gender_from_id_number(id_number: str) -> str:
    """从身份证号码推断性别。

    18位身份证第17位：奇数=男，偶数=女。

    Returns:
        "01" 男 / "02" 女，无法判断时返回 "01"。
    """
    if len(id_number) == 18 and id_number[:17].isdigit():
        return "01" if int(id_number[16]) % 2 == 1 else "02"
    return "01"


@dataclass
class ClientInfo:
    """委托方信息。"""

    name: str
    client_type: str  # natural / legal / non_legal_org
    id_number: str | None = None
    address: str | None = None
    phone: str | None = None
    legal_representative: str | None = None


@dataclass
class ConflictPartyInfo:
    """利益冲突方信息。"""

    name: str
    category: str = "11"  # 11=对方当事人
    legal_position: str = "02"  # 01=原告 02=被告 09=第三人（对方诉讼地位）
    customer_type: str = "01"  # 01=企业 11=自然人
    is_payer: str = "0"  # 0=否 1=是
    id_number: str | None = None
    contact_name: str | None = None
    contact_phone: str | None = None


@dataclass
class CaseInfo:
    """案件信息。"""

    manager_id: str  # 案件负责人 empid（可为空）
    manager_name: str  # 案件负责人姓名（按名字匹配 option）
    category: str  # 案件类型: 01~06
    stage: str  # 案件阶段: 0301 等
    which_side: str  # 代理何方: 01=原告 02=被告
    kindtype: str  # 业务类型一级
    kindtype_sed: str  # 业务类型二级
    kindtype_thr: str  # 业务类型三级
    case_name: str  # 案件名称（填合同名称）
    case_desc: str = ""  # 案情简介（填合同名称）
    resource: str = "01"  # 案源: 01=主动开拓
    language: str = "01"  # 语言: 01=中文
    is_foreign: str = "N"
    is_help: str = "N"
    is_publicgood: str = "0"
    is_factory: str = "N"
    is_secret: str = "N"
    isunion: str = "0"
    isforeigncoop: str = "0"
    start_date: str = ""  # 收案日期 yyyy-MM-dd（必填，空则取当天）
    contact_name: str = "/"  # 客户联系人姓名
    contact_phone: str = "/"  # 客户联系人电话


@dataclass
class ContractInfo:
    """委托合同信息。"""

    rec_type: str = "01"  # 收费方式: 01=定额 02=按标的比例 03=按小时
    currency: str = "RMB"
    contract_type: str = "30"  # 30=书面合同
    is_free: str = "N"
    start_date: str = ""
    end_date: str = ""
    amount: str = ""
    stamp_count: int = 3  # 预盖章份数，默认 3（1人+2）


@dataclass
class FilingFormState:
    """立案表单状态。"""

    action_url: str
    payload: dict[str, str]
    html_text: str


@dataclass
class ResolvedCustomer:
    """已匹配的 OA 客户。"""

    customer_id: str
    customer_name: str
    istemp: str = "Z"
