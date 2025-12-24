"""
文书重命名服务

负责提取文书标题并生成规范的文件名。
"""
import os
import re
import logging
from datetime import date
from pathlib import Path
from typing import Optional

from apps.core.exceptions import ValidationException
from apps.core.config import get_config
from apps.automation.services.document.document_processing import extract_document_content
from apps.automation.services.ai.ollama_client import chat
from apps.automation.services.ai import get_ollama_model, get_ollama_base_url


logger = logging.getLogger(__name__)


class DocumentRenamer:
    """文书重命名服务"""
    
    # 文书标题提取提示词
    DOCUMENT_TITLE_PROMPT = """
请从以下法律文书内容中提取文书主标题。

规则：
1. 主标题通常是：判决书、裁定书、调解书、决定书、传票、通知书等
2. 不要包含案号
3. 只返回标题文字，不要其他内容

文书内容（前500字）：
{content}
"""
    
    def __init__(self, ollama_model: str = None, ollama_base_url: str = None):
        """
        初始化文书重命名服务
        
        Args:
            ollama_model: Ollama模型名称，默认从配置文件读取
            ollama_base_url: Ollama服务地址，默认从配置文件读取
        """
        self.ollama_model = ollama_model or get_ollama_model()
        self.ollama_base_url = ollama_base_url or get_ollama_base_url()
    
    def extract_document_title(self, document_path: str) -> str:
        """
        提取文书主标题
        
        Args:
            document_path: 文书文件路径
            
        Returns:
            str: 提取的主标题
            
        Raises:
            ValidationException: 文件不存在或无法读取
        """
        if not Path(document_path).exists():
            raise ValidationException(f"文书文件不存在: {document_path}")
        
        try:
            # 使用 Document_Processor 读取文书内容
            limit = get_config("validation.text_extraction_limit", 500)
            extraction = extract_document_content(document_path, limit=limit)
            
            if not extraction.text:
                logger.warning(f"无法从文书中提取文本内容: {document_path}")
                return self._extract_title_from_filename(document_path)
            
            # 使用 Ollama 提取标题
            title = self._extract_title_with_ollama(extraction.text)
            
            if title:
                return title
            else:
                logger.warning(f"Ollama 未能提取到标题，使用文件名降级: {document_path}")
                return self._extract_title_from_filename(document_path)
                
        except Exception as e:
            logger.error(f"提取文书标题失败: {document_path}, 错误: {str(e)}")
            # 抛出异常让调用方处理降级逻辑
            raise
    
    def _extract_title_with_ollama(self, content: str) -> Optional[str]:
        """
        使用 Ollama 从文书内容中提取标题
        
        Args:
            content: 文书内容
            
        Returns:
            Optional[str]: 提取的标题，失败时返回 None
        """
        try:
            prompt = self.DOCUMENT_TITLE_PROMPT.format(content=content)
            messages = [
                {"role": "user", "content": prompt}
            ]
            
            response = chat(
                model=self.ollama_model,
                messages=messages,
                base_url=self.ollama_base_url
            )
            
            if response and "message" in response and "content" in response["message"]:
                title = response["message"]["content"].strip()
                
                # 清理提取的标题
                title = self._clean_extracted_title(title)
                
                if title:
                    logger.info(f"成功提取文书标题: {title}")
                    return title
            
            logger.warning("Ollama 返回的响应格式不正确或为空")
            return None
            
        except Exception as e:
            logger.error(f"调用 Ollama 提取标题失败: {str(e)}")
            return None
    
    def _clean_extracted_title(self, title: str) -> str:
        """
        清理从 AI 提取的标题
        
        Args:
            title: 原始标题
            
        Returns:
            str: 清理后的标题
        """
        if not title:
            return ""
        
        # 移除常见的无关内容
        title = title.strip()
        
        # 移除引号
        title = title.strip('"\'""''')
        
        # 移除案号模式（中英文括号内的内容）
        title = re.sub(r'[（(].*?[）)]', '', title)
        
        # 移除多余空格
        title = re.sub(r'\s+', '', title)
        
        # 移除法院名称前缀（各种法院名称模式）
        court_prefixes = [
            r'.*?人民法院',
            r'.*?法院',
            r'.*?仲裁委员会',
            r'.*?仲裁院',
            r'广东',
            r'佛山市',
            r'禅城区',
        ]
        
        for prefix_pattern in court_prefixes:
            title = re.sub(prefix_pattern, '', title)
        
        # 常见的文书类型（按长度排序，优先匹配更具体的类型）
        valid_titles = [
            # 完整的文书名称
            '广东法院诉讼费用交费通知书', '诉讼费用交费通知书', '交费通知书',
            '受理案件通知书', '案件受理通知书', 
            '小额诉讼告知书', '诉讼告知书',
            '诉讼权利义务告知书', '权利义务告知书',
            '诉讼风险告知书', '风险告知书',
            '财产保全裁定书', '执行通知书', '应诉通知书', '举证通知书', 
            '执行裁定书', '仲裁裁决书', '开庭传票', '廉政监督卡',
            '缴费通知书', '受理通知书',
            # 基础类型
            '判决书', '裁定书', '调解书', '决定书', '传票', '通知书', '支付令', '告知书'
        ]
        
        # 检查是否包含有效的文书类型（优先匹配更长的类型）
        for valid_title in valid_titles:
            if valid_title in title:
                return valid_title
        
        # 如果没有匹配到标准类型，尝试提取包含"书"、"通知"、"告知"等关键词的部分
        patterns = [
            r'([^，。]*?通知书)',
            r'([^，。]*?告知书)', 
            r'([^，。]*?裁定书)',
            r'([^，。]*?判决书)',
            r'([^，。]*?调解书)',
            r'([^，。]*?决定书)',
            r'([^，。]*?传票)',
            r'([^，。]*?支付令)',
            r'([^，。]*?监督卡)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, title)
            if match:
                extracted = match.group(1)
                # 再次清理法院名称
                for prefix_pattern in court_prefixes:
                    extracted = re.sub(prefix_pattern, '', extracted)
                if extracted and len(extracted) <= 20:
                    return extracted
        
        # 如果没有匹配到标准类型，返回清理后的原标题
        return title if len(title) <= 20 else title[:20]

    def _extract_title_from_filename(self, document_path: str) -> str:
        """
        从文件名中提取标题（降级方案）
        
        Args:
            document_path: 文件路径
            
        Returns:
            str: 从文件名提取的标题
        """
        filename = Path(document_path).stem
        
        # 移除常见的前缀和后缀
        filename = re.sub(r'^(下载|文书|司法文书)', '', filename)
        filename = re.sub(r'(副本|复件|\d+)$', '', filename)
        
        # 移除法院名称前缀
        court_prefixes = [
            r'.*?人民法院',
            r'.*?法院',
            r'佛山市禅城区',
            r'广东',
            r'佛山市',
            r'禅城区',
        ]
        
        for prefix_pattern in court_prefixes:
            filename = re.sub(prefix_pattern, '', filename)
        
        # 提取文书类型（按长度排序，优先匹配更具体的类型）
        title_patterns = [
            # 完整的文书名称
            r'(广东法院诉讼费用交费通知书|诉讼费用交费通知书|交费通知书)',
            r'(受理案件通知书|案件受理通知书)',
            r'(小额诉讼告知书|诉讼告知书)',
            r'(诉讼权利义务告知书|权利义务告知书)',
            r'(诉讼风险告知书|风险告知书)',
            r'(财产保全裁定书|执行通知书|应诉通知书|举证通知书|执行裁定书|仲裁裁决书|开庭传票|廉政监督卡)',
            r'(缴费通知书|受理通知书)',
            # 基础类型
            r'(判决书|裁定书|调解书|决定书|传票|通知书|支付令|告知书)'
        ]
        
        for pattern in title_patterns:
            match = re.search(pattern, filename)
            if match:
                return match.group(1)
        
        # 如果没有匹配到，尝试提取包含关键词的部分
        fallback_patterns = [
            r'([^，。]*?通知书)',
            r'([^，。]*?告知书)', 
            r'([^，。]*?裁定书)',
            r'([^，。]*?判决书)',
            r'([^，。]*?调解书)',
            r'([^，。]*?决定书)',
            r'([^，。]*?传票)',
            r'([^，。]*?支付令)',
            r'([^，。]*?监督卡)',
        ]
        
        for pattern in fallback_patterns:
            match = re.search(pattern, filename)
            if match:
                extracted = match.group(1)
                # 再次清理法院名称
                for prefix_pattern in court_prefixes:
                    extracted = re.sub(prefix_pattern, '', extracted)
                if extracted and len(extracted) <= 20:
                    return extracted
        
        # 如果没有匹配到，返回默认标题
        return "司法文书"
    
    def generate_filename(
        self, 
        title: str, 
        case_name: str, 
        received_date: date
    ) -> str:
        """
        生成规范文件名
        
        格式：{主标题}（{案件名称}）_{YYYYMMDD}收.pdf
        
        Args:
            title: 文书主标题
            case_name: 案件名称
            received_date: 收到日期
            
        Returns:
            str: 生成的文件名
        """
        if not title:
            title = "司法文书"
        
        if not case_name:
            case_name = "未知案件"
        
        # 清理标题和案件名称中的非法字符
        title = self._sanitize_filename_part(title)
        case_name = self._sanitize_filename_part(case_name)
        
        # 限制长度避免文件名过长
        if len(title) > 20:
            title = title[:20]
        
        if len(case_name) > 30:
            case_name = case_name[:30]
        
        # 格式化日期
        date_str = received_date.strftime("%Y%m%d")
        
        # 生成文件名：使用中文括号
        filename = f"{title}（{case_name}）_{date_str}收.pdf"
        
        return filename
    
    def _sanitize_filename_part(self, text: str) -> str:
        """
        清理文件名部分，移除非法字符
        
        Args:
            text: 原始文本
            
        Returns:
            str: 清理后的文本
        """
        if not text:
            return ""
        
        # 移除或替换文件名中的非法字符
        # Windows 文件名非法字符: < > : " | ? * \ /
        illegal_chars = r'[<>:"|?*\\/]'
        text = re.sub(illegal_chars, '', text)
        
        # 移除英文括号，避免与中文括号混淆
        text = re.sub(r'[()]', '', text)
        
        # 移除控制字符
        text = re.sub(r'[\x00-\x1f\x7f]', '', text)
        
        # 移除首尾空格和点号
        text = text.strip(' .')
        
        return text
    
    def rename(
        self, 
        document_path: str, 
        case_name: str, 
        received_date: date
    ) -> str:
        """
        重命名文书，返回新路径
        
        Args:
            document_path: 原始文书路径
            case_name: 案件名称
            received_date: 收到日期
            
        Returns:
            str: 重命名后的文件路径
            
        Raises:
            ValidationException: 文件操作失败
        """
        if not Path(document_path).exists():
            raise ValidationException(f"文书文件不存在: {document_path}")
        
        try:
            # 提取文书标题
            title = self.extract_document_title(document_path)
            
            # 生成新文件名
            new_filename = self.generate_filename(title, case_name, received_date)
            
            # 构建新文件路径
            original_path = Path(document_path)
            new_path = original_path.parent / new_filename
            
            # 如果新文件名已存在，在"收"字后面添加数字
            counter = 1
            while new_path.exists():
                # 格式：xxx收1.pdf, xxx收2.pdf
                base_filename = new_filename.replace('收.pdf', f'收{counter}.pdf')
                new_path = original_path.parent / base_filename
                counter += 1
                if counter > 100:  # 防止无限循环
                    break
            
            # 重命名文件
            original_path.rename(new_path)
            
            logger.info(f"文书重命名成功: {document_path} -> {new_path}")
            return str(new_path)
            
        except Exception as e:
            logger.error(f"文书重命名失败: {document_path}, 错误: {str(e)}")
            # 抛出异常让调用方处理降级逻辑
            raise
    
    def rename_with_fallback(
        self, 
        document_path: str, 
        case_name: str, 
        received_date: date,
        original_name: str = None
    ) -> str:
        """
        带降级方案的重命名
        
        Args:
            document_path: 原始文书路径
            case_name: 案件名称
            received_date: 收到日期
            original_name: 原始文件名（用于降级）
            
        Returns:
            str: 重命名后的文件路径
        """
        try:
            return self.rename(document_path, case_name, received_date)
        except Exception as e:
            logger.warning(f"重命名失败，使用降级方案: {str(e)}")
            
            # 降级方案：使用原始名称或简单格式
            if original_name:
                fallback_title = self._extract_title_from_filename(original_name)
            else:
                fallback_title = "司法文书"
            
            try:
                fallback_filename = self.generate_filename(
                    fallback_title, 
                    case_name, 
                    received_date
                )
                
                original_path = Path(document_path)
                fallback_path = original_path.parent / fallback_filename
                
                # 避免文件名冲突，在"收"字后面添加数字
                counter = 1
                while fallback_path.exists():
                    base_filename = fallback_filename.replace('收.pdf', f'收{counter}.pdf')
                    fallback_path = original_path.parent / base_filename
                    counter += 1
                    if counter > 100:
                        break
                
                original_path.rename(fallback_path)
                logger.info(f"使用降级方案重命名成功: {document_path} -> {fallback_path}")
                return str(fallback_path)
                
            except Exception as fallback_error:
                logger.error(f"降级方案也失败: {str(fallback_error)}")
                return document_path
