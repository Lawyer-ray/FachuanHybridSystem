"""第三方服务配置注册"""

from .field import ConfigField


def register_service_configs(registry: dict[str, ConfigField]) -> None:
    registry["services.ollama.model"] = ConfigField(
        name="services.ollama.model",
        type=str,
        default="qwen2.5:7b",
        env_var="OLLAMA_MODEL",
        description="Ollama 模型名称",
    )
    registry["services.ollama.base_url"] = ConfigField(
        name="services.ollama.base_url",
        type=str,
        default="http://localhost:11434",
        env_var="OLLAMA_BASE_URL",
        description="Ollama API 基础 URL",
    )
    registry["services.ollama.timeout"] = ConfigField(
        name="services.ollama.timeout",
        type=int,
        default=60,
        min_value=1,
        max_value=600,
        description="Ollama API 超时时间（秒）",
    )
    registry["services.sms.document_title_extraction_limit"] = ConfigField(
        name="services.sms.document_title_extraction_limit",
        type=int,
        default=50,
        min_value=20,
        max_value=5000,
        description="短信文书重命名场景的标题提取文本长度（字符）",
    )
    registry["services.scraper.encryption_key"] = ConfigField(
        name="services.scraper.encryption_key",
        type=str,
        required=False,
        sensitive=True,
        env_var="SCRAPER_ENCRYPTION_KEY",
        description="爬虫加密密钥",
    )
    registry["services.insurance.list_url"] = ConfigField(
        name="services.insurance.list_url",
        type=str,
        default="https://baoquan.court.gov.cn/wsbq/ssbq/api/commoncodepz",
        description="保险公司列表 API URL",
    )
    registry["services.insurance.premium_query_url"] = ConfigField(
        name="services.insurance.premium_query_url",
        type=str,
        default="https://baoquan.court.gov.cn/wsbq/commonapi/api/policy/premium",
        description="保险费率查询 API URL",
    )
    registry["services.insurance.default_timeout"] = ConfigField(
        name="services.insurance.default_timeout",
        type=int,
        default=30,
        min_value=1,
        max_value=300,
        description="保险服务默认超时时间（秒）",
    )
    registry["services.insurance.max_connections"] = ConfigField(
        name="services.insurance.max_connections",
        type=int,
        default=10,
        min_value=1,
        max_value=100,
        description="保险服务最大连接数",
    )
