"""
案件匹配服务

负责根据案号或当事人匹配案件

匹配优先级：
1. 案号精确匹配：系统中有相同案号 = 同一案件
2. 当事人匹配：案号匹配失败后，从短信/文书提取当事人进行双向严格匹配
3. 类型/阶段筛选：当事人匹配出多个案件时，用案号中的"刑/民/行/执"特征缩小范围
"""
import logging
import re
from typing import Optional, List, TYPE_CHECKING

from apps.core.exceptions import ValidationException
from apps.core.interfaces import ServiceLocator
from apps.automation.utils.text_utils import TextUtils

if TYPE_CHECKING:
    from apps.core.interfaces import ICaseService
    from apps.automation.services.sms.matching import (
        DocumentParserService,
        PartyMatchingService,
    )

logger = logging.getLogger("apps.automation")


class CaseMatcher:
    """案件匹配服务"""
    
    def __init__(
        self,
        case_service: Optional["ICaseService"] = None,
        document_parser_service: Optional["DocumentParserService"] = None,
        party_matching_service: Optional["PartyMatchingService"] = None,
    ):
        self._case_service = case_service
        self._document_parser_service = document_parser_service
        self._party_matching_service = party_matching_service
    
    @property
    def case_service(self) -> "ICaseService":
        if self._case_service is None:
            self._case_service = ServiceLocator.get_case_service()
        return self._case_service
    
    @property
    def document_parser_service(self) -> "DocumentParserService":
        if self._document_parser_service is None:
            from apps.automation.services.sms.matching import DocumentParserService
            self._document_parser_service = DocumentParserService()
        return self._document_parser_service
    
    @property
    def party_matching_service(self) -> "PartyMatchingService":
        if self._party_matching_service is None:
            from apps.automation.services.sms.matching import PartyMatchingService
            self._party_matching_service = PartyMatchingService()
        return self._party_matching_service
    
    def extract_parties_from_document(self, document_path: str) -> list:
        """
        从文书中提取当事人名称（代理方法）
        
        委托给 DocumentParserService 执行实际的提取逻辑
        
        Args:
            document_path: 文书文件路径
            
        Returns:
            当事人名称列表
        """
        return self.document_parser_service.extract_parties_from_document(document_path)
    
    def match(self, sms, document_path: str = None) -> Optional:
        """
        匹配案件
        
        匹配策略（按优先级）：
        1. 案号精确匹配：系统中有相同案号 = 同一案件，直接返回
        2. 当事人匹配：案号匹配失败后，从短信/文书提取当事人进行双向严格匹配
        3. 类型/阶段筛选：当事人匹配出多个案件时，用案号中的"刑/民/行/执"特征缩小范围
        """
        try:
            has_case_numbers = bool(sms.case_numbers)
            
            logger.info(f"开始匹配案件: 案号={sms.case_numbers}, 当事人={sms.party_names}")
            
            # ========== 第一优先级：案号精确匹配 ==========
            # 系统中有相同案号 = 同一案件
            if has_case_numbers:
                case = self._match_by_case_number_exact(sms.case_numbers)
                if case:
                    logger.info(f"通过案号精确匹配到案件: {case.name}")
                    return case
                logger.info("案号精确匹配失败，尝试当事人匹配")
            
            # ========== 第二优先级：当事人匹配 ==========
            # 先从短信提取当事人，失败后从文书提取
            party_names = self._extract_party_names(sms)
            if party_names:
                matched_cases = self._match_by_party_names_all(party_names)
                
                if len(matched_cases) == 1:
                    # 唯一匹配，直接返回
                    case = matched_cases[0]
                    logger.info(f"通过当事人匹配到唯一案件: {case.name}")
                    return case
                
                elif len(matched_cases) > 1:
                    # ========== 第三优先级：类型/阶段筛选 ==========
                    # 当事人匹配出多个案件，用案号特征缩小范围
                    if has_case_numbers:
                        case = self._narrow_down_by_case_number_features(
                            matched_cases, sms.case_numbers
                        )
                        if case:
                            logger.info(f"通过案号特征筛选到案件: {case.name}")
                            return case
                    
                    # 筛选后仍有多个，选择最新的
                    case = self._select_latest_case(matched_cases)
                    logger.info(
                        f"当事人匹配到多个案件（共{len(matched_cases)}个），"
                        f"选择最新的: {case.name}"
                    )
                    return case
            
            # 检查是否有匹配的案件但状态不符合要求
            self._check_and_log_closed_cases(sms)
            
            logger.info("未能匹配到任何在办状态的案件，需要人工处理")
            return None
            
        except Exception as e:
            logger.error(f"案件匹配过程中发生错误: {str(e)}")
            raise ValidationException(
                message=f"案件匹配失败: {str(e)}",
                code="CASE_MATCH_FAILED",
                errors={"error": str(e)}
            )
    
    def _match_by_case_number_exact(self, case_numbers: List[str]) -> Optional:
        """
        第一优先级：案号精确匹配
        
        用案号去系统查找案件，有相同案号说明是同一个案件
        
        匹配策略：
        1. 先查找所有匹配的案件（包括在办和已结案）
        2. 如果只有一个匹配，直接返回
        3. 如果有多个匹配，优先返回在办案件
        4. 如果有多个在办案件，返回 None 由人工决断
        5. 如果没有在办案件但有已结案案件，返回 None（已结案不自动匹配）
        """
        if not case_numbers:
            return None
        
        # 获取所有匹配的案件（包括在办和已结案）
        all_matched_cases = self._get_all_cases_by_numbers(case_numbers)
        
        if not all_matched_cases:
            return None
        
        # 只有一个匹配，检查是否在办
        if len(all_matched_cases) == 1:
            from apps.core.enums import CaseStatus
            case = all_matched_cases[0]
            if case.status == CaseStatus.ACTIVE:
                return case
            else:
                logger.info(f"案号匹配到唯一案件但已结案: {case.name}，需人工处理")
                return None
        
        # 多个匹配，按状态分类
        from apps.core.enums import CaseStatus
        active_cases = [c for c in all_matched_cases if c.status == CaseStatus.ACTIVE]
        closed_cases = [c for c in all_matched_cases if c.status == CaseStatus.CLOSED]
        
        logger.info(
            f"案号匹配到多个案件: 在办 {len(active_cases)} 个, 已结案 {len(closed_cases)} 个"
        )
        
        # 没有在办案件
        if not active_cases:
            logger.info("所有匹配案件均已结案，需人工处理")
            return None
        
        # 只有一个在办案件，直接返回
        if len(active_cases) == 1:
            logger.info(f"多个案件中只有一个在办，自动匹配: {active_cases[0].name}")
            return active_cases[0]
        
        # 多个在办案件，由人工决断
        case_names = [f"{c.name}(ID:{c.id})" for c in active_cases]
        logger.warning(
            f"案号匹配到多个在办案件，需人工决断: {', '.join(case_names)}"
        )
        return None
    
    def _extract_party_names(self, sms) -> List[str]:
        """
        提取当事人名称
        
        优先从短信提取，只有一个当事人视为提取失败，继续从文书提取
        """
        # 1. 先尝试从短信提取（至少需要2个当事人才算有效）
        if sms.party_names and len(sms.party_names) >= 2:
            return sms.party_names
        
        if sms.party_names and len(sms.party_names) == 1:
            logger.debug(f"短信只提取到1个当事人，视为提取失败，尝试从文书提取")
        
        # 2. 从文书提取
        document_paths = self.document_parser_service.get_all_document_paths(sms)
        if document_paths:
            for doc_path in document_paths:
                try:
                    doc_parties = self.document_parser_service.extract_parties_from_document(doc_path)
                    if doc_parties and len(doc_parties) >= 2:
                        logger.info(f"从文书提取到当事人: {doc_parties}")
                        return doc_parties
                except Exception as e:
                    logger.warning(f"从文书提取当事人失败: {doc_path}, 错误: {str(e)}")
                    continue
        
        # 3. 如果文书也提取失败，返回短信中的单个当事人（总比没有好）
        if sms.party_names:
            logger.debug(f"文书提取失败，使用短信中的当事人: {sms.party_names}")
            return sms.party_names
        
        return []
    
    def _match_by_party_names_all(self, party_names: List[str]) -> List:
        """
        第二优先级：当事人匹配，返回所有匹配的案件
        
        使用严格双向匹配：短信当事人 ⊆ 案件当事人 且 案件当事人 ⊆ 短信当事人
        """
        if not party_names:
            return []
        
        # 调试：检查客户数据库
        self.party_matching_service.debug_client_database(party_names)
        
        # 第一步：在现有客户中查找匹配
        matched_clients = self.party_matching_service.find_existing_clients_in_sms(party_names)
        
        if not matched_clients:
            # 第二步：模糊匹配
            matched_clients = self.party_matching_service.extract_and_match_parties_from_sms(party_names)
        
        if not matched_clients:
            return []
        
        return self._find_all_matching_cases(matched_clients)
    
    def _narrow_down_by_case_number_features(
        self, cases: List, case_numbers: List[str]
    ) -> Optional:
        """
        第三优先级：通过案号特征缩小案件范围
        
        当事人匹配出多个案件时，用案号中的"刑/民/行/执/破"特征筛选
        """
        if not cases or not case_numbers:
            return None
        
        # 从案号中提取类型和阶段特征
        case_type = None
        case_stage = None
        is_bankruptcy = False
        
        for case_number in case_numbers:
            if not case_type:
                case_type = self._detect_case_type_from_number(case_number)
            if not case_stage:
                case_stage = self._detect_case_stage_from_number(case_number)
            if not is_bankruptcy:
                is_bankruptcy = self._is_bankruptcy_case_number(case_number)
        
        # 破产案件特殊处理：筛选案件名称包含"破产"的案件
        if is_bankruptcy:
            bankruptcy_filtered = [c for c in cases if '破产' in (c.name or '')]
            if bankruptcy_filtered:
                logger.debug(f"按破产案件筛选后剩余 {len(bankruptcy_filtered)} 个案件")
                if len(bankruptcy_filtered) == 1:
                    return bankruptcy_filtered[0]
                cases = bankruptcy_filtered
        
        if not case_type and not case_stage and not is_bankruptcy:
            return None
        
        filtered = cases
        
        # 按类型筛选
        if case_type:
            type_filtered = [c for c in filtered if c.case_type == case_type]
            if type_filtered:
                filtered = type_filtered
                logger.debug(f"按案件类型 {case_type} 筛选后剩余 {len(filtered)} 个案件")
        
        # 按阶段筛选
        if case_stage:
            stage_filtered = [c for c in filtered if c.current_stage == case_stage]
            if stage_filtered:
                filtered = stage_filtered
                logger.debug(f"按案件阶段 {case_stage} 筛选后剩余 {len(filtered)} 个案件")
        
        if len(filtered) == 1:
            return filtered[0]
        
        return None
    
    def _get_all_cases_by_numbers(self, case_numbers: List[str]) -> List:
        """根据案号列表获取所有匹配的案件（包括在办和已结案）"""
        normalized_numbers = [TextUtils.normalize_case_number(num) for num in case_numbers]
        all_cases = []
        
        for case_number in normalized_numbers:
            try:
                cases = self.case_service.search_cases_by_case_number_internal(case_number)
                all_cases.extend(cases)
            except Exception:
                continue
        
        # 去重
        return list({c.id: c for c in all_cases}.values())
    
    def _get_active_cases_by_numbers(self, case_numbers: List[str]) -> List:
        """根据案号列表获取所有匹配的在办案件"""
        from apps.core.enums import CaseStatus
        
        all_cases = self._get_all_cases_by_numbers(case_numbers)
        return [c for c in all_cases if c.status == CaseStatus.ACTIVE]
    
    def _find_all_matching_cases(self, matched_clients: List) -> List:
        """根据匹配的客户查找所有关联的在办案件（双向严格匹配）"""
        from apps.core.enums import CaseStatus
        
        input_party_names = set(client.name.strip() for client in matched_clients)
        client_names = list(input_party_names)
        
        all_cases = self.case_service.search_cases_by_party_internal(
            client_names, 
            status=CaseStatus.ACTIVE.value
        )
        
        if not all_cases:
            return []
        
        all_cases_dict = {case.id: case for case in all_cases}
        exactly_matched_cases = []
        
        for case_id, case in all_cases_dict.items():
            case_party_names = self.case_service.get_case_party_names_internal(case_id)
            case_party_set = set(name.strip() for name in case_party_names if name)
            
            # 双向匹配检查
            if case_party_set.issubset(input_party_names) and input_party_names.issubset(case_party_set):
                exactly_matched_cases.append(case)
        
        return exactly_matched_cases
    
    
    def _detect_case_type_from_number(self, case_number: str) -> Optional[str]:
        """
        从案号中检测案件类型
        
        案号格式示例：
        - 刑事案件: （2025）粤0605刑初123号、刑终、刑辖
        - 民事案件: （2025）粤0605民初123号、民终、民辖
        - 行政案件: （2025）粤0605行初123号、行终、行辖
        - 破产案件: （2025）粤0605破123号
        
        Returns:
            案件类型枚举值，如 'criminal'、'civil' 等
        """
        from apps.core.enums import CaseType
        
        if not case_number:
            return None
        
        # 刑事案件：包含"刑"字（刑初、刑终、刑辖等）
        if '刑' in case_number:
            logger.debug(f"从案号 {case_number} 检测到刑事案件类型")
            return CaseType.CRIMINAL
        
        # 行政案件：包含"行"字（行初、行终、行辖等）
        # 注意：需要在民事之前检测，因为"行"比"民"更具体
        if '行' in case_number:
            logger.debug(f"从案号 {case_number} 检测到行政案件类型")
            return CaseType.ADMINISTRATIVE
        
        # 民事案件：包含"民"字（民初、民终、民辖等）
        if '民' in case_number:
            logger.debug(f"从案号 {case_number} 检测到民事案件类型")
            return CaseType.CIVIL
        
        # 破产案件：包含"破"字，在 _narrow_down_by_case_number_features 中特殊处理
        if '破' in case_number:
            logger.debug(f"从案号 {case_number} 检测到破产案件")
            return None
        
        return None
    
    def _is_bankruptcy_case_number(self, case_number: str) -> bool:
        """检查案号是否为破产案件"""
        return '破' in case_number if case_number else False
    
    def _detect_case_stage_from_number(self, case_number: str) -> Optional[str]:
        """
        从案号中检测案件阶段类型
        
        案号格式示例：
        - 执行案件: （2025）粤0605执10286号、执恢、执异、执复、执监、执协、执他
        - 执保案件: （2025）粤0605执保123号 (有"执保"，可能不是执行阶段)
        - 民事一审: （2025）粤0605民初123号
        - 民事二审: （2025）粤0605民终123号
        
        Returns:
            案件阶段枚举值，如 'enforcement'、'first_trial' 等
        """
        from apps.core.enums import CaseStage
        
        if not case_number:
            return None
        
        # 执行案件：包含"执"字
        # 执、执恢、执异、执复、执监、执协、执他 都是执行案件
        # "执保"除外，需要用其他条件判断
        if '执' in case_number:
            # "执保"不一定是执行阶段，需要其他条件判断
            if '执保' in case_number:
                logger.debug(f"案号 {case_number} 包含'执保'，不确定是否为执行阶段")
                # 不返回执行阶段，让其他条件判断
            else:
                logger.debug(f"从案号 {case_number} 检测到执行阶段")
                return CaseStage.ENFORCEMENT
        
        # 二审案件：包含"终"字
        if '终' in case_number:
            return CaseStage.SECOND_TRIAL
        
        # 一审案件：包含"初"字
        if '初' in case_number:
            return CaseStage.FIRST_TRIAL
        
        return None
    
    def match_by_case_number(self, case_numbers: List[str]) -> Optional:
        """
        通过案号匹配案件（兼容旧接口）
        
        直接调用精确匹配
        """
        return self._match_by_case_number_exact(case_numbers)
    
    def _select_latest_case(self, cases: List) -> Optional:
        """从案件列表中选择最新的案件（按 ID 降序，ID 越大越新）"""
        if not cases:
            return None
        
        # 按 ID 降序排序（ID 越大表示创建越晚）
        sorted_cases = sorted(cases, key=lambda c: c.id, reverse=True)
        
        selected_case = sorted_cases[0]
        if len(sorted_cases) > 1:
            logger.info(
                f"多个案件匹配（共{len(sorted_cases)}个），"
                f"选择最新的案件: {selected_case.name} "
                f"(ID: {selected_case.id}, 阶段: {selected_case.current_stage})"
            )
        
        return selected_case
    
    def match_by_party_names(self, party_names: List[str]) -> Optional:
        """
        通过当事人名称匹配案件（兼容旧接口）
        
        返回唯一匹配或最新的案件
        """
        matched_cases = self._match_by_party_names_all(party_names)
        
        if not matched_cases:
            return None
        
        if len(matched_cases) == 1:
            return matched_cases[0]
        
        # 多个匹配，选择最新的（ID最大）
        return self._select_latest_case(matched_cases)
    
    def _check_and_log_closed_cases(self, sms) -> None:
        """检查是否有匹配的案件但状态为已结案"""
        from apps.core.enums import CaseStatus
        
        closed_cases = set()
        
        try:
            if sms.case_numbers:
                normalized_numbers = [
                    TextUtils.normalize_case_number(num) for num in sms.case_numbers
                ]
                for case_number in normalized_numbers:
                    try:
                        cases = self.case_service.search_cases_by_case_number_internal(case_number)
                        for case in cases:
                            if case.status == CaseStatus.CLOSED:
                                closed_cases.add(case)
                                logger.warning(f"发现已结案案件（案号匹配）: {case.name}")
                    except Exception:
                        continue
            
            if sms.party_names:
                matched_clients = self.party_matching_service.find_existing_clients_in_sms(
                    sms.party_names
                )
                if matched_clients:
                    client_names = [client.name for client in matched_clients]
                    closed_party_cases = self.case_service.search_cases_by_party_internal(
                        client_names, 
                        status=CaseStatus.CLOSED.value
                    )
                    for case in closed_party_cases:
                        if case not in closed_cases:
                            closed_cases.add(case)
                            logger.warning(f"发现已结案案件（当事人匹配）: {case.name}")
            
            if closed_cases:
                logger.info(f"共发现 {len(closed_cases)} 个已结案案件，等待人工处理")
                
        except Exception as e:
            logger.warning(f"检查已结案案件时发生错误: {str(e)}")


def _get_case_matcher() -> CaseMatcher:
    """工厂函数：获取案件匹配服务实例"""
    return CaseMatcher()
