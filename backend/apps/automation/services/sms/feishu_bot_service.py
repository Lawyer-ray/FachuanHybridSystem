"""
飞书机器人服务

负责发送飞书消息和文件上传功能。
"""
import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path

import httpx
from django.conf import settings

from apps.core.exceptions import ValidationException


logger = logging.getLogger(__name__)


class FeishuBotService:
    """飞书机器人服务"""
    
    def __init__(self, webhook_url: str = None, timeout: int = None):
        """
        初始化飞书机器人服务
        
        Args:
            webhook_url: 飞书机器人 Webhook URL，如果不提供则从配置读取
            timeout: 请求超时时间（秒），如果不提供则从配置读取
        """
        self.webhook_url = webhook_url or self._get_webhook_url()
        self.timeout = timeout or self._get_timeout()
        
    def _get_webhook_url(self) -> str:
        """从配置获取 Webhook URL"""
        # 尝试使用统一配置管理器
        try:
            if getattr(settings, 'CONFIG_MANAGER_AVAILABLE', False):
                get_unified_config = getattr(settings, 'get_unified_config', None)
                if get_unified_config:
                    webhook_url = get_unified_config('chat_platforms.feishu.webhook_url')
                    if webhook_url:
                        return webhook_url
        except Exception as e:
            logger.debug(f"从统一配置获取飞书 Webhook URL 失败: {e}")
        
        # 回退到传统配置方式
        # 优先从 settings.FEISHU 读取
        feishu_config = getattr(settings, 'FEISHU', {})
        webhook_url = feishu_config.get('WEBHOOK_URL')
        
        # 兼容旧配置：从 COURT_SMS_PROCESSING 读取
        if not webhook_url:
            court_sms_config = getattr(settings, 'COURT_SMS_PROCESSING', {})
            webhook_url = court_sms_config.get('FEISHU_WEBHOOK_URL')
            
        if not webhook_url:
            logger.warning("未配置飞书 Webhook URL，飞书通知功能将不可用")
            
        return webhook_url
    
    def _get_timeout(self) -> int:
        """从配置获取超时时间"""
        # 尝试使用统一配置管理器
        try:
            if getattr(settings, 'CONFIG_MANAGER_AVAILABLE', False):
                get_unified_config = getattr(settings, 'get_unified_config', None)
                if get_unified_config:
                    timeout = get_unified_config('chat_platforms.feishu.timeout', 30)
                    return timeout
        except Exception as e:
            logger.debug(f"从统一配置获取飞书超时时间失败: {e}")
        
        # 回退到传统配置方式
        feishu_config = getattr(settings, 'FEISHU', {})
        return feishu_config.get('TIMEOUT', 30)
    
    def build_rich_text_message(
        self,
        case_name: str,
        sms_content: str,
        processed_at: datetime
    ) -> Dict[str, Any]:
        """
        构建飞书富文本消息
        
        Args:
            case_name: 案件名称
            sms_content: 短信内容
            processed_at: 处理时间
            
        Returns:
            飞书消息格式的字典
        """
        if not case_name:
            raise ValidationException("案件名称不能为空")
        if not sms_content:
            raise ValidationException("短信内容不能为空")
        if not processed_at:
            raise ValidationException("处理时间不能为空")
            
        # 格式化处理时间
        time_str = processed_at.strftime("%Y年%m月%d日 %H:%M:%S")
        
        # 构建富文本消息
        message = {
            "msg_type": "rich_text",
            "content": {
                "rich_text": {
                    "elements": [
                        {
                            "tag": "text",
                            "text": "📋 ",
                            "style": {
                                "bold": True
                            }
                        },
                        {
                            "tag": "text", 
                            "text": "法院短信处理完成",
                            "style": {
                                "bold": True,
                                "color": "blue"
                            }
                        },
                        {
                            "tag": "text",
                            "text": "\n\n"
                        },
                        {
                            "tag": "text",
                            "text": "📁 案件名称：",
                            "style": {
                                "bold": True
                            }
                        },
                        {
                            "tag": "text",
                            "text": case_name
                        },
                        {
                            "tag": "text",
                            "text": "\n\n"
                        },
                        {
                            "tag": "text",
                            "text": "📱 短信内容：",
                            "style": {
                                "bold": True
                            }
                        },
                        {
                            "tag": "text",
                            "text": f"\n{sms_content}"
                        },
                        {
                            "tag": "text",
                            "text": "\n\n"
                        },
                        {
                            "tag": "text",
                            "text": "⏰ 处理时间：",
                            "style": {
                                "bold": True
                            }
                        },
                        {
                            "tag": "text",
                            "text": time_str
                        }
                    ]
                }
            }
        }
        
        return message
    
    def send_sms_notification(
        self, 
        case_name: str,
        sms_content: str,
        document_path: str,
        processed_at: datetime
    ) -> Dict[str, Any]:
        """
        发送短信处理通知
        
        Args:
            case_name: 案件名称
            sms_content: 短信内容
            document_path: 文书文件路径
            processed_at: 处理时间
            
        Returns:
            发送结果字典，包含 success、message_sent、file_sent、error 字段
        """
        result = {
            "success": False,
            "message_sent": False,
            "file_sent": False,
            "error": None
        }
        
        if not self.webhook_url:
            error_msg = "未配置飞书 Webhook URL，跳过飞书通知"
            logger.warning(error_msg)
            result["error"] = error_msg
            return result
            
        try:
            # 构建并发送消息
            message = self.build_rich_text_message(case_name, sms_content, processed_at)
            message_success = self._send_message(message)
            result["message_sent"] = message_success
            
            if not message_success:
                result["error"] = "飞书消息发送失败"
                return result
                
            logger.info(f"飞书消息发送成功 - 案件: {case_name}")
            
            # 如果有文件且消息发送成功，尝试上传并发送文件
            if document_path and Path(document_path).exists():
                try:
                    file_key = self.upload_file(document_path)
                    if file_key:
                        # 发送文件消息
                        file_message = {
                            "msg_type": "file",
                            "content": {
                                "file_key": file_key
                            }
                        }
                        file_success = self._send_message(file_message)
                        result["file_sent"] = file_success
                        
                        if file_success:
                            logger.info(f"飞书文件发送成功 - 文件: {Path(document_path).name}")
                        else:
                            logger.warning(f"飞书文件消息发送失败 - 文件: {Path(document_path).name}")
                    else:
                        logger.warning(f"文件上传失败，跳过文件发送 - 文件: {Path(document_path).name}")
                        
                except Exception as file_error:
                    logger.error(f"处理文件上传时出错: {file_error}")
                    # 文件发送失败不影响整体成功状态
                    
            elif document_path:
                logger.warning(f"文件不存在，跳过文件发送: {document_path}")
                
            # 只要消息发送成功就认为通知成功
            result["success"] = True
            return result
            
        except ValidationException as ve:
            error_msg = f"参数验证失败: {ve}"
            logger.error(error_msg)
            result["error"] = error_msg
            return result
            
        except Exception as e:
            error_msg = f"发送飞书通知失败: {e}"
            logger.error(error_msg)
            result["error"] = error_msg
            return result
    
    def send_notification_simple(
        self, 
        case_name: str,
        sms_content: str,
        document_path: str,
        processed_at: datetime
    ) -> bool:
        """
        发送短信处理通知（简化版本，仅返回成功/失败）
        
        Args:
            case_name: 案件名称
            sms_content: 短信内容
            document_path: 文书文件路径
            processed_at: 处理时间
            
        Returns:
            是否发送成功
        """
        result = self.send_sms_notification(case_name, sms_content, document_path, processed_at)
        return result["success"]
    
    def upload_file(self, file_path: str) -> Optional[str]:
        """
        上传文件到飞书
        
        Args:
            file_path: 文件路径
            
        Returns:
            文件 key，失败返回 None
        """
        if not self.webhook_url:
            logger.warning("未配置飞书 Webhook URL，无法上传文件")
            return None
            
        file_path = Path(file_path)
        if not file_path.exists():
            logger.error(f"文件不存在: {file_path}")
            return None
            
        # 检查文件大小（飞书限制通常为 30MB）
        file_size = file_path.stat().st_size
        max_size = 30 * 1024 * 1024  # 30MB
        if file_size > max_size:
            logger.error(f"文件过大: {file_size} bytes，超过 30MB 限制")
            return None
            
        try:
            # 获取 app_access_token（需要配置 app_id 和 app_secret）
            app_access_token = self._get_app_access_token()
            if not app_access_token:
                logger.warning("无法获取 app_access_token，跳过文件上传")
                return None
                
            # 上传文件到飞书
            upload_url = "https://open.feishu.cn/open-apis/im/v1/files"
            
            with httpx.Client(timeout=self.timeout) as client:
                with open(file_path, 'rb') as f:
                    files = {
                        'file': (file_path.name, f, 'application/octet-stream')
                    }
                    data = {
                        'file_type': 'stream',
                        'file_name': file_path.name
                    }
                    headers = {
                        'Authorization': f'Bearer {app_access_token}'
                    }
                    
                    response = client.post(
                        upload_url,
                        files=files,
                        data=data,
                        headers=headers
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        if result.get("code") == 0:
                            file_key = result.get("data", {}).get("file_key")
                            logger.info(f"文件上传成功: {file_key}")
                            return file_key
                        else:
                            logger.error(f"文件上传失败: {result}")
                            return None
                    else:
                        logger.error(f"文件上传 API 调用失败: {response.status_code} - {response.text}")
                        return None
                        
        except Exception as e:
            logger.error(f"上传文件到飞书失败: {e}")
            return None
    
    def _get_app_access_token(self) -> Optional[str]:
        """
        获取飞书应用访问令牌
        
        Returns:
            访问令牌，失败返回 None
        """
        # 优先从 settings.FEISHU 读取
        feishu_config = getattr(settings, 'FEISHU', {})
        app_id = feishu_config.get('APP_ID')
        app_secret = feishu_config.get('APP_SECRET')
        
        # 兼容旧配置：从 COURT_SMS_PROCESSING 读取
        if not app_id or not app_secret:
            court_sms_config = getattr(settings, 'COURT_SMS_PROCESSING', {})
            app_id = app_id or court_sms_config.get('FEISHU_APP_ID')
            app_secret = app_secret or court_sms_config.get('FEISHU_APP_SECRET')
        
        if not app_id or not app_secret:
            logger.warning("未配置飞书 app_id 或 app_secret，无法获取访问令牌")
            return None
            
        try:
            token_url = "https://open.feishu.cn/open-apis/auth/v3/app_access_token/internal"
            
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    token_url,
                    json={
                        "app_id": app_id,
                        "app_secret": app_secret
                    },
                    headers={
                        "Content-Type": "application/json"
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get("code") == 0:
                        token = result.get("app_access_token")
                        logger.debug("获取飞书访问令牌成功")
                        return token
                    else:
                        logger.error(f"获取飞书访问令牌失败: {result}")
                        return None
                else:
                    logger.error(f"飞书令牌 API 调用失败: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            logger.error(f"获取飞书访问令牌异常: {e}")
            return None
    
    def _send_message(self, message: Dict[str, Any]) -> bool:
        """
        发送消息到飞书
        
        Args:
            message: 消息内容
            
        Returns:
            是否发送成功
        """
        if not self.webhook_url:
            return False
            
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    self.webhook_url,
                    json=message,
                    headers={
                        "Content-Type": "application/json"
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get("code") == 0:
                        logger.info("飞书消息发送成功")
                        return True
                    else:
                        logger.error(f"飞书消息发送失败: {result}")
                        return False
                else:
                    logger.error(f"飞书 API 调用失败: {response.status_code} - {response.text}")
                    return False
                    
        except Exception as e:
            logger.error(f"发送飞书消息异常: {e}")
            return False