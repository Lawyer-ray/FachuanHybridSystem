# FeishuBotService 使用指南

## 概述

FeishuBotService 是法院短信处理系统的飞书通知组件，负责将处理结果发送到飞书群聊。

## 配置

### 环境变量配置

```bash
# 飞书机器人 Webhook URL（必需）
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook-token

# 飞书应用凭证（文件上传功能需要）
FEISHU_APP_ID=cli_your_app_id
FEISHU_APP_SECRET=your_app_secret
```

### Django Settings 配置

```python
# settings.py
COURT_SMS_PROCESSING = {
    "FEISHU_WEBHOOK_URL": os.getenv("FEISHU_WEBHOOK_URL"),
    "FEISHU_APP_ID": os.getenv("FEISHU_APP_ID"),
    "FEISHU_APP_SECRET": os.getenv("FEISHU_APP_SECRET"),
}
```

## 基本使用

### 1. 创建服务实例

```python
from apps.automation.services.sms.feishu_bot_service import FeishuBotService

# 使用配置中的 webhook URL
service = FeishuBotService()

# 或者直接指定 webhook URL
service = FeishuBotService(webhook_url="https://your.webhook.url")
```

### 2. 发送通知

```python
from datetime import datetime

# 发送完整通知（包含消息和文件）
result = service.send_sms_notification(
    case_name="广州市鸡鸡百货有限公司诉某某案",
    sms_content="【佛山市禅城区人民法院】法穿你好，请查收执行裁定书...",
    document_path="/path/to/document.pdf",
    processed_at=datetime.now()
)

# 检查发送结果
if result["success"]:
    print("通知发送成功")
    print(f"消息发送: {result['message_sent']}")
    print(f"文件发送: {result['file_sent']}")
else:
    print(f"通知发送失败: {result['error']}")
```

### 3. 仅发送消息（无文件）

```python
# 简化版本，仅返回成功/失败
success = service.send_notification_simple(
    case_name="测试案件",
    sms_content="测试短信内容",
    document_path=None,  # 无文件
    processed_at=datetime.now()
)

if success:
    print("通知发送成功")
else:
    print("通知发送失败")
```

## 高级功能

### 1. 自定义消息格式

```python
# 构建自定义富文本消息
message = service.build_rich_text_message(
    case_name="案件名称",
    sms_content="短信内容",
    processed_at=datetime.now()
)

# 发送自定义消息
success = service._send_message(message)
```

### 2. 文件上传

```python
# 单独上传文件
file_key = service.upload_file("/path/to/document.pdf")

if file_key:
    # 发送文件消息
    file_message = {
        "msg_type": "file",
        "content": {
            "file_key": file_key
        }
    }
    service._send_message(file_message)
```

## 消息格式示例

发送的飞书消息格式如下：

```
📋 法院短信处理完成

📁 案件名称：广州市鸡鸡百货有限公司诉某某案

📱 短信内容：
【佛山市禅城区人民法院】法穿你好，请查收执行裁定书...

⏰ 处理时间：2025年12月14日 10:30:00
```

## 错误处理

### 常见错误及解决方案

1. **未配置 Webhook URL**
   ```
   错误：未配置飞书 Webhook URL，跳过飞书通知
   解决：设置 FEISHU_WEBHOOK_URL 环境变量
   ```

2. **文件过大**
   ```
   错误：文件过大: xxx bytes，超过 30MB 限制
   解决：压缩文件或分割文件
   ```

3. **飞书 API 调用失败**
   ```
   错误：飞书 API 调用失败: 400 - Bad Request
   解决：检查 Webhook URL 是否正确，检查消息格式
   ```

4. **无法获取访问令牌**
   ```
   错误：无法获取 app_access_token，跳过文件上传
   解决：配置 FEISHU_APP_ID 和 FEISHU_APP_SECRET
   ```

## 集成示例

### 在 CourtSMSService 中使用

```python
from apps.automation.services.sms.feishu_bot_service import FeishuBotService

class CourtSMSService:
    def __init__(self):
        self.feishu_bot = FeishuBotService()
    
    def process_sms_complete(self, sms: CourtSMS, document_path: str):
        """短信处理完成后发送飞书通知"""
        if sms.case:
            result = self.feishu_bot.send_sms_notification(
                case_name=sms.case.name,
                sms_content=sms.content,
                document_path=document_path,
                processed_at=datetime.now()
            )
            
            # 更新短信记录
            if result["success"]:
                sms.feishu_sent_at = datetime.now()
                sms.feishu_error = None
            else:
                sms.feishu_error = result["error"]
            
            sms.save()
```

## 测试

### 单元测试示例

```python
import pytest
from unittest.mock import Mock, patch
from apps.automation.services.sms.feishu_bot_service import FeishuBotService

def test_send_notification():
    with patch('apps.automation.services.sms.feishu_bot_service.httpx.Client') as mock_client:
        # Mock 成功响应
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 0}
        
        mock_client_instance = Mock()
        mock_client_instance.post.return_value = mock_response
        mock_client.return_value.__enter__.return_value = mock_client_instance
        
        # 测试发送通知
        service = FeishuBotService(webhook_url="https://test.url")
        result = service.send_sms_notification(
            "案件", "内容", None, datetime.now()
        )
        
        assert result["success"] is True
```

## 注意事项

1. **文件大小限制**：飞书文件上传限制为 30MB
2. **网络超时**：默认超时时间为 30 秒
3. **错误恢复**：文件上传失败不影响消息发送成功状态
4. **配置优先级**：直接传入的 webhook_url > Django settings > 环境变量
5. **日志记录**：所有操作都会记录详细日志，便于调试

## 相关文档

- [飞书机器人开发文档](https://open.feishu.cn/document/ukTMukTMukTM/ucTM5YjL3ETO24yNxkjN)
- [飞书文件上传 API](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/file/create)
- [Court SMS Processing 设计文档](../.kiro/specs/court-sms-processing/design.md)