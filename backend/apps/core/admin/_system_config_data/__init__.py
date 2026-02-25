"""系统配置 Admin 的默认配置数据和环境变量映射"""

from typing import Any

from ._env_mappings import get_env_mappings
from ._feishu_configs import get_dingtalk_configs, get_feishu_configs, get_wechat_work_configs
from ._general_configs import get_general_configs
from ._service_configs import get_ai_configs, get_court_sms_configs, get_scraper_configs

__all__ = ["get_default_configs", "get_env_mappings"]


def get_default_configs() -> list[dict[str, Any]]:
    """获取默认配置项列表 - 包含核心必需配置"""
    return get_feishu_configs() + get_ai_configs() + get_court_sms_configs()
