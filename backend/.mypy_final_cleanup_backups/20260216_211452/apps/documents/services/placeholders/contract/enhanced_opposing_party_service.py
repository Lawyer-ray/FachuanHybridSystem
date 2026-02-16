"""
增强版对方当事人占位符服务

根据合同绑定的案件动态生成对方当事人名称、案由与案件数量.
"""
import logging
from typing import Any, ClassVar
from apps.documents.services.placeholders.base import BasePlaceholderService
from apps.documents.services.placeholders.registry import PlaceholderRegistry
logger = logging.getLogger(__name__)

@PlaceholderRegistry.register
class EnhancedOpposingPartyService(BasePlaceholderService):
    """增强版对方当事人服务"""
    name: str = 'enhanced_opposing_party_service'
    display_name: str = '增强版对方当事人服务'
    description: str = '生成对方当事人名称、案由与案件数量'
    category: str = 'contract'
    placeholder_keys: ClassVar = ['对方当事人名称案由与案件数量']

    def generate(self, context_data: dict[str, Any]) -> dict[str, Any]:
        """
        生成增强版对方当事人占位符

        Args:
            context_data: 包含 contract 的上下文字典

        Returns:
            {"对方当事人名称、案由与案件数量": "格式化的字符串"}
        """
        try:
            contract = context_data.get('contract')
            if not contract:
                logger.warning('合同对象为空')
                return {'对方当事人名称案由与案件数量': ''}
            cases = self._get_contract_cases(contract)
            if not cases:
                result = self._format_without_cases(contract)
            else:
                result = self._format_with_cases(contract, cases)
            return {'对方当事人名称案由与案件数量': result}
        except Exception as e:
            logger.warning(f'生成对方当事人占位符失败: {e}', extra={'contract_id': getattr(context_data.get('contract'), 'id', None)}, exc_info=True)
            return {'对方当事人名称案由与案件数量': ''}

    def _get_contract_cases(self, contract: Any) -> list[Any]:
        """
        获取合同关联的案件列表

        Args:
            contract: Contract 实例

        Returns:
            案件列表
        """
        try:
            if not contract:
                return []
            return list(contract.cases.select_related('contract').prefetch_related('parties__client', 'supervising_authorities').all())
        except (AttributeError, Exception) as e:
            logger.warning(f'获取合同案件列表失败: {e}', extra={'contract_id': getattr(contract, 'id', None)})
            return []

    def _format_without_cases(self, contract: Any) -> str:
        """
        格式化无案件情况的输出

        Args:
            contract: Contract 实例

        Returns:
            格式化的字符串
        """
        try:
            opposing_parties: list[Any] = []
            for cp in contract.contract_parties.all():
                if cp.role == 'OPPOSING':
                    opposing_parties.append(cp.client)
            if not opposing_parties:
                return '合同纠纷一案'
            names: list[Any] = []
            for client in opposing_parties:
                if hasattr(client, 'name') and client.name:
                    names.append(client.name)
            opposing_names = '、'.join(names) if names else ''
            return f'{opposing_names}合同纠纷一案'
        except Exception as e:
            logger.warning(f'格式化无案件情况失败: {e}', extra={'contract_id': getattr(contract, 'id', None)})
            return '合同纠纷一案'

    def _format_with_cases(self, contract: Any, cases: list[Any]) -> str:
        """格式化有案件情况的输出"""
        try:
            if not cases:
                return ''
            opposing_client_ids, our_client_ids = self._get_contract_party_ids(contract)
            case_parts: list[Any] = []
            for case in cases:
                part = self._format_single_case(case, opposing_client_ids, our_client_ids)
                if part:
                    case_parts.append(part)
            result = ' | '.join(case_parts) if case_parts else ''
            if result and len(cases) > 0:
                result = f'{result}{self._format_case_count(len(cases))}'
            return result
        except Exception as e:
            logger.warning(f'格式化有案件情况失败: {e}')
            return ''

        def _get_contract_party_ids(contract) -> tuple[set[Any], set[Any]]:
            opposing_ids = set()
        our_ids = set()
        try:
            for cp in contract.contract_parties.all():
                if getattr(cp, 'role', None) == 'OPPOSING':
                    opposing_ids.add(cp.client_id)
                else:
                    our_ids.add(cp.client_id)
        except Exception:
            logger.exception('操作失败')
            pass
        return (opposing_ids, our_ids)

    def _format_single_case(self, case: Any, opposing_client_ids: set[Any], our_client_ids: set[Any]) -> str:
        opposing_parties = self._extract_opposing_parties_from_case(case, opposing_client_ids=opposing_client_ids, our_client_ids=our_client_ids)
        opposing_names = '、'.join(opposing_parties) if opposing_parties else ''
        cause = self._extract_cause_of_action(case)
        if opposing_names and cause:
            return f'{opposing_names}{cause}'
        return opposing_names or cause

    def _extract_opposing_parties_from_case(self, case: Any, *, opposing_client_ids: set[Any], our_client_ids: set[Any]) -> list[str]:
        """
        从案件中提取对方当事人名称列表

        Args:
            case: Case 实例

        Returns:
            对方当事人名称列表
        """
        try:
            opposing_names: list[str] = []
            seen = set()
            for party in case.parties.all():
                client = getattr(party, 'client', None)
                if not client:
                    continue
                if opposing_client_ids and party.client_id in opposing_client_ids:
                    name = getattr(client, 'name', '') or ''
                    if name and name not in seen:
                        seen.add(name)
                        opposing_names.append(name)
                    continue
                if our_client_ids and party.client_id in our_client_ids:
                    continue
                if getattr(client, 'is_our_client', False):
                    continue
                name = getattr(client, 'name', '') or ''
                if name and name not in seen:
                    seen.add(name)
                    opposing_names.append(name)
            return opposing_names
        except Exception:
            logger.exception('extract_case_opposing_parties_failed', extra={'case_id': getattr(case, 'id', None)})
            raise

    def _extract_cause_of_action(self, case: Any) -> Any:
        """
        提取并清理案由(去除ID后缀)

        Args:
            case: Case 实例

        Returns:
            清理后的案由字符串
        """
        try:
            cause = getattr(case, 'cause_of_action', None)
            if not cause:
                return ''
            if '-' in cause:
                return cause.split('-')[0].strip()
            return cause.strip()
        except Exception as e:
            logger.warning(f'提取案由失败: {e}', extra={'case_id': getattr(case, 'id', None)})
            return ''

    def _format_case_count(self, count: int) -> str:
        """
        格式化案件数量(两案、三案等)

        Args:
            count: 案件数量

        Returns:
            中文数字 + "案"
        """
        try:
            chinese_numbers = {1: '一', 2: '两', 3: '三', 4: '四', 5: '五', 6: '六', 7: '七', 8: '八', 9: '九', 10: '十'}
            chinese_num = chinese_numbers.get(count, str(count))
            return f'{chinese_num}案'
        except Exception as e:
            logger.warning(f'格式化案件数量失败: {e}', extra={'count': count})
            return '案'