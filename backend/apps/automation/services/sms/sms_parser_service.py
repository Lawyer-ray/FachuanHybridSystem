"""
短信解析服务

负责解析法院短信内容，提取下载链接、案号、当事人等信息
"""
import re
import json
import logging
from typing import List, Optional, TYPE_CHECKING
from dataclasses import dataclass

from apps.automation.utils.text_utils import TextUtils
from apps.automation.services.ai.ollama_client import chat
from apps.automation.models import CourtSMSType
from apps.automation.services.ai import get_ollama_model, get_ollama_base_url

if TYPE_CHECKING:
    from apps.core.interfaces import IClientService

logger = logging.getLogger("apps.automation")


@dataclass
class SMSParseResult:
    """短信解析结果"""
    sms_type: str
    download_links: List[str]
    case_numbers: List[str]
    party_names: List[str]
    has_valid_download_link: bool


class SMSParserService:
    """短信解析服务"""
    
    # 下载链接正则（必须包含 qdbh、sdbh、sdsin 参数）- zxfw.court.gov.cn
    DOWNLOAD_LINK_PATTERN = re.compile(
        r'https://zxfw\.court\.gov\.cn/zxfw/#/pagesAjkj/app/wssd/index\?'
        r'[^\s]*?(?=.*qdbh=[^\s&]+)(?=.*sdbh=[^\s&]+)(?=.*sdsin=[^\s&]+)[^\s]*',
        re.IGNORECASE
    )
    
    # 广东电子送达链接正则 - sd.gdems.com
    # 格式: https://sd.gdems.com/v3/dzsd/xxxxx
    GDEMS_LINK_PATTERN = re.compile(
        r'https://sd\.gdems\.com/v3/dzsd/[a-zA-Z0-9]+',
        re.IGNORECASE
    )
    
    # 当事人提取提示词
    PARTY_EXTRACTION_PROMPT = """
请从以下法院短信中提取所有当事人名称。

规则：
1. 当事人可以是自然人或法人
2. 必须排除以下内容：
   - 法院名称（如：佛山市禅城区人民法院）
   - 法官、书记员、工作人员姓名
   - 系统名称、平台名称
   - 地名、机构名（除非明确是当事人）
   - 问候语中的称呼（如"你好"前的姓名可能是收件人而非当事人）
3. 只提取明确作为案件当事人出现的姓名或公司名
4. 返回 JSON 格式：{"parties": ["当事人1", "当事人2"]}
5. 如果没有找到明确的当事人，返回：{"parties": []}

短信内容：
{content}
"""
    
    def __init__(
        self, 
        ollama_model: str = None, 
        ollama_base_url: Optional[str] = None,
        client_service: Optional["IClientService"] = None
    ):
        """
        初始化SMS解析服务
        
        Args:
            ollama_model: Ollama模型名称，默认从配置文件读取
            ollama_base_url: Ollama服务地址，默认从配置文件读取
            client_service: 客户服务实例，用于依赖注入
        """
        self.ollama_model = ollama_model or get_ollama_model()
        self.ollama_base_url = ollama_base_url or get_ollama_base_url()
        self._client_service = client_service
    
    @property
    def client_service(self) -> "IClientService":
        """延迟加载客户服务"""
        if self._client_service is None:
            from apps.core.interfaces import ServiceLocator
            self._client_service = ServiceLocator.get_client_service()
        return self._client_service
    
    def parse(self, content: str) -> SMSParseResult:
        """
        解析短信内容
        
        Args:
            content: 短信内容
            
        Returns:
            SMSParseResult: 解析结果
        """
        logger.info(f"开始解析短信内容，长度: {len(content)}")
        
        # 提取下载链接
        download_links = self.extract_download_links(content)
        has_valid_download_link = len(download_links) > 0
        
        # 提取案号
        case_numbers = self.extract_case_numbers(content)
        
        # 提取当事人名称
        party_names = self.extract_party_names(content)
        
        # 判定短信类型
        if has_valid_download_link:
            sms_type = CourtSMSType.DOCUMENT_DELIVERY
        else:
            # 简单判断：如果包含"立案"关键词则为立案通知，否则为信息通知
            if "立案" in content:
                sms_type = CourtSMSType.FILING_NOTIFICATION
            else:
                sms_type = CourtSMSType.INFO_NOTIFICATION
        
        result = SMSParseResult(
            sms_type=sms_type,
            download_links=download_links,
            case_numbers=case_numbers,
            party_names=party_names,
            has_valid_download_link=has_valid_download_link
        )
        
        logger.info(f"短信解析完成: 类型={sms_type}, 链接数={len(download_links)}, "
                   f"案号数={len(case_numbers)}, 当事人数={len(party_names)}")
        
        return result
    
    def extract_download_links(self, content: str) -> List[str]:
        """
        提取有效下载链接
        
        支持两种链接格式：
        1. zxfw.court.gov.cn - 法院执行平台
        2. sd.gdems.com - 广东电子送达
        
        Args:
            content: 短信内容
            
        Returns:
            List[str]: 有效下载链接列表
        """
        valid_links = []
        
        # 1. 提取 zxfw.court.gov.cn 链接
        zxfw_matches = self.DOWNLOAD_LINK_PATTERN.findall(content)
        for link in set(zxfw_matches):
            if self._is_valid_download_link(link):
                valid_links.append(link)
        
        # 2. 提取 sd.gdems.com 链接
        gdems_matches = self.GDEMS_LINK_PATTERN.findall(content)
        for link in set(gdems_matches):
            if link not in valid_links:  # 避免重复
                valid_links.append(link)
                logger.info(f"提取到广东电子送达链接: {link}")
        
        if valid_links:
            logger.info(f"提取到 {len(valid_links)} 个有效下载链接")
        else:
            logger.info("未找到有效下载链接")
        
        return valid_links
    
    def _is_valid_download_link(self, link: str) -> bool:
        """
        验证下载链接是否有效
        
        对于 zxfw.court.gov.cn 链接，需要包含必要参数
        对于 sd.gdems.com 链接，只需要格式正确即可
        
        Args:
            link: 链接地址
            
        Returns:
            bool: 是否有效
        """
        # zxfw.court.gov.cn 链接需要包含必要参数
        if "zxfw.court.gov.cn" in link:
            return all(param in link for param in ['qdbh=', 'sdbh=', 'sdsin='])
        
        # sd.gdems.com 链接只需要格式正确
        if "sd.gdems.com" in link:
            return True
        
        return False
    
    def extract_case_numbers(self, content: str) -> List[str]:
        """
        提取案号
        
        Args:
            content: 短信内容
            
        Returns:
            List[str]: 案号列表
        """
        # 复用 TextUtils 的案号提取功能
        case_numbers = TextUtils.extract_case_numbers(content)
        
        if case_numbers:
            logger.info(f"提取到案号: {case_numbers}")
        
        return case_numbers
    
    def extract_party_names(self, content: str) -> List[str]:
        """
        提取当事人名称
        
        新逻辑：
        1. 只在现有客户数据中查找匹配
        2. 如果找不到任何匹配，返回空列表（不使用正则或AI）
        3. 等待文书下载后，再从文书中提取当事人
        
        Args:
            content: 短信内容
            
        Returns:
            List[str]: 当事人名称列表
        """
        # 只在现有客户数据中查找匹配
        existing_parties = self._find_existing_clients_in_sms(content)
        
        if existing_parties:
            logger.info(f"在短信中找到现有客户: {existing_parties}")
            return existing_parties
        
        # 如果在现有客户中找不到匹配，返回空列表
        # 不使用正则或AI提取，因为可能会提取出错误的内容
        # 等待文书下载后，再从文书中提取当事人
        logger.info("在短信中未找到现有客户，返回空列表，等待文书下载后提取当事人")
        return []
    
    def _find_existing_clients_in_sms(self, content: str) -> List[str]:
        """
        第一步：在现有客户数据中查找在短信内容中出现的客户名称
        
        Args:
            content: 短信内容
            
        Returns:
            在短信中找到的现有客户名称列表
        """
        try:
            # 通过客户服务获取所有现有客户
            all_clients = self.client_service.get_all_clients_internal()
            found_parties = []
            
            logger.info(f"开始在短信中查找现有的 {len(all_clients)} 个客户")
            
            # 遍历每个客户，检查其名称是否在短信内容中
            for client in all_clients:
                client_name = client.name.strip()
                
                # 跳过太短的名称（避免误匹配）
                if len(client_name) < 2:
                    continue
                
                # 检查客户名称是否在短信内容中出现
                if client_name in content:
                    found_parties.append(client_name)
                    logger.info(f"在短信中找到现有客户: {client_name}")
            
            if found_parties:
                logger.info(f"总共在短信中找到 {len(found_parties)} 个现有客户: {found_parties}")
            else:
                logger.info("在短信中未找到任何现有客户")
            
            return found_parties
            
        except Exception as e:
            logger.warning(f"查找现有客户时出错: {str(e)}")
            return []

    def _extract_party_names_with_ollama(self, content: str) -> List[str]:
        """
        使用 Ollama 提取当事人名称
        
        Args:
            content: 短信内容
            
        Returns:
            List[str]: 当事人名称列表
        """
        prompt = self.PARTY_EXTRACTION_PROMPT.format(content=content)
        messages = [
            {"role": "user", "content": prompt}
        ]
        
        response = chat(
            model=self.ollama_model,
            messages=messages,
            base_url=self.ollama_base_url
        )
        
        # 解析响应
        if "message" in response and "content" in response["message"]:
            content_text = response["message"]["content"]
            try:
                # 尝试解析JSON
                result = json.loads(content_text)
                if isinstance(result, dict) and "parties" in result:
                    parties = result["parties"]
                    if isinstance(parties, list):
                        logger.info(f"Ollama提取到当事人: {parties}")
                        return parties
            except json.JSONDecodeError:
                logger.warning(f"Ollama返回内容不是有效JSON: {content_text}")
        
        return []
    
    def _extract_party_names_with_regex(self, content: str) -> List[str]:
        """
        使用正则表达式提取当事人名称（降级方案）
        
        Args:
            content: 短信内容
            
        Returns:
            List[str]: 当事人名称列表
        """
        parties = []
        
        # 1. 提取公司名称（精确匹配完整公司名）
        company_patterns = [
            # 匹配完整的公司名称，避免截断
            r'[\u4e00-\u9fa5]{2,30}(?:有限责任公司|股份有限公司)',
            r'[\u4e00-\u9fa5]{2,20}有限公司(?![^\u4e00-\u9fa5])',
            r'[\u4e00-\u9fa5]{2,20}(?:集团|企业)(?![^\u4e00-\u9fa5])',
        ]
        
        for pattern in company_patterns:
            matches = re.findall(pattern, content)
            parties.extend(matches)
        
        # 2. 特殊处理：从"A与B"模式中提取当事人
        # 先处理公司与公司的情况
        company_vs_company = re.findall(
            r'([\u4e00-\u9fa5]{2,30}?(?:有限责任公司|股份有限公司|有限公司|集团|企业))与([\u4e00-\u9fa5]{2,30}?(?:有限责任公司|股份有限公司|有限公司|集团|企业))',
            content
        )
        for match in company_vs_company:
            parties.extend(match)
        
        # 处理公司与个人的情况
        company_vs_person = re.findall(
            r'([\u4e00-\u9fa5]{2,30}?(?:有限责任公司|股份有限公司|有限公司|集团|企业))与([\u4e00-\u9fa5]{2,4}?)(?=\s|财产|合同|纠纷|争议|案|一案)',
            content
        )
        for match in company_vs_person:
            parties.extend(match)
        
        # 处理个人与公司的情况
        person_vs_company = re.findall(
            r'([\u4e00-\u9fa5]{2,4}?)与([\u4e00-\u9fa5]{2,30}?(?:有限责任公司|股份有限公司|有限公司|集团|企业))',
            content
        )
        for match in person_vs_company:
            parties.extend(match)
        
        # 处理个人与个人的情况（需要更严格的上下文）
        person_vs_person_patterns = [
            # 使用非贪婪匹配和更精确的边界
            r'([\u4e00-\u9fa5]{2,4}?)与([\u4e00-\u9fa5]{2,4}?)(?=合同|纠纷|争议|案件)',
            r'([\u4e00-\u9fa5]{2,4}?)诉([\u4e00-\u9fa5]{2,4}?)(?=案件|案)',
            # 特殊处理：收到...与...的案件
            r'收到\s*([\u4e00-\u9fa5]{2,4}?)与([\u4e00-\u9fa5]{2,4}?)的',
            # 关于...诉...案件
            r'关于\s*([\u4e00-\u9fa5]{2,4}?)诉([\u4e00-\u9fa5]{2,4}?)案件',
        ]
        
        for pattern in person_vs_person_patterns:
            matches = re.findall(pattern, content)
            for match in matches:
                if isinstance(match, tuple):
                    parties.extend(match)
                else:
                    parties.append(match)
        
        # 3. 提取个人姓名（在特定上下文中）
        name_contexts = [
            # 明确的当事人角色
            r'(?:当事人|申请人|被申请人|原告|被告|上诉人|被上诉人|申请执行人|被执行人)[：:]\s*([\u4e00-\u9fa5]{2,4})',
            # 案件描述中的姓名
            r'关于\s*([\u4e00-\u9fa5]{2,4})\s*(?:与|诉)',
            r'([\u4e00-\u9fa5]{2,4})\s*诉\s*([\u4e00-\u9fa5]{2,4})',
        ]
        
        for pattern in name_contexts:
            matches = re.findall(pattern, content)
            for match in matches:
                if isinstance(match, tuple):
                    parties.extend(match)
                else:
                    parties.append(match)
        
        # 4. 去重
        parties = list(set(parties))
        
        # 5. 过滤掉明显不是当事人的词汇
        exclude_keywords = [
            # 机构名称
            '法院', '人民法院', '中级法院', '高级法院', '最高法院',
            '政府', '委员会', '管理局', '监督局',
            # 职务人员
            '书记员', '法官', '审判员', '执行员', '助理', '律师',
            # 系统词汇
            '通知', '短信', '系统', '平台', '网站', '服务',
            # 地名（除非明确是公司名的一部分）
            '佛山市', '禅城区', '广东省', '深圳市', '北京市', '上海市',
            # 问候语和动作
            '你好', '收到', '查收', '下载', '链接', '请于', '联系',
            # 文书类型
            '裁定书', '判决书', '通知书', '执行书', '决定书',
            # 其他
            '案件', '号码', '电话', '地址', '时间', '日期',
            '一案', '纠纷', '争议', '合同', '财产', '保全',
            # 常见的非当事人词汇
            '关于', '涉及', '明日', '到庭', '立案', '已立案',
            '的案', '的', '收到'  # 特殊过滤
        ]
        
        filtered_parties = []
        for party in parties:
            if not party or len(party.strip()) == 0:
                continue
                
            party = party.strip()
            
            # 检查是否包含排除关键词
            should_exclude = False
            for keyword in exclude_keywords:
                if keyword in party:
                    should_exclude = True
                    break
            
            # 检查长度合理性
            if not should_exclude and 2 <= len(party) <= 30:
                # 检查是否是纯中文（公司名可能包含数字）
                if re.match(r'^[\u4e00-\u9fa5\d]+$', party):
                    # 额外过滤：避免提取到"有限公司"这样的片段
                    if party not in ['有限公司', '股份有限公司', '有限责任公司', '集团', '企业']:
                        # 避免提取到明显的片段
                        if not (party.endswith('的') or party.startswith('的') or 
                               party.endswith('财') or party.endswith('案')):
                            filtered_parties.append(party)
        
        if filtered_parties:
            logger.info(f"正则提取到当事人: {filtered_parties}")
        else:
            logger.info("正则未提取到有效当事人")
        
        return filtered_parties
    
    def _is_document_delivery_without_parties(self, content: str) -> bool:
        """
        判断是否是文书送达短信（只有案号没有明确当事人）
        
        Args:
            content: 短信内容
            
        Returns:
            bool: 是否是文书送达短信
        """
        # 检查是否包含文书送达的关键词
        delivery_keywords = [
            "请查收", "送达文书", "案件文书", "文书送达", 
            "受理通知书", "缴费通知书", "告知书", "廉政监督卡"
        ]
        
        has_delivery_keywords = any(keyword in content for keyword in delivery_keywords)
        
        # 检查是否有下载链接
        has_download_link = bool(self.DOWNLOAD_LINK_PATTERN.search(content))
        
        # 检查是否有案号
        case_numbers = TextUtils.extract_case_numbers(content)
        has_case_number = len(case_numbers) > 0
        
        # 检查是否缺少明确的当事人信息（没有"与"、"诉"等关键词）
        party_indicators = ["与", "诉", "申请人", "被申请人", "原告", "被告"]
        has_party_indicators = any(indicator in content for indicator in party_indicators)
        
        # 如果有送达关键词、有下载链接、有案号，但没有当事人指示词，则认为是文书送达短信
        is_delivery_sms = (has_delivery_keywords and has_download_link and 
                          has_case_number and not has_party_indicators)
        
        if is_delivery_sms:
            logger.info("识别为文书送达短信，将等待下载文书后提取当事人")
        
        return is_delivery_sms