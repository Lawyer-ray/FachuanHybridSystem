"""Business logic services."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, cast

logger = logging.getLogger(__name__)


class SpecialCaseType:
    """特殊案件类型枚举"""

    PERSONALITY_RIGHTS = "personality_rights"  # 人格权侵权
    IP = "ip"  # 知识产权
    PAYMENT_ORDER = "payment_order"  # 申请支付令
    REVOKE_ARBITRATION = "revoke_arbitration"  # 申请撤销仲裁裁决
    PUBLIC_NOTICE = "public_notice"  # 公示催告程序
    LABOR_DISPUTE = "labor_dispute"  # 劳动争议


# ============================================================================
# 特殊案由编码常量
# ============================================================================

# 基于编码识别的特殊案由
PERSONALITY_RIGHTS_CODE = "9001"  # 人格权纠纷
IP_CONTRACT_CODE = "9300"  # 知识产权合同纠纷
IP_INFRINGEMENT_CODE = "9363"  # 知识产权权属、侵权纠纷

# 特殊案由编码映射
SPECIAL_CAUSE_CODES: dict[str, str] = {
    PERSONALITY_RIGHTS_CODE: SpecialCaseType.PERSONALITY_RIGHTS,
    IP_CONTRACT_CODE: SpecialCaseType.IP,
    IP_INFRINGEMENT_CODE: SpecialCaseType.IP,
}

# ============================================================================
# 特殊案由名称常量
# ============================================================================

# 基于名称识别的特殊案由
PAYMENT_ORDER_NAMES = ["申请支付令", "申请海事支付令"]
REVOKE_ARBITRATION_NAMES = ["申请撤销仲裁裁决"]
PUBLIC_NOTICE_NAMES = ["公示催告程序案件", "申请公示催告"]
LABOR_DISPUTE_NAMES = ["劳动争议"]

# 特殊案由名称映射
SPECIAL_CAUSE_NAMES: dict[str, str] = {}
for name in PAYMENT_ORDER_NAMES:
    SPECIAL_CAUSE_NAMES[name] = SpecialCaseType.PAYMENT_ORDER
for name in REVOKE_ARBITRATION_NAMES:
    SPECIAL_CAUSE_NAMES[name] = SpecialCaseType.REVOKE_ARBITRATION
for name in PUBLIC_NOTICE_NAMES:
    SPECIAL_CAUSE_NAMES[name] = SpecialCaseType.PUBLIC_NOTICE
for name in LABOR_DISPUTE_NAMES:
    SPECIAL_CAUSE_NAMES[name] = SpecialCaseType.LABOR_DISPUTE

# ============================================================================
# 费用配置常量
# ============================================================================

# 固定费用配置
FIXED_FEES: dict[str, Decimal] = {
    SpecialCaseType.REVOKE_ARBITRATION: Decimal("400"),
    SpecialCaseType.PUBLIC_NOTICE: Decimal("100"),
    SpecialCaseType.LABOR_DISPUTE: Decimal("10"),
}

# 费用范围配置
FEE_RANGES: dict[str, dict[str, Decimal]] = {
    SpecialCaseType.PERSONALITY_RIGHTS: {
        "min": Decimal("100"),
        "max": Decimal("500"),
        "half_min": Decimal("50"),
        "half_max": Decimal("250"),
    },
    SpecialCaseType.IP: {
        "min": Decimal("500"),
        "max": Decimal("1000"),
        "half_min": Decimal("250"),
        "half_max": Decimal("500"),
    },
}

# 显示控制配置
DISPLAY_CONFIG: dict[str, dict[str, bool]] = {
    SpecialCaseType.PAYMENT_ORDER: {
        "show_acceptance_fee": True,
        "show_half_fee": True,
        "show_payment_order_fee": True,
    },
    SpecialCaseType.REVOKE_ARBITRATION: {
        "show_acceptance_fee": False,
        "show_half_fee": False,
        "show_payment_order_fee": False,
    },
    SpecialCaseType.PUBLIC_NOTICE: {
        "show_acceptance_fee": False,
        "show_half_fee": False,
        "show_payment_order_fee": False,
    },
    SpecialCaseType.LABOR_DISPUTE: {
        "show_acceptance_fee": False,
        "show_half_fee": False,
        "show_payment_order_fee": False,
    },
}

# 默认显示配置(非支付令案件不显示支付令申请费)
DEFAULT_DISPLAY_CONFIG: dict[str, bool] = {
    "show_acceptance_fee": True,
    "show_half_fee": True,
    "show_payment_order_fee": False,
}


class CauseRuleService:
    """
    案由规则服务

    判断案由类型并返回适用的计算规则.
    通过案由的层级结构(祖先链)识别特殊案件类型.
    """

    def get_ancestor_codes(self, cause_id: int) -> list[str]:
        """
        获取案由的祖先链编码列表

        从当前案由向上遍历到根案由,返回所有案由的编码.
        顺序为从当前案由到根案由.

            cause_id: 案由ID

            List[str]: 祖先链编码列表,从当前案由到根案由

        Requirements: 1.1, 1.2, 1.3
        """
        from .wiring import get_cause_court_query_service

        codes = get_cause_court_query_service().get_cause_ancestor_codes_internal(cause_id)
        logger.info("获取案由祖先链编码", extra={"cause_id": cause_id, "codes": codes})
        return codes

    def get_ancestor_names(self, cause_id: int) -> list[str]:
        """
        获取案由的祖先链名称列表

        从当前案由向上遍历到根案由,返回所有案由的名称.
        顺序为从当前案由到根案由.

            cause_id: 案由ID

            List[str]: 祖先链名称列表,从当前案由到根案由

        Requirements: 1.1, 1.2, 1.3
        """
        from .wiring import get_cause_court_query_service

        names = get_cause_court_query_service().get_cause_ancestor_names_internal(cause_id)
        logger.info("获取案由祖先链名称", extra={"cause_id": cause_id, "names": names})
        return names

    def detect_special_case_type(self, cause_id: int) -> str | None:
        """
        检测案由对应的特殊案件类型

        优先级:
        1. 基于名称匹配(申请支付令、撤销仲裁、公示催告、劳动争议)
        2. 基于编码匹配(人格权、知识产权)

            cause_id: 案由ID

            特殊案件类型字符串,或 None(普通案件)
            - "personality_rights": 人格权侵权案件
            - "ip": 知识产权案件
            - "payment_order": 申请支付令
            - "revoke_arbitration": 申请撤销仲裁裁决
            - "public_notice": 公示催告程序
            - "labor_dispute": 劳动争议

        Requirements: 2.1, 3.1, 4.1, 5.1, 6.1, 7.1
        """
        # 获取祖先链名称和编码
        ancestor_names = self.get_ancestor_names(cause_id)
        ancestor_codes = self.get_ancestor_codes(cause_id)

        if not ancestor_names and not ancestor_codes:
            return None

        # 1. 基于名称匹配(优先级更高,因为这些是精确匹配)
        for name in ancestor_names:
            if name in SPECIAL_CAUSE_NAMES:
                special_type = SPECIAL_CAUSE_NAMES[name]
                logger.info(
                    "检测到特殊案件类型(名称匹配)",
                    extra={"cause_id": cause_id, "matched_name": name, "special_type": special_type},
                )
                return special_type

        # 2. 基于编码匹配
        for code in ancestor_codes:
            if code in SPECIAL_CAUSE_CODES:
                special_type = SPECIAL_CAUSE_CODES[code]
                logger.info(
                    "检测到特殊案件类型(编码匹配)",
                    extra={"cause_id": cause_id, "matched_code": code, "special_type": special_type},
                )
                return special_type

        logger.info("未检测到特殊案件类型", extra={"cause_id": cause_id})
        return None

    def get_fee_rule(self, cause_id: int) -> dict[str, Any]:
        """
        获取案由对应的费用计算规则

        根据案由类型返回相应的费用计算规则配置.

            cause_id: 案由ID

            dict[str, Any]: 费用计算规则配置
            {
                "special_case_type": str | None,      # 特殊案件类型
                "fee_display_text": str | None,       # 特殊费用显示文本
                "fixed_fee": Decimal | None,          # 固定费用
                "fee_range": dict[str, Any]| None,             # 费用范围配置
                "use_property_rule": bool,            # 是否使用财产案件规则
                "show_acceptance_fee": bool,          # 是否显示案件受理费
                "show_half_fee": bool,                # 是否显示减半后受理费
                "show_payment_order_fee": bool,       # 是否显示支付令申请费
            }

        Requirements: 2.1, 3.1, 4.1, 5.1, 6.1, 7.1
        """
        special_type = self.detect_special_case_type(cause_id)

        # 默认规则(普通案件)
        rule: dict[str, Any] = {
            "special_case_type": special_type,
            "fee_display_text": None,
            "fixed_fee": None,
            "fee_range": None,
            "use_property_rule": True,
            **DEFAULT_DISPLAY_CONFIG,
        }

        if not special_type:
            return rule

        # 获取显示配置
        if special_type in DISPLAY_CONFIG:
            rule.update(DISPLAY_CONFIG[special_type])

        # 处理固定费用类型
        if special_type in FIXED_FEES:
            fixed_fee = FIXED_FEES[special_type]
            rule["fixed_fee"] = fixed_fee
            rule["use_property_rule"] = False

            # 生成显示文本
            if special_type == SpecialCaseType.REVOKE_ARBITRATION:
                rule["fee_display_text"] = f"申请撤销仲裁裁决费用:{fixed_fee}元"
            elif special_type == SpecialCaseType.PUBLIC_NOTICE:
                rule["fee_display_text"] = f"申请公示催告费用:{fixed_fee}元"
            elif special_type == SpecialCaseType.LABOR_DISPUTE:
                rule["fee_display_text"] = f"劳动争议:{fixed_fee}元"

        # 处理费用范围类型
        elif special_type in FEE_RANGES:
            fee_range = FEE_RANGES[special_type]
            rule["fee_range"] = fee_range

            # 生成显示文本(无金额时的范围提示)
            if special_type == SpecialCaseType.PERSONALITY_RIGHTS or special_type == SpecialCaseType.IP:
                rule["fee_display_text"] = (
                    f"案件受理费:{fee_range['min']}-{fee_range['max']}元,"
                    f"减半后受理费:{fee_range['half_min']}-{fee_range['half_max']}元"
                )

        # 支付令案件:使用财产案件规则,但显示支付令申请费
        elif special_type == SpecialCaseType.PAYMENT_ORDER:
            rule["use_property_rule"] = True

        logger.info(
            "获取案由费用规则",
            extra={
                "cause_id": cause_id,
                "special_type": special_type,
                "rule": {k: str(v) if isinstance(v, Decimal) else v for k, v in rule.items()},
            },
        )

        return rule
