"""
管辖权分析引擎

根据合同约定和当事人信息推荐管辖法院
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class JurisdictionParams:
    """管辖权分析参数"""

    has_agreed_jurisdiction: bool
    agreed_court: str
    is_agreed_valid: bool | None
    invalid_reason: str
    plaintiff_location: str
    defendant_location: str


@dataclass(frozen=True)
class JurisdictionResult:
    """管辖权分析结果"""

    has_agreed_jurisdiction: bool
    agreed_court: str
    is_agreed_valid: bool | None
    invalid_reason: str
    plaintiff_location: str
    defendant_location: str
    recommended_court: str
    recommendation_reason: str
    alternative_court: str
    legal_basis: str


class JurisdictionAnalyzerService:
    """管辖权分析服务"""

    def analyze(self, params: JurisdictionParams) -> JurisdictionResult:
        """
        管辖权分析逻辑：

        1. 有约定管辖且有效 → 推荐约定法院
        2. 无约定管辖 → 推荐原告所在地法院（合同履行地）
        3. 约定管辖无效 → 推荐原告所在地法院，说明无效原因
        """
        if params.has_agreed_jurisdiction and params.is_agreed_valid:
            recommended_court = params.agreed_court
            recommendation_reason = "合同中有明确的管辖约定且约定有效，应按约定确定管辖法院"
            legal_basis = (
                "《中华人民共和国民事诉讼法》第三十五条：合同或者其他财产权益纠纷的当事人"
                "可以书面协议选择被告住所地、合同履行地、合同签订地、原告住所地、"
                "标的物所在地等与争议有实际联系的地点的人民法院管辖"
            )
        elif not params.has_agreed_jurisdiction:
            recommended_court = f"{params.plaintiff_location}人民法院"
            recommendation_reason = (
                "合同未约定管辖法院，买卖合同中接收货币一方（原告）所在地为合同履行地，"
                "依据民诉法解释第18条，由合同履行地法院管辖"
            )
            legal_basis = (
                "《最高人民法院关于适用〈中华人民共和国民事诉讼法〉的解释》第18条："
                "合同约定履行地点的，以约定的履行地点为合同履行地。"
                "合同对履行地点没有约定或者约定不明确，争议标的为给付货币的，"
                "接收货币一方所在地为合同履行地"
            )
        else:
            # 约定管辖无效
            recommended_court = f"{params.plaintiff_location}人民法院"
            recommendation_reason = (
                f"合同约定管辖无效（{params.invalid_reason}），按法定管辖，以原告所在地（合同履行地）法院管辖"
            )
            legal_basis = (
                "《中华人民共和国民事诉讼法》第三十五条、"
                "《最高人民法院关于适用〈中华人民共和国民事诉讼法〉的解释》第18条"
            )

        alternative_court = f"{params.defendant_location}人民法院"

        return JurisdictionResult(
            has_agreed_jurisdiction=params.has_agreed_jurisdiction,
            agreed_court=params.agreed_court,
            is_agreed_valid=params.is_agreed_valid,
            invalid_reason=params.invalid_reason,
            plaintiff_location=params.plaintiff_location,
            defendant_location=params.defendant_location,
            recommended_court=recommended_court,
            recommendation_reason=recommendation_reason,
            alternative_court=alternative_court,
            legal_basis=legal_basis,
        )
