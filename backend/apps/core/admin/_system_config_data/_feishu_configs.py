"""飞书、钉钉、企业微信配置数据"""

from typing import Any

__all__ = ["get_feishu_configs", "get_dingtalk_configs", "get_wechat_work_configs"]


def get_feishu_configs() -> list[dict[str, Any]]:
    """获取飞书配置项"""
    return [
        # ============ 飞书配置 ============
        {"key": "FEISHU_APP_ID", "category": "feishu", "description": "飞书应用 App ID", "is_secret": False},
        {"key": "FEISHU_APP_SECRET", "category": "feishu", "description": "飞书应用 App Secret", "is_secret": True},
        {
            "key": "FEISHU_DEFAULT_OWNER_ID",
            "category": "feishu",
            "description": "飞书群聊默认群主 ID（open_id 格式：ou_xxxxxx）",
            "is_secret": False,
        },
        {
            "key": "FEISHU_WEBHOOK_URL",
            "category": "feishu",
            "description": "飞书 Webhook URL（可选，用于传统通知）",
            "is_secret": False,
        },
        {
            "key": "FEISHU_TIMEOUT",
            "category": "feishu",
            "description": "飞书 API 超时时间（秒）",
            "value": "30",
            "is_secret": False,
        },
        # ============ 飞书群聊配置 ============
        {
            "key": "FEISHU_CHAT_CASE_GROUP",
            "category": "feishu",
            "description": "案件通知群名称",
            "value": "案件通知群",
            "is_secret": False,
        },
        {
            "key": "FEISHU_CHAT_DOCUMENT_GROUP",
            "category": "feishu",
            "description": "文书通知群名称",
            "value": "法院文书通知群",
            "is_secret": False,
        },
        {
            "key": "FEISHU_CHAT_SMS_GROUP",
            "category": "feishu",
            "description": "短信通知群名称",
            "value": "法院短信通知群",
            "is_secret": False,
        },
        {
            "key": "FEISHU_CHAT_ALERT_GROUP",
            "category": "feishu",
            "description": "系统告警群名称",
            "value": "系统告警群",
            "is_secret": False,
        },
        {
            "key": "FEISHU_CHAT_CONTRACT_GROUP",
            "category": "feishu",
            "description": "合同通知群名称",
            "value": "合同通知群",
            "is_secret": False,
        },
        {
            "key": "FEISHU_CHAT_FINANCE_GROUP",
            "category": "feishu",
            "description": "财务通知群名称",
            "value": "财务通知群",
            "is_secret": False,
        },
        # ============ 群聊名称模板配置 ============
        {
            "key": "CASE_CHAT_NAME_TEMPLATE",
            "category": "feishu",
            "description": (
                "案件群聊名称模板，支持占位符：{stage}（案件阶段）、{case_name}（案件名称）、{case_type}（案件类型）"
            ),
            "value": "【{stage}】{case_name}",
            "is_secret": False,
        },
        {
            "key": "CASE_CHAT_DEFAULT_STAGE",
            "category": "feishu",
            "description": "案件阶段为空时的默认显示文本",
            "value": "待定",
            "is_secret": False,
        },
        {
            "key": "CASE_CHAT_NAME_MAX_LENGTH",
            "category": "feishu",
            "description": "群聊名称最大长度（飞书限制为60）",
            "value": "60",
            "is_secret": False,
        },
        # ============ 飞书高级配置 ============
        {
            "key": "FEISHU_TEST_MODE",
            "category": "feishu",
            "description": "飞书测试模式（启用后不会真正发送消息）",
            "value": "false",
            "is_secret": False,
        },
        {"key": "FEISHU_TEST_OWNER_ID", "category": "feishu", "description": "飞书测试群主 ID", "is_secret": False},
        {
            "key": "FEISHU_OWNER_VALIDATION_ENABLED",
            "category": "feishu",
            "description": "启用群主验证",
            "value": "true",
            "is_secret": False,
        },
        {
            "key": "FEISHU_OWNER_RETRY_ENABLED",
            "category": "feishu",
            "description": "启用群主重试",
            "value": "true",
            "is_secret": False,
        },
        {
            "key": "FEISHU_OWNER_MAX_RETRIES",
            "category": "feishu",
            "description": "群主设置最大重试次数",
            "value": "3",
            "is_secret": False,
        },
        {
            "key": "FEISHU_MESSAGE_BATCH_SIZE",
            "category": "feishu",
            "description": "飞书消息批量发送数量",
            "value": "10",
            "is_secret": False,
        },
        {
            "key": "FEISHU_FILE_UPLOAD_MAX_SIZE",
            "category": "feishu",
            "description": "飞书文件上传最大大小（MB）",
            "value": "30",
            "is_secret": False,
        },
    ]


def get_dingtalk_configs() -> list[dict[str, Any]]:
    """获取钉钉配置项"""
    return [
        {"key": "DINGTALK_APP_KEY", "category": "dingtalk", "description": "钉钉应用 App Key", "is_secret": False},
        {
            "key": "DINGTALK_APP_SECRET",
            "category": "dingtalk",
            "description": "钉钉应用 App Secret",
            "is_secret": True,
        },
        {"key": "DINGTALK_AGENT_ID", "category": "dingtalk", "description": "钉钉应用 Agent ID", "is_secret": False},
        {
            "key": "DINGTALK_TIMEOUT",
            "category": "dingtalk",
            "description": "钉钉 API 超时时间（秒）",
            "value": "30",
            "is_secret": False,
        },
        {
            "key": "DINGTALK_CHAT_CASE_GROUP",
            "category": "dingtalk",
            "description": "钉钉案件通知群名称",
            "value": "案件通知群",
            "is_secret": False,
        },
        {
            "key": "DINGTALK_CHAT_ALERT_GROUP",
            "category": "dingtalk",
            "description": "钉钉系统告警群名称",
            "value": "系统告警群",
            "is_secret": False,
        },
    ]


def get_wechat_work_configs() -> list[dict[str, Any]]:
    """获取企业微信配置项"""
    return [
        {
            "key": "WECHAT_WORK_CORP_ID",
            "category": "wechat_work",
            "description": "企业微信 Corp ID",
            "is_secret": False,
        },
        {
            "key": "WECHAT_WORK_AGENT_ID",
            "category": "wechat_work",
            "description": "企业微信 Agent ID",
            "is_secret": False,
        },
        {
            "key": "WECHAT_WORK_SECRET",
            "category": "wechat_work",
            "description": "企业微信应用 Secret",
            "is_secret": True,
        },
        {
            "key": "WECHAT_WORK_TIMEOUT",
            "category": "wechat_work",
            "description": "企业微信 API 超时时间（秒）",
            "value": "30",
            "is_secret": False,
        },
        {
            "key": "WECHAT_WORK_CHAT_CASE_GROUP",
            "category": "wechat_work",
            "description": "企业微信案件通知群名称",
            "value": "案件通知群",
            "is_secret": False,
        },
    ]
