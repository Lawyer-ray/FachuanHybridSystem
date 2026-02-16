"""
文书解析服务

负责从文书中提取当事人信息
"""
import logging
import os
from typing import Optional, List, TYPE_CHECKING

from apps.core.interfaces import ServiceLocator

if TYPE_CHECKING:
    from apps.core.interfaces import IClientService, ILawyerService

logger = logging.getLogger("apps.automation")


class DocumentParserService:
    """文书解析服务 - 负责从文书中提取当事人信息"""
    
    def __init__(
        self,
        client_service: Optional["IClientService"] = None,
        lawyer_service: Optional["ILawyerService"] = None,
    ):
        """
        初始化文书解析服务
        
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
    
    def extract_parties_from_document(self, document_path: str) -> List[str]:
        """
        从文书中提取当事人名称
        
        处理步骤：
        1. 读取 PDF 内容
        2. 删除换行符
        3. 在现有客户数据库中匹配当事人（不使用 Ollama）
        
        注意：Ollama 只用于提取案号，不用于提取当事人
        
        Args:
            document_path: 文书文件路径
            
        Returns:
            当事人名称列表
        """
        try:
            # 获取文档处理服务
            doc_service = ServiceLocator.get_document_processing_service()
            
            # 读取 PDF 内容（增加限制到 3000 字符以获取更多内容）
            result = doc_service.extract_document_content_by_path_internal(
                document_path, 
                limit=3000
            )
            
            if not result.get("text"):
                logger.warning(f"无法从文书中提取文本: {document_path}")
                return []
            
            # 删除换行符，便于匹配
            content = result["text"].replace("\n", "").replace("\r", "")
            logger.info(
                f"从文书中提取到 {len(result['text'])} 字符的内容，"
                f"删除换行符后为 {len(content)} 字符"
            )
            
            # 在现有客户数据库中匹配当事人（不使用 Ollama）
            return self.match_parties_from_content(content)
            
        except Exception as e:
            logger.error(f"从文书提取当事人失败: {str(e)}")
            return []
    
    def match_parties_from_content(self, content: str) -> List[str]:
        """
        从文书内容中匹配现有客户数据库中的当事人
        
        不使用 Ollama，直接在文书内容中搜索已有客户名称
        
        Args:
            content: 文书内容（已删除换行符）
            
        Returns:
            匹配到的当事人名称列表
        """
        if not content:
            return []
        
        try:
            # 获取所有现有客户
            all_clients = self.client_service.get_all_clients_internal()
            
            # 获取律师姓名用于排除
            lawyer_names = self.get_lawyer_names()
            
            matched_parties = []
            
            logger.info(f"开始在文书内容中匹配 {len(all_clients)} 个现有客户")
            
            for client in all_clients:
                client_name = client.name.strip()
                
                # 排除律师
                if client_name in lawyer_names:
                    continue
                
                # 检查客户名称是否出现在文书内容中
                if len(client_name) >= 2 and client_name in content:
                    matched_parties.append(client_name)
                    logger.info(f"在文书中匹配到客户: {client_name}")
            
            if matched_parties:
                logger.info(
                    f"从文书内容中匹配到 {len(matched_parties)} 个当事人: "
                    f"{matched_parties}"
                )
            else:
                logger.info("从文书内容中未匹配到任何当事人")
            
            return matched_parties
            
        except Exception as e:
            logger.warning(f"从文书内容匹配当事人失败: {str(e)}")
            return []
    
    def get_all_document_paths(self, sms) -> List[str]:
        """
        获取短信关联的所有已下载成功的文书路径
        
        优先从 CourtDocument 记录获取，如果没有记录则尝试从 ScraperTask.result 获取
        （处理文书下载成功但数据库保存失败的情况）
        
        Args:
            sms: CourtSMS 实例
            
        Returns:
            文书路径列表
        """
        document_paths = []
        
        try:
            # 方式1：从 CourtDocument 记录获取
            if sms.scraper_task and hasattr(sms.scraper_task, 'documents'):
                documents = sms.scraper_task.documents.filter(download_status='success')
                for doc in documents:
                    if doc.local_file_path and os.path.exists(doc.local_file_path):
                        document_paths.append(doc.local_file_path)
            
            # 方式2：如果没有从数据库获取到，尝试从任务结果中获取
            if not document_paths and sms.scraper_task:
                result = sms.scraper_task.result
                if result and isinstance(result, dict):
                    files = result.get('files', [])
                    for file_path in files:
                        if file_path and os.path.exists(file_path):
                            document_paths.append(file_path)
                    
                    if files and not document_paths:
                        logger.warning(
                            f"任务结果中有 {len(files)} 个文件路径，但都不存在"
                        )
                        
            logger.info(f"获取到 {len(document_paths)} 个已下载的文书路径")
        except Exception as e:
            logger.warning(f"获取文书路径失败: {str(e)}")
        
        return document_paths
    
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


def _get_document_parser_service() -> DocumentParserService:
    """工厂函数：获取文书解析服务实例"""
    return DocumentParserService()
