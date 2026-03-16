"""法院短信、AI、爬虫等服务配置数据"""

from typing import Any

__all__ = ["get_court_sms_configs", "get_ai_configs", "get_scraper_configs"]


def get_court_sms_configs() -> list[dict[str, Any]]:
    """获取法院短信与文书送达配置项"""
    return []


def get_ai_configs() -> list[dict[str, Any]]:
    """获取 AI 配置项"""
    return [
        {
            "key": "AI_PROVIDER",
            "category": "ai",
            "description": "AI 服务提供商（ollama/siliconflow）",
            "value": "siliconflow",
            "is_secret": False,
        },
        {
            "key": "OLLAMA_MODEL",
            "category": "ai",
            "description": "Ollama 模型名称",
            "value": "qwen3.5:0.8b",
            "is_secret": False,
        },
        {
            "key": "OLLAMA_BASE_URL",
            "category": "ai",
            "description": "Ollama API 地址",
            "value": "http://localhost:11434",
            "is_secret": False,
        },
        {
            "key": "SILICONFLOW_API_KEY",
            "category": "ai",
            "description": "硅基流动 API Key",
            "value": "<SILICONFLOW_API_KEY>",
            "is_secret": True,
        },
        {
            # Faker
            "key": "SILICONFLOW_BASE_URL",
            "category": "ai",
            "description": "硅基流动 API 地址",
            "value": "https://api.siliconflow.cn/v1",
            "is_secret": False,
        },
        {
            "key": "SILICONFLOW_MODEL",
            "category": "ai",
            "description": "硅基流动模型名称",
            "value": "Pro/Qwen/Qwen3-0.6B",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_RECALL_WEIGHT_KEYWORD",
            "category": "ai",
            "description": "案例检索宽召回权重：关键词重合",
            "value": "0.18",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_RECALL_WEIGHT_SUMMARY",
            "category": "ai",
            "description": "案例检索宽召回权重：案情摘要重合",
            "value": "0.22",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_RECALL_WEIGHT_BM25",
            "category": "ai",
            "description": "案例检索宽召回权重：BM25代理分",
            "value": "0.22",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_RECALL_WEIGHT_VECTOR",
            "category": "ai",
            "description": "案例检索宽召回权重：向量相似分",
            "value": "0.18",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_RECALL_WEIGHT_PASSAGE",
            "category": "ai",
            "description": "案例检索宽召回权重：段落对齐分",
            "value": "0.16",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_RECALL_WEIGHT_METADATA",
            "category": "ai",
            "description": "案例检索宽召回权重：元信息提示分",
            "value": "0.04",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_PASSAGE_TOP_K",
            "category": "ai",
            "description": "案例检索段落精排：每案取前K段",
            "value": "5",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_PASSAGE_MAX_CHARS",
            "category": "ai",
            "description": "案例检索段落精排：全文切分最大字符数",
            "value": "18000",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_PASSAGE_PREVIEW_MAX_CHARS",
            "category": "ai",
            "description": "案例检索段落精排：单段送模最大字符数",
            "value": "1600",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_FEEDBACK_QUERY_LIMIT",
            "category": "ai",
            "description": "案例检索伪相关反馈：最多扩展检索式数",
            "value": "3",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_FEEDBACK_MIN_TERMS",
            "category": "ai",
            "description": "案例检索伪相关反馈：最少反馈词数量",
            "value": "3",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_FEEDBACK_MIN_SCORE_FLOOR",
            "category": "ai",
            "description": "案例检索伪相关反馈：最低分数下限",
            "value": "0.62",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_FEEDBACK_SCORE_MARGIN",
            "category": "ai",
            "description": "案例检索伪相关反馈：阈值回退边际",
            "value": "0.22",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_QUERY_VARIANT_ENABLED",
            "category": "ai",
            "description": "案例检索扩展：启用LLM查询变体",
            "value": "True",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_QUERY_VARIANT_MAX_COUNT",
            "category": "ai",
            "description": "案例检索扩展：LLM查询变体数量上限",
            "value": "2",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_QUERY_VARIANT_MODEL",
            "category": "ai",
            "description": "案例检索扩展：LLM查询变体模型（留空则沿用任务模型）",
            "value": "",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_DETAIL_CACHE_TTL_SECONDS",
            "category": "ai",
            "description": "案例检索缓存：案例详情缓存TTL（秒）",
            "value": "21600",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_SIMILARITY_CACHE_TTL_SECONDS",
            "category": "ai",
            "description": "案例检索缓存：相似度评分缓存TTL（秒）",
            "value": "86400",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_SEMANTIC_VECTOR_ENABLED",
            "category": "ai",
            "description": "案例检索宽召回：启用语义向量相似度",
            "value": "True",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_SEMANTIC_VECTOR_MODEL",
            "category": "ai",
            "description": "案例检索宽召回：语义向量模型（留空则回退字符向量）",
            "value": "BAAI/bge-m3",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_SEMANTIC_VECTOR_CACHE_TTL_SECONDS",
            "category": "ai",
            "description": "案例检索宽召回：语义向量缓存TTL（秒）",
            "value": "86400",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_DUAL_REVIEW_ENABLED",
            "category": "ai",
            "description": "案例检索精排：启用双模型复核",
            "value": "True",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_DUAL_REVIEW_MODEL",
            "category": "ai",
            "description": "案例检索精排：复核模型",
            "value": "Qwen/Qwen2.5-14B-Instruct",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_DUAL_REVIEW_PRIMARY_WEIGHT",
            "category": "ai",
            "description": "案例检索精排：主模型权重",
            "value": "0.62",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_DUAL_REVIEW_SECONDARY_WEIGHT",
            "category": "ai",
            "description": "案例检索精排：复核模型权重",
            "value": "0.38",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_DUAL_REVIEW_TRIGGER_FLOOR",
            "category": "ai",
            "description": "案例检索精排：触发双模型复核的最低分",
            "value": "0.60",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_DUAL_REVIEW_GAP_TOLERANCE",
            "category": "ai",
            "description": "案例检索精排：主复核分歧惩罚阈值",
            "value": "0.18",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_DUAL_REVIEW_REQUIRED_MIN",
            "category": "ai",
            "description": "案例检索精排：复核最低通过分",
            "value": "0.55",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_ONLINE_TUNING_ENABLED",
            "category": "ai",
            "description": "案例检索在线反馈：启用参数自动微调",
            "value": "True",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_ONLINE_MIN_SIMILARITY_DELTA",
            "category": "ai",
            "description": "案例检索在线反馈：执行阈值增量",
            "value": "0.0",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_ADAPTIVE_THRESHOLD_ENABLED",
            "category": "ai",
            "description": "案例检索精排：启用自适应阈值回收",
            "value": "True",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_ADAPTIVE_THRESHOLD_FLOOR",
            "category": "ai",
            "description": "案例检索精排：自适应阈值最低下限",
            "value": "0.76",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_ADAPTIVE_THRESHOLD_STEP",
            "category": "ai",
            "description": "案例检索精排：每轮下调阈值步长",
            "value": "0.025",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_ADAPTIVE_THRESHOLD_SCAN_INTERVAL",
            "category": "ai",
            "description": "案例检索精排：每扫描N篇无新增命中触发阈值下调",
            "value": "30",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_FEEDBACK_POSITIVE_COUNT",
            "category": "ai",
            "description": "案例检索在线反馈：真实命中计数",
            "value": "0",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_FEEDBACK_NEGATIVE_COUNT",
            "category": "ai",
            "description": "案例检索在线反馈：误命中计数",
            "value": "0",
            "is_secret": False,
        },
        {
            "key": "LEGAL_RESEARCH_FEEDBACK_MISSED_COUNT",
            "category": "ai",
            "description": "案例检索在线反馈：漏命中计数",
            "value": "0",
            "is_secret": False,
        },
    ]


