"""
案由规则服务属性测试

Feature: litigation-fee-cause-rules
测试案由规则服务的正确性属性
"""

from typing import List, Optional

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from apps.cases.services.data.cause_rule_service import (
    IP_CONTRACT_CODE,
    IP_INFRINGEMENT_CODE,
    LABOR_DISPUTE_NAMES,
    PAYMENT_ORDER_NAMES,
    PERSONALITY_RIGHTS_CODE,
    PUBLIC_NOTICE_NAMES,
    REVOKE_ARBITRATION_NAMES,
    SPECIAL_CAUSE_CODES,
    SPECIAL_CAUSE_NAMES,
    CauseRuleService,
    SpecialCaseType,
)


@pytest.fixture
def cause_rule_service():
    """创建 CauseRuleService 实例"""
    return CauseRuleService()


@pytest.mark.django_db
class TestAncestorChainProperties:
    """祖先链查询属性测试"""

    @settings(max_examples=100)
    @given(cause_id=st.integers(min_value=1, max_value=100000))
    def test_property_1_ancestor_chain_correctness(self, cause_id: int):
        """
        Property 1: 祖先链查询正确性

        Feature: litigation-fee-cause-rules, Property 1: 祖先链查询正确性
        Validates: Requirements 1.1, 1.2

        对于任意案由及其父级案由链，get_ancestor_codes(cause_id) 返回的编码列表
        应包含从当前案由到根案由的所有编码，且顺序为从当前案由到根案由。
        """
        from apps.core.models import CauseOfAction

        service = CauseRuleService()

        # 获取祖先链编码
        codes = service.get_ancestor_codes(cause_id)
        names = service.get_ancestor_names(cause_id)

        # 验证编码和名称列表长度一致
        assert len(codes) == len(names), f"编码列表长度 {len(codes)} 与名称列表长度 {len(names)} 不一致"

        # 如果案由存在，验证祖先链正确性
        cause = CauseOfAction.objects.filter(id=cause_id).first()
        if cause:
            # 验证第一个元素是当前案由
            assert codes[0] == cause.code, f"祖先链第一个编码应为当前案由编码 {cause.code}，但得到 {codes[0]}"
            assert names[0] == cause.name, f"祖先链第一个名称应为当前案由名称 {cause.name}，但得到 {names[0]}"

            # 验证祖先链完整性
            expected_codes: list[str] = []
            expected_names: list[str] = []
            current = cause
            while current:
                expected_codes.append(current.code)
                expected_names.append(current.name)
                current = current.parent  # type: ignore[assignment]

            assert codes == expected_codes, f"祖先链编码 {codes} 与预期 {expected_codes} 不符"
            assert names == expected_names, f"祖先链名称 {names} 与预期 {expected_names} 不符"
        else:
            # 案由不存在时应返回空列表
            assert codes == [], f"案由不存在时应返回空列表，但得到 {codes}"
            assert names == [], f"案由不存在时应返回空列表，但得到 {names}"

    def test_ancestor_chain_root_cause(self, cause_rule_service: CauseRuleService):
        """
        测试根案由（无父级）的祖先链

        根案由的祖先链应仅包含自身。
        """
        from apps.core.models import CauseOfAction

        # 查找一个根案由（无父级）
        root_cause = CauseOfAction.objects.filter(parent__isnull=True).first()
        if root_cause:
            codes = cause_rule_service.get_ancestor_codes(root_cause.id)
            assert len(codes) == 1, f"根案由祖先链应只有一个元素，但得到 {len(codes)}"
            assert codes[0] == root_cause.code

    def test_ancestor_chain_multi_level(self, cause_rule_service: CauseRuleService):
        """
        测试多层级案由的祖先链

        多层级案由的祖先链应包含所有层级。
        """
        from apps.core.models import CauseOfAction

        # 查找一个有父级的案由
        child_cause = CauseOfAction.objects.filter(parent__isnull=False).first()
        if child_cause:
            codes = cause_rule_service.get_ancestor_codes(child_cause.id)
            # 至少应有2个元素（自身和父级）
            assert len(codes) >= 2, f"有父级的案由祖先链应至少有2个元素，但得到 {len(codes)}"


