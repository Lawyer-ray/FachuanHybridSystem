"""
群聊名称配置服务

本模块提供群聊名称相关配置的读取和模板渲染功能。
通过 SystemConfig 模型读取配置，支持缓存机制提高性能。

设计原则：
- 单一职责：专注于群名配置的读取和渲染
- 配置热更新：每次读取从缓存获取最新值
- 默认值回退：配置不存在时使用默认值
- 容错处理：无效占位符不影响正常渲染

主要功能：
- 读取群名模板配置
- 读取默认阶段显示配置
- 读取群名最大长度配置
- 渲染群聊名称（模板替换 + 长度截断）
"""

import logging
import re
from typing import Optional

from apps.core.models import SystemConfig

logger = logging.getLogger(__name__)


class ChatNameConfigService:
    """群聊名称配置服务
    
    提供群名相关配置的读取和模板渲染功能。
    通过 SystemConfig 模型读取配置，支持缓存机制。
    
    配置项：
    - CASE_CHAT_NAME_TEMPLATE: 群名模板，支持 {stage}、{case_name}、{case_type} 占位符
    - CASE_CHAT_DEFAULT_STAGE: 默认阶段显示文本
    - CASE_CHAT_NAME_MAX_LENGTH: 群名最大长度
    
    Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 3.1, 3.2, 3.3
    """
    
    # 配置键常量
    CONFIG_KEY_TEMPLATE = 'CASE_CHAT_NAME_TEMPLATE'
    CONFIG_KEY_DEFAULT_STAGE = 'CASE_CHAT_DEFAULT_STAGE'
    CONFIG_KEY_MAX_LENGTH = 'CASE_CHAT_NAME_MAX_LENGTH'
    
    # 默认值
    DEFAULT_TEMPLATE = '【{stage}】{case_name}'
    DEFAULT_STAGE = '待定'
    DEFAULT_MAX_LENGTH = 60
    
    # 支持的占位符
    VALID_PLACEHOLDERS = {'stage', 'case_name', 'case_type'}
    
    def __init__(self):
        """初始化群聊名称配置服务"""
        logger.debug("ChatNameConfigService 初始化完成")
    
    def get_template(self) -> str:
        """获取群名模板
        
        从 SystemConfig 读取群名模板配置。
        如果配置不存在或为空，返回默认模板。
        
        Returns:
            str: 群名模板字符串
            
        Requirements: 1.1, 1.2
        """
        template = SystemConfig.get_value(
            self.CONFIG_KEY_TEMPLATE,
            default=self.DEFAULT_TEMPLATE
        )
        
        # 如果配置值为空，使用默认模板
        if not template or not template.strip():
            logger.debug(f"群名模板配置为空，使用默认模板: {self.DEFAULT_TEMPLATE}")
            return self.DEFAULT_TEMPLATE
        
        return template.strip()
    
    def get_default_stage(self) -> str:
        """获取默认阶段显示文本
        
        从 SystemConfig 读取默认阶段显示配置。
        如果配置不存在或为空，返回默认值 "待定"。
        
        Returns:
            str: 默认阶段显示文本
            
        Requirements: 2.1, 2.3
        """
        default_stage = SystemConfig.get_value(
            self.CONFIG_KEY_DEFAULT_STAGE,
            default=self.DEFAULT_STAGE
        )
        
        # 如果配置值为空，使用默认值
        if not default_stage or not default_stage.strip():
            logger.debug(f"默认阶段配置为空，使用默认值: {self.DEFAULT_STAGE}")
            return self.DEFAULT_STAGE
        
        return default_stage.strip()
    
    def get_max_length(self) -> int:
        """获取群名最大长度
        
        从 SystemConfig 读取群名最大长度配置。
        如果配置不存在、为空或无效，返回默认值 60。
        
        Returns:
            int: 群名最大长度
            
        Requirements: 3.1, 3.3
        """
        max_length_str = SystemConfig.get_value(
            self.CONFIG_KEY_MAX_LENGTH,
            default=str(self.DEFAULT_MAX_LENGTH)
        )
        
        try:
            max_length = int(max_length_str)
            if max_length <= 0:
                logger.warning(f"群名最大长度配置无效 ({max_length})，使用默认值: {self.DEFAULT_MAX_LENGTH}")
                return self.DEFAULT_MAX_LENGTH
            return max_length
        except (ValueError, TypeError):
            logger.warning(f"群名最大长度配置格式错误 ({max_length_str})，使用默认值: {self.DEFAULT_MAX_LENGTH}")
            return self.DEFAULT_MAX_LENGTH
    
    def render_chat_name(
        self,
        case_name: str,
        stage: Optional[str] = None,
        case_type: Optional[str] = None
    ) -> str:
        """渲染群聊名称
        
        使用配置的模板渲染群聊名称，支持占位符替换和长度截断。
        
        占位符说明：
        - {stage}: 案件阶段显示名称
        - {case_name}: 案件名称
        - {case_type}: 案件类型显示名称
        
        截断规则：
        - 如果渲染后的群名超过最大长度，进行截断
        - 截断时保留完整的阶段标识部分（如 "【一审】"）
        - 截断案件名称部分，添加省略号
        
        Args:
            case_name: 案件名称
            stage: 案件阶段显示名称（可选，为空时使用默认阶段）
            case_type: 案件类型显示名称（可选）
            
        Returns:
            str: 格式化后的群聊名称
            
        Requirements: 1.2, 1.3, 1.4, 2.2, 3.2
        
        Examples:
            >>> service = ChatNameConfigService()
            >>> service.render_chat_name("张三诉李四合同纠纷案", "一审")
            "【一审】张三诉李四合同纠纷案"
            
            >>> service.render_chat_name("王五诉赵六债务纠纷案", None)
            "【待定】王五诉赵六债务纠纷案"
        """
        # 获取配置
        template = self.get_template()
        max_length = self.get_max_length()
        
        # 处理阶段：为空时使用默认阶段
        if not stage or not stage.strip():
            stage = self.get_default_stage()
        
        # 处理案件类型：为空时使用空字符串
        if not case_type:
            case_type = ''
        
        # 处理案件名称：为空时使用空字符串
        if not case_name:
            case_name = ''
        
        # 渲染模板
        chat_name = self._render_template(template, stage, case_name, case_type)
        
        # 截断处理
        if len(chat_name) > max_length:
            chat_name = self._truncate_chat_name(
                chat_name, max_length, template, stage, case_name, case_type
            )
        
        logger.debug(f"渲染群聊名称: {chat_name}")
        return chat_name
    
    def _render_template(
        self,
        template: str,
        stage: str,
        case_name: str,
        case_type: str
    ) -> str:
        """渲染模板
        
        替换模板中的有效占位符，忽略无效占位符并记录警告。
        
        Args:
            template: 模板字符串
            stage: 阶段显示名称
            case_name: 案件名称
            case_type: 案件类型显示名称
            
        Returns:
            str: 渲染后的字符串
            
        Requirements: 1.3, 1.4
        """
        # 构建替换映射
        replacements = {
            'stage': stage,
            'case_name': case_name,
            'case_type': case_type,
        }
        
        # 查找模板中的所有占位符
        placeholder_pattern = r'\{(\w+)\}'
        found_placeholders = re.findall(placeholder_pattern, template)
        
        # 检查无效占位符
        for placeholder in found_placeholders:
            if placeholder not in self.VALID_PLACEHOLDERS:
                logger.warning(f"模板中包含无效占位符: {{{placeholder}}}，将保留原文")
        
        # 替换有效占位符
        result = template
        for placeholder, value in replacements.items():
            result = result.replace(f'{{{placeholder}}}', value)
        
        return result
    
    def _truncate_chat_name(
        self,
        chat_name: str,
        max_length: int,
        template: str,
        stage: str,
        case_name: str,
        case_type: str
    ) -> str:
        """截断群聊名称
        
        截断群名时保留完整的阶段标识部分。
        
        截断策略：
        1. 识别阶段标识部分（如 "【一审】"）
        2. 计算可用于案件名称的长度
        3. 截断案件名称并添加省略号
        
        Args:
            chat_name: 原始群聊名称
            max_length: 最大长度
            template: 模板字符串
            stage: 阶段显示名称
            case_name: 案件名称
            case_type: 案件类型显示名称
            
        Returns:
            str: 截断后的群聊名称
            
        Requirements: 3.2
        """
        # 识别阶段标识部分
        # 默认模板格式为 "【{stage}】{case_name}"，阶段标识为 "【xxx】"
        stage_prefix = f'【{stage}】'
        
        # 检查群名是否以阶段标识开头
        if chat_name.startswith(stage_prefix):
            # 计算阶段标识长度
            stage_prefix_len = len(stage_prefix)
            
            # 计算可用于案件名称的长度（减去省略号长度）
            ellipsis = '...'
            available_len = max_length - stage_prefix_len - len(ellipsis)
            
            if available_len > 0:
                # 截断案件名称部分
                remaining_part = chat_name[stage_prefix_len:]
                truncated_remaining = remaining_part[:available_len] + ellipsis
                truncated_name = stage_prefix + truncated_remaining
            else:
                # 如果阶段标识本身就超过最大长度，直接截断
                truncated_name = chat_name[:max_length - len(ellipsis)] + ellipsis
        else:
            # 如果不是标准格式，直接截断
            ellipsis = '...'
            truncated_name = chat_name[:max_length - len(ellipsis)] + ellipsis
        
        logger.debug(f"群名截断: {chat_name} -> {truncated_name} (最大长度: {max_length})")
        return truncated_name
