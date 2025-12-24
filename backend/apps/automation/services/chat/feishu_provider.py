"""
飞书群聊提供者实现

本模块实现了飞书平台的群聊操作，包括群聊创建、消息发送、文件上传等功能。
使用飞书开放平台API，支持企业内部群聊管理。

API文档参考：
- 飞书开放平台：https://open.feishu.cn/
- 群聊管理：https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/chat
- 消息发送：https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/message

配置要求：
- FEISHU.APP_ID: 飞书应用ID
- FEISHU.APP_SECRET: 飞书应用密钥
- FEISHU.TIMEOUT: API请求超时时间（可选，默认30秒）
"""

import json
import logging
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import requests

from django.conf import settings

from apps.core.enums import ChatPlatform
from apps.core.exceptions import (
    ChatCreationException,
    MessageSendException,
    ConfigurationException,
    ChatProviderException,
    OwnerPermissionException,
    OwnerNotFoundException,
    OwnerValidationException,
    OwnerTimeoutException,
    OwnerNetworkException,
    OwnerConfigException
)
from .base import ChatProvider, ChatResult, MessageContent
from .owner_config_manager import OwnerConfigManager

logger = logging.getLogger(__name__)


class FeishuChatProvider(ChatProvider):
    """飞书群聊提供者
    
    实现飞书平台的群聊操作，包括：
    - 创建群聊
    - 发送文本消息
    - 发送文件消息
    - 获取群聊信息
    
    使用飞书开放平台API，需要配置应用ID和密钥。
    """
    
    # 飞书API基础URL
    BASE_URL = "https://open.feishu.cn/open-apis"
    
    # API端点
    ENDPOINTS = {
        # 使用内部应用获取 tenant_access_token 的端点
        "tenant_access_token": "/auth/v3/tenant_access_token/internal",
        "create_chat": "/im/v1/chats",
        "send_message": "/im/v1/messages",
        "upload_file": "/im/v1/files",
        "get_chat": "/im/v1/chats/{chat_id}",
    }
    
    def __init__(self):
        """初始化飞书群聊提供者"""
        self.config = self._load_config()
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        
        # 初始化群主配置管理器
        self.owner_config = OwnerConfigManager()
        
        # 验证配置
        if not self.is_available():
            logger.warning("飞书群聊提供者配置不完整，某些功能可能不可用")
    
    @property
    def platform(self) -> ChatPlatform:
        """返回平台类型"""
        return ChatPlatform.FEISHU
    
    def _load_config(self) -> Dict[str, Any]:
        """加载飞书配置
        
        优先从 Admin 后台的 SystemConfig 读取配置，
        如果没有则回退到 Django settings。
        
        Returns:
            Dict[str, Any]: 飞书配置字典
            
        Raises:
            ConfigurationException: 当配置格式错误时
        """
        try:
            config = {}
            
            # 优先从 Admin 后台的 SystemConfig 读取配置
            try:
                from apps.core.models import SystemConfig
                
                # 获取飞书分类下的所有配置
                db_configs = SystemConfig.get_category_configs('feishu')
                
                if db_configs:
                    # 映射数据库配置键到内部配置键
                    key_mapping = {
                        'FEISHU_APP_ID': 'APP_ID',
                        'FEISHU_APP_SECRET': 'APP_SECRET',
                        'FEISHU_WEBHOOK_URL': 'WEBHOOK_URL',
                        'FEISHU_TIMEOUT': 'TIMEOUT',
                        'FEISHU_DEFAULT_OWNER_ID': 'DEFAULT_OWNER_ID',
                    }
                    
                    for db_key, internal_key in key_mapping.items():
                        if db_key in db_configs and db_configs[db_key]:
                            config[internal_key] = db_configs[db_key]
                    
                    logger.debug(f"从 SystemConfig 加载飞书配置: {list(config.keys())}")
                    
            except Exception as e:
                logger.debug(f"从 SystemConfig 加载配置失败，回退到 settings: {str(e)}")
            
            # 如果 SystemConfig 没有配置，回退到 Django settings
            if not config.get('APP_ID') or not config.get('APP_SECRET'):
                settings_config = getattr(settings, 'FEISHU', {})
                
                if isinstance(settings_config, dict):
                    # 合并 settings 配置（不覆盖已有的 SystemConfig 配置）
                    for key, value in settings_config.items():
                        if key not in config and value is not None and value != "":
                            config[key] = value
                    
                    logger.debug(f"从 settings 补充飞书配置: {list(config.keys())}")
            
            # 设置默认值
            config.setdefault('TIMEOUT', 30)
            
            # 过滤掉空值配置
            filtered_config = {}
            for key, value in config.items():
                if value is not None and value != "":
                    filtered_config[key] = value
            
            logger.debug(f"最终飞书配置: {list(filtered_config.keys())}")
            return filtered_config
            
        except Exception as e:
            logger.error(f"加载飞书配置失败: {str(e)}")
            raise ConfigurationException(
                message=f"无法加载飞书配置: {str(e)}",
                platform="feishu",
                errors={"original_error": str(e)}
            ) from e
    
    def is_available(self) -> bool:
        """检查平台是否可用
        
        检查必要的配置项是否存在。
        
        Returns:
            bool: 平台是否可用
        """
        required_configs = ['APP_ID', 'APP_SECRET']
        
        for config_key in required_configs:
            if not self.config.get(config_key):
                logger.debug(f"飞书配置缺失: {config_key}")
                return False
        
        return True
    
    def _get_tenant_access_token(self) -> str:
        """获取租户访问令牌
        
        使用应用ID和密钥获取访问令牌，支持令牌缓存和自动刷新。
        
        Returns:
            str: 访问令牌
            
        Raises:
            ConfigurationException: 当配置不完整时
            ChatProviderException: 当API调用失败时
        """
        # 检查缓存的令牌是否有效
        if (self._access_token and 
            self._token_expires_at and 
            datetime.now() < self._token_expires_at - timedelta(minutes=5)):  # 提前5分钟刷新
            return self._access_token
        
        # 检查必要配置
        app_id = self.config.get('APP_ID')
        app_secret = self.config.get('APP_SECRET')
        
        if not app_id or not app_secret:
            raise ConfigurationException(
                message="飞书APP_ID或APP_SECRET未配置",
                platform="feishu",
                missing_config="APP_ID, APP_SECRET"
            )
        
        # 请求新的访问令牌
        url = f"{self.BASE_URL}{self.ENDPOINTS['tenant_access_token']}"
        payload = {
            "app_id": app_id,
            "app_secret": app_secret
        }
        
        try:
            timeout = self.config.get('TIMEOUT', 30)
            response = requests.post(
                url,
                json=payload,
                timeout=timeout,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            
            data = response.json()
            
            # 检查飞书API响应
            if data.get('code') != 0:
                error_msg = data.get('msg', '未知错误')
                raise ChatProviderException(
                    message=f"获取飞书访问令牌失败: {error_msg}",
                    platform="feishu",
                    error_code=str(data.get('code')),
                    errors={"api_response": data}
                )
            
            # 缓存令牌
            self._access_token = data['tenant_access_token']
            expires_in = data.get('expire', 7200)  # 默认2小时
            self._token_expires_at = datetime.now() + timedelta(seconds=expires_in)
            
            logger.debug("已获取飞书访问令牌")
            return self._access_token
            
        except requests.RequestException as e:
            logger.error(f"请求飞书访问令牌失败: {str(e)}")
            raise ChatProviderException(
                message=f"网络请求失败: {str(e)}",
                platform="feishu",
                errors={"original_error": str(e)}
            ) from e
        except (KeyError, ValueError) as e:
            logger.error(f"解析飞书API响应失败: {str(e)}")
            raise ChatProviderException(
                message=f"API响应格式错误: {str(e)}",
                platform="feishu",
                errors={"original_error": str(e)}
            ) from e
    
    def create_chat(self, chat_name: str, owner_id: Optional[str] = None) -> ChatResult:
        """创建群聊
        
        调用飞书开放平台API创建群聊，支持群主设置功能。
        集成OwnerConfigManager获取有效群主ID。
        
        根据飞书开发文档：https://open.feishu.cn/document/server-docs/group/chat/create
        
        注意：飞书创建群聊API要求：
        1. 使用 user_id_type 查询参数指定用户ID类型
        2. 如果不指定 owner_id，则机器人为群主
        3. user_id_list 可以为空，创建只有机器人的群
        
        Args:
            chat_name: 群聊名称
            owner_id: 群主ID（可选，飞书中为用户的open_id）
            
        Returns:
            ChatResult: 包含群聊ID和创建结果的响应对象
            
        Raises:
            ChatCreationException: 当群聊创建失败时
            ConfigurationException: 当配置不完整时
            
        Requirements: 1.1, 1.4
        """
        if not self.is_available():
            raise ConfigurationException(
                message="飞书配置不完整，无法创建群聊",
                platform="feishu",
                missing_config="APP_ID, APP_SECRET"
            )
        
        try:
            # 使用OwnerConfigManager获取有效的群主ID
            effective_owner_id = self.owner_config.get_effective_owner_id(owner_id)
            
            logger.info(f"创建飞书群聊: {chat_name}, 指定群主: {owner_id}, 有效群主: {effective_owner_id}")
            
            # 获取访问令牌
            access_token = self._get_tenant_access_token()
            
            # 构建请求URL（带查询参数）
            url = f"{self.BASE_URL}{self.ENDPOINTS['create_chat']}"
            
            # 查询参数 - 指定用户ID类型
            params = {
                "user_id_type": "open_id"
            }
            
            # 请求头
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=utf-8"
            }
            
            # 根据飞书官方API文档构建请求体
            payload = {
                "name": chat_name,
                "chat_mode": "group",  # 群聊模式
                "chat_type": "private",  # 私有群聊
                "add_member_permission": "all_members",  # 谁可以添加群成员
                "share_card_permission": "allowed",  # 是否允许分享群名片
                "at_all_permission": "all_members",  # 谁可以@所有人
                "group_message_type": "chat"  # 群消息形式
            }
            
            # 如果提供了描述，添加到请求体
            description = f"案件群聊: {chat_name}"
            if description:
                payload["description"] = description
            
            # 如果有有效的群主ID，添加到参数中
            if effective_owner_id:
                # 验证群主ID格式（如果启用验证）
                if self.owner_config.is_validation_enabled():
                    try:
                        self.owner_config.validate_owner_id_strict(effective_owner_id)
                    except Exception as e:
                        logger.warning(f"群主ID验证失败，继续使用: {effective_owner_id}, 错误: {str(e)}")
                
                # 如果是union_id格式，需要转换为open_id
                if effective_owner_id.startswith('on_'):
                    # 这是union_id，需要转换为open_id
                    open_id = self._convert_union_id_to_open_id(effective_owner_id)
                    if open_id:
                        payload["owner_id"] = open_id
                        payload["user_id_list"] = [open_id]
                        logger.debug(f"转换union_id为open_id: {effective_owner_id} -> {open_id}")
                    else:
                        logger.warning(f"无法转换union_id为open_id: {effective_owner_id}")
                else:
                    # 直接使用提供的ID（假设是open_id）
                    payload["owner_id"] = effective_owner_id
                    payload["user_id_list"] = [effective_owner_id]
            
            logger.debug(f"创建飞书群聊请求URL: {url}")
            logger.debug(f"创建飞书群聊请求参数: {params}")
            logger.debug(f"创建飞书群聊请求体: {payload}")
            
            # 发送请求
            timeout = self.config.get('TIMEOUT', 30)
            response = requests.post(
                url,
                params=params,
                json=payload,
                headers=headers,
                timeout=timeout
            )
            
            # 记录响应详情用于调试
            logger.debug(f"飞书API响应状态码: {response.status_code}")
            logger.debug(f"飞书API响应内容: {response.text}")
            
            response.raise_for_status()
            
            data = response.json()
            logger.debug(f"飞书API响应数据: {data}")
            
            # 检查飞书API响应
            if data.get('code') != 0:
                error_msg = data.get('msg', '未知错误')
                error_code = str(data.get('code'))
                
                logger.error(f"创建飞书群聊失败: {error_msg} (code: {error_code})")
                logger.error(f"完整响应: {data}")
                
                # 根据错误代码分类异常类型
                exception_class = self._classify_feishu_error(error_code, error_msg)
                
                raise exception_class(
                    message=f"创建群聊失败: {error_msg}",
                    platform="feishu",
                    error_code=error_code,
                    owner_id=effective_owner_id,
                    chat_id=None,
                    errors={
                        "api_response": data,
                        "chat_name": chat_name,
                        "specified_owner_id": owner_id,
                        "effective_owner_id": effective_owner_id,
                        "request_payload": payload
                    }
                )
            
            # 提取群聊信息
            chat_data = data.get('data', {})
            chat_id = chat_data.get('chat_id')
            
            if not chat_id:
                raise ChatCreationException(
                    message="API响应中缺少群聊ID",
                    platform="feishu",
                    errors={"api_response": data}
                )
            
            logger.info(f"成功创建飞书群聊: {chat_name} (ID: {chat_id}), 群主: {effective_owner_id}")
            
            # 构建包含群主信息的响应
            result = ChatResult(
                success=True,
                chat_id=chat_id,
                chat_name=chat_name,
                message="群聊创建成功",
                raw_response=data
            )
            
            # 在raw_response中添加群主信息，便于后续验证
            if result.raw_response:
                result.raw_response['owner_info'] = {
                    'specified_owner_id': owner_id,
                    'effective_owner_id': effective_owner_id,
                    'owner_set': bool(effective_owner_id)
                }
            
            return result
            
        except ChatCreationException:
            # 重新抛出业务异常
            raise
        except requests.RequestException as e:
            logger.error(f"创建飞书群聊网络请求失败: {str(e)}")
            raise OwnerNetworkException(
                message=f"网络请求失败: {str(e)}",
                platform="feishu",
                owner_id=effective_owner_id,
                network_error=str(e),
                errors={
                    "original_error": str(e),
                    "chat_name": chat_name,
                    "specified_owner_id": owner_id
                }
            ) from e
        except Exception as e:
            logger.error(f"创建飞书群聊时发生未知错误: {str(e)}")
            raise ChatCreationException(
                message=f"创建群聊时发生未知错误: {str(e)}",
                platform="feishu",
                errors={
                    "original_error": str(e),
                    "chat_name": chat_name,
                    "specified_owner_id": owner_id
                }
            ) from e
    
    def send_message(self, chat_id: str, content: MessageContent) -> ChatResult:
        """发送消息到群聊
        
        使用简单的文本消息格式，避免复杂的富文本格式问题。
        
        Args:
            chat_id: 群聊ID
            content: 消息内容
            
        Returns:
            ChatResult: 消息发送结果
            
        Raises:
            MessageSendException: 当消息发送失败时
            ConfigurationException: 当配置不完整时
        """
        if not self.is_available():
            raise ConfigurationException(
                message="飞书配置不完整，无法发送消息",
                platform="feishu",
                missing_config="APP_ID, APP_SECRET"
            )
        
        try:
            # 获取访问令牌
            access_token = self._get_tenant_access_token()
            
            # 构建请求URL和查询参数
            url = f"{self.BASE_URL}{self.ENDPOINTS['send_message']}"
            params = {
                "receive_id_type": "chat_id"  # 作为查询参数传递
            }
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            # 构建简单的文本消息内容
            message_text = self._build_simple_text_message(content)
            
            # 构建消息参数 - 不包含 receive_id_type（已在查询参数中）
            payload = {
                "receive_id": chat_id,
                "msg_type": "text",
                "content": json.dumps({
                    "text": message_text
                })
            }
            
            logger.debug(f"发送飞书消息请求URL: {url}")
            logger.debug(f"发送飞书消息查询参数: {params}")
            logger.debug(f"发送飞书消息请求体: {payload}")
            
            # 发送请求
            timeout = self.config.get('TIMEOUT', 30)
            response = requests.post(
                url,
                params=params,  # 添加查询参数
                json=payload,
                headers=headers,
                timeout=timeout
            )
            
            logger.debug(f"飞书API响应状态码: {response.status_code}")
            logger.debug(f"飞书API响应内容: {response.text}")
            
            response.raise_for_status()
            
            data = response.json()
            
            # 检查飞书API响应
            if data.get('code') != 0:
                error_msg = data.get('msg', '未知错误')
                error_code = str(data.get('code'))
                
                logger.error(f"发送飞书消息失败: {error_msg} (code: {error_code})")
                logger.error(f"完整响应: {data}")
                
                raise MessageSendException(
                    message=f"发送消息失败: {error_msg}",
                    platform="feishu",
                    error_code=error_code,
                    chat_id=chat_id,
                    errors={
                        "api_response": data,
                        "content": content.__dict__,
                        "request_payload": payload
                    }
                )
            
            # 提取消息信息
            message_data = data.get('data', {})
            message_id = message_data.get('message_id')
            
            logger.info(f"成功发送飞书消息到群聊: {chat_id} (消息ID: {message_id})")
            
            return ChatResult(
                success=True,
                chat_id=chat_id,
                message="消息发送成功",
                raw_response=data
            )
            
        except MessageSendException:
            # 重新抛出业务异常
            raise
        except requests.RequestException as e:
            logger.error(f"发送飞书消息网络请求失败: {str(e)}")
            raise MessageSendException(
                message=f"网络请求失败: {str(e)}",
                platform="feishu",
                chat_id=chat_id,
                errors={
                    "original_error": str(e),
                    "content": content.__dict__
                }
            ) from e
        except Exception as e:
            logger.error(f"发送飞书消息时发生未知错误: {str(e)}")
            raise MessageSendException(
                message=f"发送消息时发生未知错误: {str(e)}",
                platform="feishu",
                chat_id=chat_id,
                errors={
                    "original_error": str(e),
                    "content": content.__dict__
                }
            ) from e
    
    def _build_simple_text_message(self, content: MessageContent) -> str:
        """构建简单的文本消息
        
        将MessageContent转换为简单的文本格式，避免复杂的富文本格式问题。
        
        Args:
            content: 消息内容
            
        Returns:
            str: 格式化的文本消息
        """
        message_parts = []
        
        # 添加标题（如果存在）
        if content.title:
            message_parts.append(f"📋 {content.title}")
        
        # 添加正文
        if content.text:
            message_parts.append(content.text)
        
        # 用换行符连接各部分
        return "\n\n".join(message_parts) if message_parts else "空消息"
    
    def _build_rich_text_message(self, content: MessageContent) -> Dict[str, Any]:
        """构建飞书富文本消息格式
        
        将MessageContent转换为飞书支持的富文本消息格式。
        注意：此方法保留用于未来可能的富文本需求。
        
        Args:
            content: 消息内容
            
        Returns:
            Dict[str, Any]: 飞书富文本消息格式
        """
        # 构建富文本元素
        elements = []
        
        # 添加标题（如果存在）
        if content.title:
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**{content.title}**"
                }
            })
        
        # 添加正文
        if content.text:
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": content.text
                }
            })
        
        # 添加分隔线（如果有标题和正文）
        if content.title and content.text:
            elements.insert(1, {
                "tag": "hr"
            })
        
        # 构建完整的富文本消息
        rich_text_content = {
            "elements": elements
        }
        
        return rich_text_content
    
    def send_file(self, chat_id: str, file_path: str) -> ChatResult:
        """发送文件到群聊
        
        先上传文件获取file_key，然后发送文件消息。
        
        Args:
            chat_id: 群聊ID
            file_path: 文件路径
            
        Returns:
            ChatResult: 文件发送结果
            
        Raises:
            MessageSendException: 当文件发送失败时
            ConfigurationException: 当配置不完整时
        """
        if not self.is_available():
            raise ConfigurationException(
                message="飞书配置不完整，无法发送文件",
                platform="feishu",
                missing_config="APP_ID, APP_SECRET"
            )
        
        import os
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            raise MessageSendException(
                message=f"文件不存在: {file_path}",
                platform="feishu",
                chat_id=chat_id,
                errors={"file_path": file_path}
            )
        
        try:
            # 第一步：上传文件获取file_key
            file_key = self._upload_file(file_path)
            
            # 第二步：发送文件消息
            return self._send_file_message(chat_id, file_key, file_path)
            
        except MessageSendException:
            # 重新抛出业务异常
            raise
        except Exception as e:
            logger.error(f"发送飞书文件时发生未知错误: {str(e)}")
            raise MessageSendException(
                message=f"发送文件时发生未知错误: {str(e)}",
                platform="feishu",
                chat_id=chat_id,
                errors={
                    "original_error": str(e),
                    "file_path": file_path
                }
            ) from e
    
    def _upload_file(self, file_path: str) -> str:
        """上传文件到飞书并获取file_key
        
        Args:
            file_path: 文件路径
            
        Returns:
            str: 飞书文件key
            
        Raises:
            MessageSendException: 当文件上传失败时
        """
        import os
        
        try:
            # 获取访问令牌
            access_token = self._get_tenant_access_token()
            
            # 构建请求
            url = f"{self.BASE_URL}{self.ENDPOINTS['upload_file']}"
            headers = {
                "Authorization": f"Bearer {access_token}"
            }
            
            # 准备文件上传
            file_name = os.path.basename(file_path)
            file_type = self._get_file_type(file_path)
            
            with open(file_path, 'rb') as file:
                files = {
                    'file': (file_name, file, self._get_mime_type(file_path))
                }
                data = {
                    'file_type': file_type,
                    'file_name': file_name
                }
                
                # 发送请求
                timeout = self.config.get('TIMEOUT', 30)
                response = requests.post(
                    url,
                    headers=headers,
                    files=files,
                    data=data,
                    timeout=timeout
                )
                response.raise_for_status()
            
            data = response.json()
            
            # 检查飞书API响应
            if data.get('code') != 0:
                error_msg = data.get('msg', '未知错误')
                error_code = str(data.get('code'))
                
                logger.error(f"上传飞书文件失败: {error_msg} (code: {error_code})")
                
                raise MessageSendException(
                    message=f"文件上传失败: {error_msg}",
                    platform="feishu",
                    error_code=error_code,
                    errors={
                        "api_response": data,
                        "file_path": file_path
                    }
                )
            
            # 提取file_key
            file_data = data.get('data', {})
            file_key = file_data.get('file_key')
            
            if not file_key:
                raise MessageSendException(
                    message="API响应中缺少文件key",
                    platform="feishu",
                    errors={"api_response": data}
                )
            
            logger.debug(f"成功上传文件到飞书: {file_name} (key: {file_key})")
            return file_key
            
        except MessageSendException:
            raise
        except requests.RequestException as e:
            logger.error(f"上传飞书文件网络请求失败: {str(e)}")
            raise MessageSendException(
                message=f"文件上传网络请求失败: {str(e)}",
                platform="feishu",
                errors={
                    "original_error": str(e),
                    "file_path": file_path
                }
            ) from e
        except Exception as e:
            logger.error(f"上传飞书文件时发生未知错误: {str(e)}")
            raise MessageSendException(
                message=f"文件上传时发生未知错误: {str(e)}",
                platform="feishu",
                errors={
                    "original_error": str(e),
                    "file_path": file_path
                }
            ) from e
    
    def _send_file_message(self, chat_id: str, file_key: str, file_path: str) -> ChatResult:
        """发送文件消息
        
        根据飞书官方API文档，发送文件消息时 content 中只需要 file_key。
        参考：https://open.feishu.cn/document/server-docs/im-v1/message/create
        
        Args:
            chat_id: 群聊ID
            file_key: 飞书文件key
            file_path: 原始文件路径（用于日志记录）
            
        Returns:
            ChatResult: 文件发送结果
        """
        import os
        
        try:
            # 获取访问令牌
            access_token = self._get_tenant_access_token()
            
            # 构建请求URL和查询参数
            # 根据飞书官方示例：url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
            url = f"{self.BASE_URL}{self.ENDPOINTS['send_message']}"
            params = {
                "receive_id_type": "chat_id"
            }
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=utf-8"
            }
            
            # 根据飞书官方示例，content 中只需要 file_key，不需要 file_name
            # 官方示例：content = {"file_key": file_key}
            file_name = os.path.basename(file_path)
            content = {"file_key": file_key}
            
            payload = {
                "receive_id": chat_id,
                "msg_type": "file",
                "content": json.dumps(content, ensure_ascii=False)
            }
            
            logger.debug(f"发送飞书文件消息请求URL: {url}")
            logger.debug(f"发送飞书文件消息查询参数: {params}")
            logger.debug(f"发送飞书文件消息请求体: {payload}")
            
            # 发送请求
            timeout = self.config.get('TIMEOUT', 30)
            response = requests.post(
                url,
                params=params,  # 添加查询参数
                json=payload,
                headers=headers,
                timeout=timeout
            )
            
            logger.debug(f"飞书API响应状态码: {response.status_code}")
            logger.debug(f"飞书API响应内容: {response.text}")
            
            response.raise_for_status()
            
            data = response.json()
            
            # 检查飞书API响应
            if data.get('code') != 0:
                error_msg = data.get('msg', '未知错误')
                error_code = str(data.get('code'))
                
                logger.error(f"发送飞书文件消息失败: {error_msg} (code: {error_code})")
                logger.error(f"完整响应: {data}")
                
                raise MessageSendException(
                    message=f"发送文件消息失败: {error_msg}",
                    platform="feishu",
                    error_code=error_code,
                    chat_id=chat_id,
                    errors={
                        "api_response": data,
                        "file_key": file_key,
                        "file_path": file_path,
                        "request_payload": payload
                    }
                )
            
            # 提取消息信息
            message_data = data.get('data', {})
            message_id = message_data.get('message_id')
            
            logger.info(f"成功发送飞书文件到群聊: {chat_id} (文件: {file_name}, 消息ID: {message_id})")
            
            return ChatResult(
                success=True,
                chat_id=chat_id,
                message=f"文件发送成功: {file_name}",
                raw_response=data
            )
            
        except MessageSendException:
            raise
        except requests.RequestException as e:
            logger.error(f"发送飞书文件消息网络请求失败: {str(e)}")
            raise MessageSendException(
                message=f"发送文件消息网络请求失败: {str(e)}",
                platform="feishu",
                chat_id=chat_id,
                errors={
                    "original_error": str(e),
                    "file_key": file_key,
                    "file_path": file_path
                }
            ) from e
    
    def _get_file_type(self, file_path: str) -> str:
        """根据文件扩展名确定飞书文件类型
        
        Args:
            file_path: 文件路径
            
        Returns:
            str: 飞书文件类型
        """
        import os
        
        _, ext = os.path.splitext(file_path.lower())
        
        # 飞书支持的文件类型映射
        file_type_mapping = {
            '.pdf': 'pdf',
            '.doc': 'doc',
            '.docx': 'docx',
            '.xls': 'xls',
            '.xlsx': 'xlsx',
            '.ppt': 'ppt',
            '.pptx': 'pptx',
            '.txt': 'txt',
            '.jpg': 'image',
            '.jpeg': 'image',
            '.png': 'image',
            '.gif': 'image',
            '.mp4': 'video',
            '.avi': 'video',
            '.mov': 'video',
            '.mp3': 'audio',
            '.wav': 'audio',
            '.zip': 'zip',
            '.rar': 'rar',
        }
        
        return file_type_mapping.get(ext, 'file')
    
    def _get_mime_type(self, file_path: str) -> str:
        """根据文件扩展名确定MIME类型
        
        Args:
            file_path: 文件路径
            
        Returns:
            str: MIME类型
        """
        import os
        import mimetypes
        
        mime_type, _ = mimetypes.guess_type(file_path)
        return mime_type or 'application/octet-stream'
    
    def get_chat_info(self, chat_id: str) -> ChatResult:
        """获取群聊详细信息
        
        Args:
            chat_id: 群聊ID
            
        Returns:
            ChatResult: 包含群聊详细信息的响应对象
            
        Raises:
            ChatProviderException: 当获取群聊信息失败时
            ConfigurationException: 当配置不完整时
        """
        if not self.is_available():
            raise ConfigurationException(
                message="飞书配置不完整，无法获取群聊信息",
                platform="feishu",
                missing_config="APP_ID, APP_SECRET"
            )
        
        try:
            # 获取访问令牌
            access_token = self._get_tenant_access_token()
            
            # 构建请求
            url = f"{self.BASE_URL}{self.ENDPOINTS['get_chat'].format(chat_id=chat_id)}"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            # 发送请求
            timeout = self.config.get('TIMEOUT', 30)
            response = requests.get(
                url,
                headers=headers,
                timeout=timeout
            )
            response.raise_for_status()
            
            data = response.json()
            
            # 检查飞书API响应
            if data.get('code') != 0:
                error_msg = data.get('msg', '未知错误')
                error_code = str(data.get('code'))
                
                logger.error(f"获取飞书群聊信息失败: {error_msg} (code: {error_code})")
                
                raise ChatProviderException(
                    message=f"获取群聊信息失败: {error_msg}",
                    platform="feishu",
                    error_code=error_code,
                    errors={
                        "api_response": data,
                        "chat_id": chat_id
                    }
                )
            
            # 提取群聊信息
            chat_data = data.get('data', {})
            chat_name = chat_data.get('name', '')
            
            logger.debug(f"成功获取飞书群聊信息: {chat_id} (名称: {chat_name})")
            
            return ChatResult(
                success=True,
                chat_id=chat_id,
                chat_name=chat_name,
                message="获取群聊信息成功",
                raw_response=data
            )
            
        except ChatProviderException:
            # 重新抛出业务异常
            raise
        except requests.RequestException as e:
            logger.error(f"获取飞书群聊信息网络请求失败: {str(e)}")
            raise ChatProviderException(
                message=f"网络请求失败: {str(e)}",
                platform="feishu",
                errors={
                    "original_error": str(e),
                    "chat_id": chat_id
                }
            ) from e
        except Exception as e:
            logger.error(f"获取飞书群聊信息时发生未知错误: {str(e)}")
            raise ChatProviderException(
                message=f"获取群聊信息时发生未知错误: {str(e)}",
                platform="feishu",
                errors={
                    "original_error": str(e),
                    "chat_id": chat_id
                }
            ) from e
    
    def verify_owner_setting(self, chat_id: str, expected_owner_id: str) -> bool:
        """验证群主设置是否正确
        
        创建群聊后验证群主设置是否正确。
        通过查询群聊信息来验证实际群主是否与期望的群主一致。
        
        Args:
            chat_id: 群聊ID
            expected_owner_id: 期望的群主ID
            
        Returns:
            bool: 群主设置是否正确
            
        Requirements: 1.2
        
        Example:
            provider = FeishuChatProvider()
            result = provider.create_chat("测试群聊", "ou_abc123")
            if result.success:
                is_correct = provider.verify_owner_setting(result.chat_id, "ou_abc123")
        """
        try:
            # 获取群聊信息
            chat_info = self.get_chat_owner_info(chat_id)
            
            if not chat_info:
                logger.warning(f"无法获取群聊信息进行群主验证: {chat_id}")
                return False
            
            # 获取实际群主ID
            actual_owner_id = chat_info.get('owner_id')
            
            if not actual_owner_id:
                logger.warning(f"群聊信息中缺少群主ID: {chat_id}")
                return False
            
            # 比较群主ID
            is_match = actual_owner_id == expected_owner_id
            
            if is_match:
                logger.info(f"群主设置验证成功: {chat_id}, 群主: {actual_owner_id}")
            else:
                logger.warning(f"群主设置验证失败: {chat_id}, 期望: {expected_owner_id}, 实际: {actual_owner_id}")
            
            return is_match
            
        except Exception as e:
            logger.error(f"验证群主设置时发生错误: {chat_id}, 错误: {str(e)}")
            return False
    
    def get_chat_owner_info(self, chat_id: str) -> Dict[str, Any]:
        """获取群聊群主信息
        
        查询群聊详细信息，提取群主相关信息。
        
        Args:
            chat_id: 群聊ID
            
        Returns:
            Dict[str, Any]: 群主信息字典，包含owner_id等字段
            
        Raises:
            ChatProviderException: 当获取群聊信息失败时
            
        Requirements: 1.2
        
        Example:
            provider = FeishuChatProvider()
            owner_info = provider.get_chat_owner_info("oc_abc123")
            print(f"群主ID: {owner_info.get('owner_id')}")
        """
        if not self.is_available():
            raise ConfigurationException(
                message="飞书配置不完整，无法获取群聊群主信息",
                platform="feishu",
                missing_config="APP_ID, APP_SECRET"
            )
        
        try:
            # 获取访问令牌
            access_token = self._get_tenant_access_token()
            
            # 构建请求URL，添加查询参数指定用户ID类型
            url = f"{self.BASE_URL}{self.ENDPOINTS['get_chat'].format(chat_id=chat_id)}"
            params = {
                "user_id_type": "open_id"
            }
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            # 发送请求
            timeout = self.config.get('TIMEOUT', 30)
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=timeout
            )
            response.raise_for_status()
            
            data = response.json()
            
            # 检查飞书API响应
            if data.get('code') != 0:
                error_msg = data.get('msg', '未知错误')
                error_code = str(data.get('code'))
                
                logger.error(f"获取飞书群聊群主信息失败: {error_msg} (code: {error_code})")
                
                raise ChatProviderException(
                    message=f"获取群聊群主信息失败: {error_msg}",
                    platform="feishu",
                    error_code=error_code,
                    errors={
                        "api_response": data,
                        "chat_id": chat_id
                    }
                )
            
            # 提取群聊信息
            chat_data = data.get('data', {})
            
            # 构建群主信息
            owner_info = {
                'chat_id': chat_id,
                'owner_id': chat_data.get('owner_id'),
                'owner_id_type': chat_data.get('owner_id_type', 'open_id'),
                'chat_name': chat_data.get('name'),
                'chat_mode': chat_data.get('chat_mode'),
                'chat_type': chat_data.get('chat_type'),
                'member_count': len(chat_data.get('members', [])),
                'raw_data': chat_data
            }
            
            logger.debug(f"成功获取群聊群主信息: {chat_id}, 群主: {owner_info.get('owner_id')}")
            
            return owner_info
            
        except ChatProviderException:
            # 重新抛出业务异常
            raise
        except requests.RequestException as e:
            logger.error(f"获取飞书群聊群主信息网络请求失败: {str(e)}")
            raise ChatProviderException(
                message=f"网络请求失败: {str(e)}",
                platform="feishu",
                errors={
                    "original_error": str(e),
                    "chat_id": chat_id
                }
            ) from e
        except Exception as e:
            logger.error(f"获取飞书群聊群主信息时发生未知错误: {str(e)}")
            raise ChatProviderException(
                message=f"获取群聊群主信息时发生未知错误: {str(e)}",
                platform="feishu",
                errors={
                    "original_error": str(e),
                    "chat_id": chat_id
                }
            ) from e
    def retry_owner_setting(self, chat_id: str, owner_id: str, max_retries: int = 3) -> bool:
        """重试群主设置
        
        当群主设置失败时，使用RetryManager实现智能重试策略。
        支持不同错误类型的重试策略和指数退避算法。
        
        Args:
            chat_id: 群聊ID
            owner_id: 群主ID
            max_retries: 最大重试次数（默认3次，实际以配置为准）
            
        Returns:
            bool: 重试是否成功
            
        Requirements: 1.3
        
        Example:
            provider = FeishuChatProvider()
            success = provider.retry_owner_setting("oc_abc123", "ou_def456", 3)
        """
        from .retry_config import RetryManager, RetryConfig
        from apps.core.exceptions import OwnerRetryException
        
        if not self.owner_config.is_retry_enabled():
            logger.info(f"重试机制已禁用，跳过群主设置重试: {chat_id}")
            return False
        
        # 创建重试管理器
        retry_manager = RetryManager()
        
        # 定义重试操作
        def verify_operation():
            """验证群主设置的操作"""
            if not self.verify_owner_setting(chat_id, owner_id):
                # 如果验证失败，抛出异常触发重试
                from apps.core.exceptions import OwnerValidationException
                raise OwnerValidationException(
                    message=f"群主设置验证失败: 期望群主 {owner_id}",
                    owner_id=owner_id,
                    chat_id=chat_id,
                    validation_type="owner_verification"
                )
            return True
        
        try:
            # 执行带重试的验证操作
            result = retry_manager.execute_with_retry(
                operation=verify_operation,
                operation_name=f"verify_owner_setting_{chat_id}",
                context={
                    "chat_id": chat_id,
                    "owner_id": owner_id,
                    "max_retries": max_retries
                }
            )
            
            # 获取重试摘要
            summary = retry_manager.get_retry_summary()
            logger.info(f"群主设置重试成功: {chat_id}, 摘要: {summary}")
            
            return True
            
        except Exception as e:
            # 获取重试摘要
            summary = retry_manager.get_retry_summary()
            logger.error(f"群主设置重试最终失败: {chat_id}, 摘要: {summary}, 错误: {str(e)}")
            
            return False
    

    
    def _classify_feishu_error(self, error_code: str, error_msg: str):
        """分类飞书API错误
        
        根据飞书API返回的错误代码和错误消息，分类为相应的异常类型。
        
        Args:
            error_code: 飞书API错误代码
            error_msg: 飞书API错误消息
            
        Returns:
            Exception class: 相应的异常类
        """
        # 飞书API常见错误代码映射
        # 参考：https://open.feishu.cn/document/ukTMukTMukTM/ugjM14COyUjL4ITN
        
        error_msg_lower = error_msg.lower()
        
        # 权限相关错误
        if (error_code in ['99991663', '99991664', '99991665'] or 
            'permission' in error_msg_lower or 
            'forbidden' in error_msg_lower or
            'access denied' in error_msg_lower):
            return OwnerPermissionException
        
        # 用户不存在错误
        if (error_code in ['99991400', '99991401'] or
            'user not found' in error_msg_lower or
            'invalid user' in error_msg_lower or
            'user does not exist' in error_msg_lower):
            return OwnerNotFoundException
        
        # 参数验证错误
        if (error_code in ['99991400', '1400'] or
            'invalid parameter' in error_msg_lower or
            'parameter error' in error_msg_lower or
            'validation failed' in error_msg_lower):
            return OwnerValidationException
        
        # 超时错误
        if ('timeout' in error_msg_lower or
            'timed out' in error_msg_lower):
            return OwnerTimeoutException
        
        # 网络错误
        if ('network' in error_msg_lower or
            'connection' in error_msg_lower or
            'request failed' in error_msg_lower):
            return OwnerNetworkException
        
        # 默认返回通用群聊创建异常
        return ChatCreationException
    
    def _convert_union_id_to_open_id(self, union_id: str) -> Optional[str]:
        """转换union_id为open_id
        
        通过飞书API将union_id转换为open_id。
        使用用户信息查询API进行转换。
        
        Args:
            union_id: 飞书用户的union_id
            
        Returns:
            Optional[str]: 对应的open_id，如果转换失败则返回None
        """
        try:
            # 获取访问令牌
            access_token = self._get_tenant_access_token()
            
            # 构建请求URL
            url = f"{self.BASE_URL}/contact/v3/users/{union_id}"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            # 查询参数：指定返回open_id
            params = {
                "user_id_type": "union_id",  # 输入类型是union_id
                "department_id_type": "department_id"
            }
            
            # 发送请求
            timeout = self.config.get('TIMEOUT', 30)
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=timeout
            )
            response.raise_for_status()
            
            data = response.json()
            
            # 检查API响应
            if data.get('code') == 0:
                user_data = data.get('data', {}).get('user', {})
                open_id = user_data.get('open_id')
                
                if open_id:
                    logger.info(f"成功转换union_id为open_id: {union_id} -> {open_id}")
                    return open_id
                else:
                    logger.warning(f"API响应中缺少open_id: {union_id}")
                    return None
            else:
                error_msg = data.get('msg', '未知错误')
                logger.warning(f"转换union_id失败: {union_id}, 错误: {error_msg}")
                return None
                
        except Exception as e:
            logger.error(f"转换union_id时发生错误: {union_id}, 错误: {str(e)}")
            return None