@pytest.mark.django_db
class TestCodeBasedDetectionProperties:
    """基于编码的案由类型识别属性测试"""

    @settings(max_examples=100)
    @given(cause_id=st.integers(min_value=1, max_value=100000))
    def test_property_2_code_based_detection(self, cause_id: int):
        """
        Property 2: 基于编码的案由类型识别

        Feature: litigation-fee-cause-rules, Property 2: 基于编码的案由类型识别
        Validates: Requirements 2.1, 3.1

        对于任意案由，如果其祖先链包含编码 9001，则 detect_special_case_type 应返回
        "personality_rights"；如果其祖先链包含编码 9300 或 9363，则应返回 "ip"。
        """
        from apps.core.models import CauseOfAction

        service = CauseRuleService()

        # 获取祖先链编码
        codes = service.get_ancestor_codes(cause_id)
        names = service.get_ancestor_names(cause_id)

        if not codes:
            # 案由不存在，跳过
            return

        # 检测特殊案件类型
        special_type = service.detect_special_case_type(cause_id)

        # 检查是否有名称匹配（名称匹配优先级更高）
        has_name_match = any(name in SPECIAL_CAUSE_NAMES for name in names)

        if has_name_match:
            # 如果有名称匹配，跳过编码检测验证
            return

        # 验证编码匹配
        if PERSONALITY_RIGHTS_CODE in codes:
            assert special_type == SpecialCaseType.PERSONALITY_RIGHTS, (
                f"祖先链包含编码 {PERSONALITY_RIGHTS_CODE}，应识别为人格权案件，但得到 {special_type}"
            )
        elif IP_CONTRACT_CODE in codes or IP_INFRINGEMENT_CODE in codes:
            assert special_type == SpecialCaseType.IP, (
                f"祖先链包含知识产权编码，应识别为知识产权案件，但得到 {special_type}"
            )

    def test_personality_rights_detection(self, cause_rule_service: CauseRuleService):
        """
        测试人格权纠纷案由识别

        编码为 9001 或其子案由应识别为人格权案件。
        """
        from apps.core.models import CauseOfAction

        # 查找人格权纠纷案由
        cause = CauseOfAction.objects.filter(code=PERSONALITY_RIGHTS_CODE).first()
        if cause:
            special_type = cause_rule_service.detect_special_case_type(cause.id)
            assert special_type == SpecialCaseType.PERSONALITY_RIGHTS, (
                f"编码 {PERSONALITY_RIGHTS_CODE} 应识别为人格权案件"
            )

    def test_ip_contract_detection(self, cause_rule_service: CauseRuleService):
        """
        测试知识产权合同纠纷案由识别

        编码为 9300 或其子案由应识别为知识产权案件。
        """
        from apps.core.models import CauseOfAction

        # 查找知识产权合同纠纷案由
        cause = CauseOfAction.objects.filter(code=IP_CONTRACT_CODE).first()
        if cause:
            special_type = cause_rule_service.detect_special_case_type(cause.id)
            assert special_type == SpecialCaseType.IP, f"编码 {IP_CONTRACT_CODE} 应识别为知识产权案件"

    def test_ip_infringement_detection(self, cause_rule_service: CauseRuleService):
        """
        测试知识产权权属、侵权纠纷案由识别

        编码为 9363 或其子案由应识别为知识产权案件。
        """
        from apps.core.models import CauseOfAction

        # 查找知识产权权属、侵权纠纷案由
        cause = CauseOfAction.objects.filter(code=IP_INFRINGEMENT_CODE).first()
        if cause:
            special_type = cause_rule_service.detect_special_case_type(cause.id)
            assert special_type == SpecialCaseType.IP, f"编码 {IP_INFRINGEMENT_CODE} 应识别为知识产权案件"


