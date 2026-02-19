"""业务功能、日志、验证配置注册"""

from .field import ConfigField


def register_feature_configs(registry: dict[str, ConfigField]) -> None:
    # 案件聊天
    registry["features.case_chat.default_platform"] = ConfigField(
        name="features.case_chat.default_platform", type=str, default="feishu",
        choices=["feishu", "dingtalk", "wechat_work", "telegram", "slack"],
        description="默认聊天平台",
    )
    registry["features.case_chat.auto_create_on_push"] = ConfigField(
        name="features.case_chat.auto_create_on_push", type=bool, default=True,
        description="推送时自动创建聊天群",
    )
    registry["features.case_chat.default_owner_id"] = ConfigField(
        name="features.case_chat.default_owner_id", type=str,
        env_var="CASE_CHAT_DEFAULT_OWNER_ID", description="案件聊天默认群主 ID",
    )
    # 法院短信
    registry["features.court_sms.max_retries"] = ConfigField(
        name="features.court_sms.max_retries", type=int, default=3,
        min_value=0, max_value=10, description="法院短信最大重试次数",
    )
    registry["features.court_sms.retry_delay"] = ConfigField(
        name="features.court_sms.retry_delay", type=int, default=60,
        min_value=1, max_value=3600, description="法院短信重试延迟（秒）",
    )
    registry["features.court_sms.auto_recovery"] = ConfigField(
        name="features.court_sms.auto_recovery", type=bool, default=True,
        description="是否启用自动恢复",
    )
    # 文档处理
    registry["features.document_processing.default_text_limit"] = ConfigField(
        name="features.document_processing.default_text_limit", type=int, default=5000,
        min_value=100, max_value=100000, description="默认文本提取限制（字符数）",
    )
    registry["features.document_processing.max_text_limit"] = ConfigField(
        name="features.document_processing.max_text_limit", type=int, default=50000,
        min_value=1000, max_value=1000000, description="最大文本提取限制（字符数）",
    )
    registry["features.document_processing.default_preview_page"] = ConfigField(
        name="features.document_processing.default_preview_page", type=int, default=1,
        min_value=1, description="默认预览页数",
    )
    registry["features.document_processing.max_preview_pages"] = ConfigField(
        name="features.document_processing.max_preview_pages", type=int, default=10,
        min_value=1, max_value=100, description="最大预览页数",
    )
    # 日志
    registry["logging.file_max_size"] = ConfigField(
        name="logging.file_max_size", type=int, default=10485760,
        min_value=1048576, max_value=104857600, description="日志文件最大大小（字节）",
    )
    registry["logging.api_backup_count"] = ConfigField(
        name="logging.api_backup_count", type=int, default=5,
        min_value=1, max_value=50, description="API 日志文件备份数量",
    )
    registry["logging.error_backup_count"] = ConfigField(
        name="logging.error_backup_count", type=int, default=10,
        min_value=1, max_value=50, description="错误日志文件备份数量",
    )
    registry["logging.sql_backup_count"] = ConfigField(
        name="logging.sql_backup_count", type=int, default=3,
        min_value=1, max_value=20, description="SQL 日志文件备份数量",
    )
    _log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    registry["logging.console_level"] = ConfigField(
        name="logging.console_level", type=str, default="INFO",
        choices=_log_levels, description="控制台日志级别",
    )
    registry["logging.file_level"] = ConfigField(
        name="logging.file_level", type=str, default="INFO",
        choices=_log_levels, description="文件日志级别",
    )
    registry["logging.error_level"] = ConfigField(
        name="logging.error_level", type=str, default="ERROR",
        choices=_log_levels, description="错误日志级别",
    )
    registry["logging.django_level"] = ConfigField(
        name="logging.django_level", type=str, default="INFO",
        choices=_log_levels, description="Django 日志级别",
    )
    registry["logging.request_level"] = ConfigField(
        name="logging.request_level", type=str, default="WARNING",
        choices=_log_levels, description="Django 请求日志级别",
    )
    registry["logging.apps_level"] = ConfigField(
        name="logging.apps_level", type=str, default="INFO",
        choices=_log_levels, description="应用日志级别",
    )
    registry["logging.root_level"] = ConfigField(
        name="logging.root_level", type=str, default="WARNING",
        choices=_log_levels, description="根日志级别",
    )
    # 分页
    registry["pagination.default_page_size"] = ConfigField(
        name="pagination.default_page_size", type=int, default=20,
        min_value=1, max_value=1000, description="默认分页大小",
    )
    registry["pagination.max_page_size"] = ConfigField(
        name="pagination.max_page_size", type=int, default=100,
        min_value=1, max_value=10000, description="最大分页大小",
    )
    # 验证规则
    registry["validation.max_amount"] = ConfigField(
        name="validation.max_amount", type=float, default=10000000.0,
        min_value=0.01, description="最大金额限制",
    )
    registry["validation.max_string_length"] = ConfigField(
        name="validation.max_string_length", type=int, default=1000,
        min_value=1, max_value=100000, description="字符串最大长度限制",
    )
    registry["validation.max_file_size"] = ConfigField(
        name="validation.max_file_size", type=int, default=52428800,
        min_value=1024, max_value=1073741824, description="文件上传最大大小（字节）",
    )
    registry["validation.name_max_length"] = ConfigField(
        name="validation.name_max_length", type=int, default=255,
        min_value=1, max_value=1000, description="姓名/名称字段最大长度",
    )
    registry["validation.phone_max_length"] = ConfigField(
        name="validation.phone_max_length", type=int, default=20,
        min_value=1, max_value=50, description="电话号码字段最大长度",
    )
    registry["validation.address_max_length"] = ConfigField(
        name="validation.address_max_length", type=int, default=255,
        min_value=1, max_value=1000, description="地址字段最大长度",
    )
    registry["validation.id_number_max_length"] = ConfigField(
        name="validation.id_number_max_length", type=int, default=64,
        min_value=1, max_value=100, description="身份证号/统一社会信用代码最大长度",
    )
    registry["validation.decimal_max_digits"] = ConfigField(
        name="validation.decimal_max_digits", type=int, default=15,
        min_value=1, max_value=30, description="金额字段最大位数",
    )
    registry["validation.decimal_places"] = ConfigField(
        name="validation.decimal_places", type=int, default=2,
        min_value=0, max_value=10, description="金额字段小数位数",
    )
    registry["validation.text_extraction_limit"] = ConfigField(
        name="validation.text_extraction_limit", type=int, default=5000,
        min_value=100, max_value=100000, description="文本提取默认限制（字符数）",
    )
    registry["validation.max_text_extraction_limit"] = ConfigField(
        name="validation.max_text_extraction_limit", type=int, default=50000,
        min_value=1000, max_value=1000000, description="文本提取最大限制（字符数）",
    )
    registry["validation.screenshot_limit"] = ConfigField(
        name="validation.screenshot_limit", type=int, default=5,
        min_value=1, max_value=20, description="调试截图收集数量限制",
    )
    # Steering
    registry["steering.conditional_loading.enabled"] = ConfigField(
        name="steering.conditional_loading.enabled", type=bool, default=True,
        description="是否启用条件加载",
    )
    registry["steering.conditional_loading.cache_ttl"] = ConfigField(
        name="steering.conditional_loading.cache_ttl", type=int, default=3600,
        min_value=60, max_value=86400, description="条件加载缓存 TTL（秒）",
    )
    registry["steering.performance.load_threshold_ms"] = ConfigField(
        name="steering.performance.load_threshold_ms", type=int, default=100,
        min_value=1, max_value=10000, description="加载性能阈值（毫秒）",
    )
    registry["steering.performance.warn_threshold_ms"] = ConfigField(
        name="steering.performance.warn_threshold_ms", type=int, default=500,
        min_value=1, max_value=10000, description="性能警告阈值（毫秒）",
    )
