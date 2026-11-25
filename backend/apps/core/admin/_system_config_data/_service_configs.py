"""法院短信、AI、企业数据、爬虫等服务配置数据"""

import os
from typing import Any

__all__ = [
    "get_court_sms_configs",
    "get_ai_configs",
    "get_enterprise_data_configs",
    "get_scraper_configs",
    "get_ocr_configs",
]


def get_court_sms_configs() -> list[dict[str, Any]]:
    """获取法院短信与文书送达配置项"""
    return []


def get_ai_configs() -> list[dict[str, Any]]:
    """获取 AI 配置项（仅保留用户必须配置的项，其余由代码默认值兜底）"""
    return [
        {
            "key": "OPENAI_COMPATIBLE_API_KEY",
            "category": "ai",
            "description": "OpenAI-compatible API Key（兼容旧配置，单 Key）。多平台 / 多 Key 并发请在「AI 平台」管理页配置",
            "value": "<OPENAI_COMPATIBLE_API_KEY>",
            "is_secret": True,
        },
        {
            "key": "OPENAI_COMPATIBLE_BASE_URL",
            "category": "ai",
            "description": "OpenAI-compatible API 地址（兼容旧配置，kimi26 vLLM）。多平台请在「AI 平台」管理页配置",
            # 默认网关 URL 可经 LLM_DEFAULT_BASE_URL 环境变量替换（回退值保持原网关，行为零变化）
            "value": os.environ.get("LLM_DEFAULT_BASE_URL", "http://116.196.92.175:8001/v1"),
            "is_secret": False,
        },
        {
            "key": "OPENAI_COMPATIBLE_DEFAULT_MODEL",
            "category": "ai",
            "description": "OpenAI-compatible 默认模型名称（兼容旧配置）",
            "value": "kimi26",
            "is_secret": False,
        },
    ]


def get_scraper_configs() -> list[dict[str, Any]]:
    """获取爬虫配置项（仅保留用户必须配置的项）"""
    return [
        {"key": "SCRAPER_ENCRYPTION_KEY", "category": "scraper", "description": "爬虫加密密钥", "is_secret": True},
        {
            "key": "PLAYWRIGHT_HEADED",
            "category": "scraper",
            "description": "Playwright 浏览器有头模式（true=显示浏览器窗口，便于调试；false=无头后台运行）",
            "value": "true",
            "is_secret": False,
        },
    ]


def get_enterprise_data_configs() -> list[dict[str, Any]]:
    """获取企业数据配置项（仅保留用户必须配置的项）"""
    return [
        {
            "key": "TIANYANCHA_MCP_API_KEY",
            "category": "enterprise_data",
            "description": "天眼查 MCP API Key（Bearer Token，支持多 Key；每行一个）",
            "value": "",
            "is_secret": True,
        },
        {
            "key": "QCC_MCP_API_KEY",
            "category": "enterprise_data",
            "description": "企查查 MCP API Key（Bearer Token，支持多 Key；每行一个）",
            "value": "",
            "is_secret": True,
        },
        # 元典可配的只有 key 与 agent 侧 MCP 总开关：平台地址 / MCP Server 清单 / 每 key
        # 并发上限都是代码常量，见 ``apps/core/services/yuandian_settings.py``。别把这三条
        # 加回默认配置——它们不随部署变，落库只会多出一个「没点过初始化就是空」的失败面。
        {
            "key": "YUANDIAN_API_KEYS",
            "category": "enterprise_data",
            "description": "元典 API Key（Bearer Token；支持多 Key，每行一个）",
            "value": "",
            "is_secret": True,
        },
        {
            "key": "YUANDIAN_MCP_ENABLED",
            "category": "enterprise_data",
            "description": (
                "AI 助手是否挂载元典 MCP 工具（true=挂载 / false=不挂载）。工具调用会把案情发给外部的"
                "元典服务；不影响检索任务里显式选择的元典数据源"
            ),
            "value": "true",
            "is_secret": False,
        },
    ]