@pytest.mark.django_db
class TestNameBasedDetectionProperties:
    """基于名称的案由类型识别属性测试"""

    @settings(max_examples=100)
    @given(cause_id=st.integers(min_value=1, max_value=100000))
    def test_property_3_name_based_detection(self, cause_id: int):
        """
        Property 3: 基于名称的案由类型识别

        Feature: litigation-fee-cause-rules, Property 3: 基于名称的案由类型识别
        Validates: Requirements 4.1, 5.1, 6.1, 7.1

        对于任意案由，如果其名称或祖先链中的名称匹配特殊名称列表
        （申请支付令、申请撤销仲裁裁决、公示催告程序案件、劳动争议等），
        则 detect_special_case_type 应返回对应的特殊类型。
        """
        from apps.core.models import CauseOfAction

        service = CauseRuleService()

        # 获取祖先链名称
        names = service.get_ancestor_names(cause_id)

        if not names:
            # 案由不存在，跳过
            return

        # 检测特殊案件类型
        special_type = service.detect_special_case_type(cause_id)

        # 检查名称匹配
        for name in names:
            if name in PAYMENT_ORDER_NAMES:
                assert special_type == SpecialCaseType.PAYMENT_ORDER, (
                    f"名称 {name} 应识别为支付令案件，但得到 {special_type}"
                )
                return
            elif name in REVOKE_ARBITRATION_NAMES:
                assert special_type == SpecialCaseType.REVOKE_ARBITRATION, (
                    f"名称 {name} 应识别为撤销仲裁案件，但得到 {special_type}"
                )
                return
            elif name in PUBLIC_NOTICE_NAMES:
                assert special_type == SpecialCaseType.PUBLIC_NOTICE, (
                    f"名称 {name} 应识别为公示催告案件，但得到 {special_type}"
                )
                return
            elif name in LABOR_DISPUTE_NAMES:
                assert special_type == SpecialCaseType.LABOR_DISPUTE, (
                    f"名称 {name} 应识别为劳动争议案件，但得到 {special_type}"
                )
                return

    def test_payment_order_detection(self, cause_rule_service: CauseRuleService):
        """
        测试申请支付令案由识别

        名称为"申请支付令"或"申请海事支付令"应识别为支付令案件。
        """
        from apps.core.models import CauseOfAction

        for name in PAYMENT_ORDER_NAMES:
            cause = CauseOfAction.objects.filter(name=name).first()
            if cause:
                special_type = cause_rule_service.detect_special_case_type(cause.id)
                assert special_type == SpecialCaseType.PAYMENT_ORDER, f"名称 {name} 应识别为支付令案件"

    def test_revoke_arbitration_detection(self, cause_rule_service: CauseRuleService):
        """
        测试申请撤销仲裁裁决案由识别

        名称为"申请撤销仲裁裁决"应识别为撤销仲裁案件。
        """
        from apps.core.models import CauseOfAction

        for name in REVOKE_ARBITRATION_NAMES:
            cause = CauseOfAction.objects.filter(name=name).first()
            if cause:
                special_type = cause_rule_service.detect_special_case_type(cause.id)
                assert special_type == SpecialCaseType.REVOKE_ARBITRATION, f"名称 {name} 应识别为撤销仲裁案件"

    def test_public_notice_detection(self, cause_rule_service: CauseRuleService):
        """
        测试公示催告程序案由识别

        名称为"公示催告程序案件"或"申请公示催告"应识别为公示催告案件。
        """
        from apps.core.models import CauseOfAction

        for name in PUBLIC_NOTICE_NAMES:
            cause = CauseOfAction.objects.filter(name=name).first()
            if cause:
                special_type = cause_rule_service.detect_special_case_type(cause.id)
                assert special_type == SpecialCaseType.PUBLIC_NOTICE, f"名称 {name} 应识别为公示催告案件"

    def test_labor_dispute_detection(self, cause_rule_service: CauseRuleService):
        """
        测试劳动争议案由识别

        名称包含"劳动争议"应识别为劳动争议案件。
        """
        from apps.core.models import CauseOfAction

        for name in LABOR_DISPUTE_NAMES:
            cause = CauseOfAction.objects.filter(name=name).first()
            if cause:
                special_type = cause_rule_service.detect_special_case_type(cause.id)
                assert special_type == SpecialCaseType.LABOR_DISPUTE, f"名称 {name} 应识别为劳动争议案件"

    def test_normal_case_detection(self, cause_rule_service: CauseRuleService):
        """
        测试普通案由识别

        不匹配任何特殊规则的案由应返回 None。
        """
        from apps.core.models import CauseOfAction

        # 查找一个普通案由（不在特殊编码和名称列表中）
        special_codes = list(SPECIAL_CAUSE_CODES.keys())
        special_names = list(SPECIAL_CAUSE_NAMES.keys())

        # 排除特殊案由
        normal_cause = CauseOfAction.objects.exclude(code__in=special_codes).exclude(name__in=special_names).first()

        if normal_cause:
            # 还需要检查其祖先链是否包含特殊案由
            codes = cause_rule_service.get_ancestor_codes(normal_cause.id)
            names = cause_rule_service.get_ancestor_names(normal_cause.id)

            has_special_code = any(code in special_codes for code in codes)
            has_special_name = any(name in special_names for name in names)

            if not has_special_code and not has_special_name:
                special_type = cause_rule_service.detect_special_case_type(normal_cause.id)
                assert special_type is None, f"普通案由 {normal_cause.name} 应返回 None，但得到 {special_type}"
