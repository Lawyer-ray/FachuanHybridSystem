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
        # 只有这两项进配置表：**因部署而异**的才是配置（key、开关）。接口地址、模型名、
        # 并发上限、超时、两个阈值都是实测出来的工程常数，留在
        # disagreement_judge.py 的模块常量里——写进 admin 只会给「随手调松阈值」开门，
        # 而且调松是静默生效的（不报错，只是把更多错值采信成对的）。
        #
        # 两级门禁的语义见 `dual_engine_runner.py`（judge_requested / judge_effective）：
        # 本项是**部署级总闸**，任务级开关是 `PdfSplitJob.ocr_judge_enabled`，两者都过才生效。
        # 缺 key 时按未启用处理并打 `ocr_judge_enabled_without_key` warning。
        {
            "key": "OCR_JUDGE_ENABLED",
            "category": "ocr",
            "description": (
                "多引擎分歧是否用第三方打分器自动裁定（0=关，默认；1=开）。"
                "这是**部署级总闸**：关着或缺 Key 时一条都不判，分歧全部进人工清单。"
                "与任务级开关（材料预处理 → 自动分段设置 → 分歧自动裁定）两级都过才生效；"
                "缺 Key 时按未启用处理，日志会有 ocr_judge_enabled_without_key 提示。"
            ),
            "value": "0",
            "is_secret": False,
        },
        {
            "key": "OCR_JUDGE_API_KEY",
            "category": "ocr",
            "description": (
                "分歧裁定打分器的 API Key（Bearer Token）。敏感项，加密存储。"
                "它只决定「这台环境**能不能**判」，不决定「这份卷宗**要不要**判」——后者在任务上。"
                "留空时即使总闸打开也按未启用处理，分歧全部落人工。"
                "供应商侧政策：可读分辨率下的证件图像会被拒（content_policy_violation），"
                "所以证件/账号类字段不走此路，走 L1 校验位。"
            ),
            "value": "",
            "is_secret": True,
        },
    ]
