"""
当事人匹配服务

负责在现有客户数据库中匹配当事人
"""
import logging
from typing import Optional, List, TYPE_CHECKING

from apps.core.interfaces import ServiceLocator

if TYPE_CHECKING:
    from apps.core.interfaces import IClientService, ILawyerService

logger = logging.getLogger("apps.automation")


class PartyMatchingService:
    """当事人匹配服务 - 负责在现有客户数据库中匹配当事人"""
    
    def __init__(
        self,
        client_service: Optional["IClientService"] = None,
        lawyer_service: Optional["ILawyerService"] = None,
    ):
        """
        初始化当事人匹配服务
        
        Args:
            client_service: 客户服务实例（可选，用于依赖注入）
            lawyer_service: 律师服务实例（可选，用于依赖注入）
        """
        self._client_service = client_service
        self._lawyer_service = lawyer_service
    
    @property
    def client_service(self) -> "IClientService":
        """延迟加载客户服务"""
        if self._client_service is None:
            self._client_service = ServiceLocator.get_client_service()
        return self._client_service
    
    @property
    def lawyer_service(self) -> "ILawyerService":
        """延迟加载律师服务"""
        if self._lawyer_service is None:
            self._lawyer_service = ServiceLocator.get_lawyer_service()
        return self._lawyer_service
    
    def find_existing_clients_in_sms(self, party_names: List[str]) -> List:
        """
        在现有客户数据中查找与短信内容匹配的当事人
        
        注意：只检索 Client 表中的真正客户，排除律师等非客户人员
        
        Args:
            party_names: 从短信中提取的当事人名称列表
            
        Returns:
            匹配的 Client 对象列表
        """
        if not party_names:
            return []
        
        matched_clients = []
        
        # 通过客户服务获取所有现有客户
        all_clients = self.client_service.get_all_clients_internal()
        
        # 获取所有律师姓名，用于排除匹配
        lawyer_names = self.get_lawyer_names()
        
        logger.info(f"开始在 {len(all_clients)} 个现有客户中查找匹配")
        logger.info(f"将排除 {len(lawyer_names)} 个律师姓名: {lawyer_names}")
        
        # 遍历每个客户，检查其名称是否在短信提取的当事人中
        for client in all_clients:
            client_name = client.name.strip()
            
            # 排除律师：如果客户姓名与律师姓名匹配，跳过
            if client_name in lawyer_names:
                logger.info(f"跳过律师: {client_name}")
                continue
            
            # 检查客户名称是否与短信中提取的当事人名称匹配
            for party_name in party_names:
                party_name = party_name.strip()
                
                # 排除律师：如果当事人姓名是律师，跳过
                if party_name in lawyer_names:
                    logger.info(f"跳过律师当事人: {party_name}")
                    continue
                
                # 精确匹配
                if client_name == party_name:
                    matched_clients.append(client)
                    logger.info(f"精确匹配找到客户: {client_name}")
                    break
                
                # 包含匹配（客户名称包含在当事人名称中，或反之）
                elif (len(client_name) >= 2 and client_name in party_name) or \
                     (len(party_name) >= 2 and party_name in client_name):
                    matched_clients.append(client)
                    logger.info(f"包含匹配找到客户: {client_name} <-> {party_name}")
                    break
        
        # 去重（基于客户ID）
        matched_clients = self._deduplicate_clients(matched_clients)
        
        if matched_clients:
            logger.info(
                f"在现有客户中找到 {len(matched_clients)} 个匹配: "
                f"{[c.name for c in matched_clients]}"
            )
        else:
            logger.info("在现有客户中未找到匹配")
        
        return matched_clients
    
    def extract_and_match_parties_from_sms(self, party_names: List[str]) -> List:
        """
        使用模糊匹配逻辑查找当事人
        
        Args:
            party_names: 从短信中提取的当事人名称列表
            
        Returns:
            匹配的 Client 对象列表
        """
        if not party_names:
            return []
        
        matched_clients = []
        
        # 获取律师姓名用于排除
        lawyer_names = self.get_lawyer_names()
        
        # 使用客户服务进行模糊匹配
        for party_name in party_names:
            party_name = party_name.strip()
            
            # 排除律师姓名
            if party_name in lawyer_names:
                logger.info(f"跳过律师当事人: {party_name}")
                continue
            
            if len(party_name) >= 2:  # 至少2个字符才进行匹配
                clients = self.client_service.search_clients_by_name_internal(
                    party_name, 
                    exact_match=False
                )
                
                # 进一步过滤掉可能是律师的客户记录
                filtered_clients = []
                for client in clients:
                    if client.name.strip() not in lawyer_names:
                        filtered_clients.append(client)
                    else:
                        logger.info(f"过滤掉律师客户记录: {client.name}")
                
                matched_clients.extend(filtered_clients)
                if filtered_clients:
                    logger.info(
                        f"模糊匹配找到客户: {party_name} -> "
                        f"{[c.name for c in filtered_clients]}"
                    )
        
        # 去重（基于客户ID）
        matched_clients = self._deduplicate_clients(matched_clients)
        
        if matched_clients:
            logger.info(
                f"模糊匹配找到 {len(matched_clients)} 个客户: "
                f"{[c.name for c in matched_clients]}"
            )
        
        return matched_clients
    
    def get_lawyer_names(self) -> List[str]:
        """
        获取所有律师姓名，用于排除匹配
        
        Returns:
            律师姓名列表
        """
        try:
            # 通过律师服务获取所有律师姓名
            lawyer_names = self.lawyer_service.get_all_lawyer_names_internal()
            
            logger.info(f"获取到 {len(lawyer_names)} 个律师姓名: {lawyer_names}")
            return lawyer_names
            
        except Exception as e:
            logger.warning(f"获取律师姓名失败: {str(e)}")
            # 如果获取失败，返回空列表，不影响主流程
            return []
    
    def debug_client_database(self, party_names: List[str]) -> None:
        """
        调试方法：检查客户数据库中是否有相关记录
        
        Args:
            party_names: 当事人名称列表
        """
        try:
            # 获取所有客户
            all_clients = self.client_service.get_all_clients_internal()
            logger.info(f"客户数据库总数: {len(all_clients)}")
            
            # 检查是否有包含关键词的客户
            for party_name in party_names:
                matching_clients = []
                for client in all_clients:
                    if party_name in client.name or client.name in party_name:
                        matching_clients.append(client.name)
                
                if matching_clients:
                    logger.info(
                        f"当事人 '{party_name}' 在客户库中找到相似记录: "
                        f"{matching_clients}"
                    )
                else:
                    logger.info(
                        f"当事人 '{party_name}' 在客户库中未找到相似记录"
                    )
                    
        except Exception as e:
            logger.warning(f"调试客户数据库失败: {str(e)}")
    
    def _deduplicate_clients(self, clients: List) -> List:
        """
        去重客户列表（基于客户ID）
        
        Args:
            clients: 客户对象列表
            
        Returns:
            去重后的客户对象列表
        """
        seen_ids = set()
        unique_clients = []
        for client in clients:
            if client.id not in seen_ids:
                unique_clients.append(client)
                seen_ids.add(client.id)
        return unique_clients


def _get_party_matching_service() -> PartyMatchingService:
    """工厂函数：获取当事人匹配服务实例"""
    return PartyMatchingService()