def get_ocr_configs() -> list[dict[str, Any]]:
    """获取 OCR 服务配置项"""
    return [
        {
            "key": "OCR_PROVIDER",
            "category": "ocr",
            "description": "OCR 引擎选择（local=本地 RapidOCR / paddleocr_api=百度 PaddleOCR API）",
            "value": "paddleocr_api",
            "is_secret": False,
        },
        {
            "key": "PADDLEOCR_API_MODEL",
            "category": "ocr",
            "description": (
                "PaddleOCR API 模型选择（"
                "pp_ocrv6=纯文字OCR-快但生僻字易错, "
                "pp_structure_v3=文档结构化-适合表格/版面分析, "
                "paddleocr_vl=版面分析+OCR-适合复杂文档/合同, "
                "paddleocr_vl_1_5=高精度版面分析-适合法律文书/密集排版文档, "
                "paddleocr_vl_1_6=最新版-生僻字/印章增强，推荐法律文书使用）"
            ),
            "value": "paddleocr_vl_1_6",
            "is_secret": False,
        },
        {
            "key": "PADDLEOCR_JOB_API_URL",
            "category": "ocr",
            "description": "PaddleOCR v2 异步 Job API 地址（所有模型共用，靠 model 参数区分产品线）",
            "value": "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs",
            "is_secret": False,
        },
        {
            "key": "PADDLEOCR_API_TOKEN",
            "category": "ocr",
            "description": "PaddleOCR API Token（Authorization: token {TOKEN}）",
            "value": "",
            "is_secret": True,
        },
        {
            "key": "PDF_SPLIT_SEGMENT_STRATEGY",
            "category": "ocr",
            "description": (
                "材料预处理的分段策略：batch=逐批摘要（默认，稳、大卷宗不会超时）；"
                "wholebook=整本一次看完再切（更准，但大卷宗可能撞 LLM 超时，失败会自动退回 batch）；"
                "wholebook_cross=两条都跑，边界不一致的段标「两种切法不一致」交人工裁定（多一次 LLM 调用）"
            ),
            "value": "batch",
            "is_secret": False,
        },
        {
            "key": "DEEPSEEK_OCR_API_KEY",
            "category": "ocr",
            "description": (
                "DeepSeek OCR API Key（文件解析/OCR，按页计费 1.5 元/1000 页）。"
                "填了之后「解析平台」里会多出一个可选的 DeepSeek 引擎；"
                "auto 模式下它排在 MinerU/Textin 之后作为兜底，想让它当首选请锁定它。"
            ),
            "value": "",
            "is_secret": True,
        },
        {
            "key": "DEEPSEEK_OCR_API_URL",
            "category": "ocr",
            "description": "DeepSeek OCR 接口地址（一般不用改）",
            "value": "https://api.deepseek.com/v1/tools/ocr",
            "is_secret": False,
        },
        # ── 多引擎分歧裁定（Jev 判别式打分器）─────────────────────────────────
        # 用途：两个引擎对**同一个字段**读出不同值时，把「裁块图 + 各候选文本」送打分器，
        # 它返回「这段文本是该图正确转写的概率」。只认相对比较，不认绝对阈值。
        # 取证与五条硬结论见 docs/analysis/multi-engine-ocr-brief-2026-11-25.md §11。
        #
        # 注意：组件已实现（disagreement_judge.py / field_verification.py），但**尚未接线到
        # 主链**——现在打开开关不会产生任何效果，要等 pipeline 的分歧点调用它。
        {
            "key": "OCR_JUDGE_ENABLED",
            "category": "ocr",
            "description": (
                "多引擎分歧是否用第三方打分器裁定（0=关，默认；1=开）。"
                "关着时与引入该功能前逐位一致：分歧只进人工抽屉。"
                "打开前需先填 OCR_JUDGE_API_KEY，且主链已接线（否则开关无效果）。"
            ),
            "value": "0",
            "is_secret": False,
        },
        {
            "key": "OCR_JUDGE_API_URL",
            "category": "ocr",
            "description": "分歧裁定打分接口（OpenAI 兼容 chat/completions，一般不用改）",
            "value": "https://api.modelbest.cn/v1/chat/completions",
            "is_secret": False,
        },
        {
            "key": "OCR_JUDGE_API_KEY",
            "category": "ocr",
            "description": (
                "分歧裁定打分器的 API Key（Bearer Token）。留空则判定一律落人工；"
                "敏感项，加密存储。供应商侧政策：可读分辨率下的证件图像会被拒"
                "（content_policy_violation），所以证件/账号类字段不走此路，见 L1 校验位。"
            ),
            "value": "",
            "is_secret": True,
        },
        {
            "key": "OCR_JUDGE_MODEL",
            "category": "ocr",
            "description": "打分模型名（判别式：给图 + 候选文本，只回概率，不生成新文本）",
            "value": "MiniCPM-OCR-Jev",
            "is_secret": False,
        },
        {
            "key": "OCR_JUDGE_MAX_CONCURRENCY",
            "category": "ocr",
            "description": (
                "打分请求的进程内并发上限。默认 2：实测 4 并发立即被限流（429），2 稳定。"
                "调高不会更快，只会把请求打回退避重试。"
            ),
            "value": "2",
            "is_secret": False,
        },
        {
            "key": "OCR_JUDGE_PROB_FLOOR",
            "category": "ocr",
            "description": (
                "胜者最低分。低于它就判「两个都不像图上的字」交人工。"
                "默认 0.05 而不是 0.5：实测真值分数可以是 0.158（模糊证件块），"
                "绝对值不可比，只有相对倍数可依赖。"
            ),
            "value": "0.05",
            "is_secret": False,
        },
        {
            "key": "OCR_JUDGE_RATIO_MIN",
            "category": "ocr",
            "description": (
                "胜者 / 次高分的倍数下限，低于它交人工。默认 10：实测真错案例的倍数在"
                "55–1900 倍之间，而汉字形近字的错值也能拿 0.58（真值 0.994，仅 1.7 倍），"
                "阈值定低了会把形近字误采信。"
            ),
            "value": "10",
            "is_secret": False,
        },
        {
            "key": "OCR_JUDGE_TIMEOUT_SECONDS",
            "category": "ocr",
            "description": "单次打分请求超时（秒）。实测中位 1.2s、最慢 10s，留足余量给拥塞",
            "value": "180",
            "is_secret": False,
        },
        {
            "key": "DEEPSEEK_OCR_PURPOSE",
            "category": "ocr",
            "description": (
                "DeepSeek 解析模式：text_recognition=只取文字（快、便宜、表格给出 HTML）；"
                "rich_layout_recognition=带版面块与坐标（慢、退化率更高，但「原文坐标对照」需要它）"
            ),
            "value": "text_recognition",
            "is_secret": False,
        },
    ]
