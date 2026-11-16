"""证件类型自动判型（纯函数，基于 OCR 文本关键词与特征）。"""

from __future__ import annotations

import logging
import re

from apps.client.models import ClientIdentityDoc

from .prompts import PROMPT_MAPPING
from .text_cleaning import _prepare_text_for_llm

logger = logging.getLogger(__name__)

_BUSINESS_TOKENS = (
    "营业执照",
    "统一社会信用代码",
    "企业名称",
    "法定代表人",
    "注册资本",
    "成立日期",
    "营业期限",
    "经营范围",
    "住所",
    "类型",
    "business license",
    "credit code",
)
_ID_CARD_TOKENS = ("公民身份号码", "居民身份证", "姓名", "性别", "民族", "住址", "出生")


def _resolve_doc_type(doc_type: str, raw_text: str, source_name: str | None = None) -> str:
    requested = (doc_type or "").strip()
    if requested and requested != "auto" and requested in PROMPT_MAPPING:
        return requested

    if requested and requested not in {"auto", *PROMPT_MAPPING.keys()}:
        logger.warning("收到不支持的证件类型，已自动降级判型: doc_type=%s", requested)

    text = _prepare_text_for_llm(raw_text)
    normalized = text.lower()
    source = (source_name or "").lower()

    def has_any(tokens: tuple[str, ...]) -> bool:
        return any(token in text or token in normalized or token in source for token in tokens)

    business_score = sum(1 for token in _BUSINESS_TOKENS if token in text or token in normalized or token in source)
    id_score = sum(1 for token in _ID_CARD_TOKENS if token in text)

    credit_code_match = re.search(r"(?<![0-9A-Z])([0-9A-Z]{18})(?![0-9A-Z])", text.upper())
    if credit_code_match:
        credit_code = credit_code_match.group(1)
        has_alpha = any(ch.isalpha() for ch in credit_code)
        if has_alpha or business_score >= 1:
            logger.info(
                "证件自动判型命中统一社会信用代码特征: requested_doc_type=%s, resolved_doc_type=%s, business_score=%s, id_score=%s",
                requested or "auto",
                ClientIdentityDoc.BUSINESS_LICENSE,
                business_score,
                id_score,
            )
            return str(ClientIdentityDoc.BUSINESS_LICENSE)

    if business_score >= 2 and business_score >= id_score + 1:
        logger.info(
            "证件自动判型命中营业执照关键词: requested_doc_type=%s, resolved_doc_type=%s, business_score=%s, id_score=%s",
            requested or "auto",
            ClientIdentityDoc.BUSINESS_LICENSE,
            business_score,
            id_score,
        )
        return str(ClientIdentityDoc.BUSINESS_LICENSE)

    if has_any(("passport", "护照", "nationality", "passport no", "issuing country")):
        return str(ClientIdentityDoc.PASSPORT)

    if has_any(("港澳", "通行证", "往来港澳", "hk", "macao")):
        return str(ClientIdentityDoc.HK_MACAO_PERMIT)

    if has_any(("户口本", "常住人口登记", "户主", "与户主关系")):
        return str(ClientIdentityDoc.HOUSEHOLD_REGISTER)

    if has_any(("居住证", "residence permit")):
        return str(ClientIdentityDoc.RESIDENCE_PERMIT)

    if has_any(("法定代表人", "负责人", "法人身份证")) and re.search(r"(?<!\d)\d{17}[\dXx](?!\d)", text):
        return str(ClientIdentityDoc.LEGAL_REP_ID_CARD)

    logger.info(
        "证件自动判型回退身份证: requested_doc_type=%s, resolved_doc_type=%s, business_score=%s, id_score=%s",
        requested or "auto",
        ClientIdentityDoc.ID_CARD,
        business_score,
        id_score,
    )
    return str(ClientIdentityDoc.ID_CARD)