def get_scraper_configs() -> list[dict[str, Any]]:
    """获取爬虫与 Token 配置项"""
    return [
        # ============ 爬虫配置 ============
        {
            "key": "SCRAPER_ENABLED",
            "category": "scraper",
            "description": "启用爬虫功能",
            "value": "True",
            "is_secret": False,
        },
        {"key": "SCRAPER_ENCRYPTION_KEY", "category": "scraper", "description": "爬虫加密密钥", "is_secret": True},
        {
            "key": "SCRAPER_HEADLESS",
            "category": "scraper",
            "description": "爬虫是否使用无头模式",
            "value": "True",
            "is_secret": False,
        },
        {
            "key": "SCRAPER_TIMEOUT",
            "category": "scraper",
            "description": "爬虫页面加载超时时间（秒）",
            "value": "60",
            "is_secret": False,
        },
        {
            "key": "SCRAPER_MAX_CONCURRENT",
            "category": "scraper",
            "description": "爬虫最大并发数",
            "value": "3",
            "is_secret": False,
        },
        {
            "key": "SCRAPER_RETRY_COUNT",
            "category": "scraper",
            "description": "爬虫失败重试次数",
            "value": "3",
            "is_secret": False,
        },
        {
            "key": "SCRAPER_DOWNLOAD_DIR",
            "category": "scraper",
            "description": "爬虫下载目录",
            "value": "/tmp/scraper_downloads",  # nosec B108
            "is_secret": False,
        },
        # ============ Token 获取配置 ============
        {
            "key": "TOKEN_AUTO_REFRESH_ENABLED",
            "category": "scraper",
            "description": "启用 Token 自动刷新",
            "value": "True",
            "is_secret": False,
        },
        {
            "key": "TOKEN_REFRESH_INTERVAL",
            "category": "scraper",
            "description": "Token 刷新间隔（分钟）",
            "value": "30",
            "is_secret": False,
        },
        {
            "key": "TOKEN_CACHE_TTL",
            "category": "scraper",
            "description": "Token 缓存有效期（秒）",
            "value": "3600",
            "is_secret": False,
        },
    ]
