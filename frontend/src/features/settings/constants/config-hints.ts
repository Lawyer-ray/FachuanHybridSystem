// ─── Category hints：仅提供 UI 优化，不决定字段列表 ───────────────────────────

interface FieldHint {
  label?: string
  placeholder?: string
  fullWidth?: boolean
}

interface FieldGroup {
  label: string
  keys: string[]
}

interface CategoryHints {
  title: string
  description: string
  fields?: Record<string, FieldHint>
  fieldOrder?: string[]
  groups?: FieldGroup[]
}

export const CATEGORY_HINTS: Record<string, CategoryHints> = {
  feishu: {
    title: '飞书配置',
    description: 'App ID、App Secret、默认负责人等飞书集成参数',
    fieldOrder: ['FEISHU_APP_ID', 'FEISHU_APP_SECRET', 'FEISHU_DEFAULT_OWNER_ID', 'CASE_CHAT_NAME_TEMPLATE'],
    fields: {
      FEISHU_APP_ID: { label: 'App ID', placeholder: 'cli_xxxxx' },
      FEISHU_APP_SECRET: { label: 'App Secret' },
      FEISHU_DEFAULT_OWNER_ID: { label: '默认负责人', placeholder: 'ou_xxxxxx' },
      CASE_CHAT_NAME_TEMPLATE: { label: '群聊名称模板', placeholder: '[{stage}]{case_name}', fullWidth: true },
    },
  },
  dingtalk: {
    title: '钉钉配置',
    description: 'App Key、App Secret、Agent ID 等钉钉集成参数',
    fieldOrder: ['DINGTALK_APP_KEY', 'DINGTALK_APP_SECRET', 'DINGTALK_AGENT_ID', 'DINGTALK_DEFAULT_OWNER_ID'],
    fields: {
      DINGTALK_APP_KEY: { label: 'App Key' },
      DINGTALK_APP_SECRET: { label: 'App Secret' },
      DINGTALK_AGENT_ID: { label: 'Agent ID' },
      DINGTALK_DEFAULT_OWNER_ID: { label: '默认群主 userid' },
    },
  },
  wechat_work: {
    title: '企业微信配置',
    description: 'Corp ID、Agent ID、Secret 等企业微信集成参数',
    fieldOrder: ['WECHAT_WORK_CORP_ID', 'WECHAT_WORK_AGENT_ID', 'WECHAT_WORK_SECRET', 'WECHAT_WORK_DEFAULT_OWNER_ID'],
    fields: {
      WECHAT_WORK_CORP_ID: { label: 'Corp ID' },
      WECHAT_WORK_AGENT_ID: { label: 'Agent ID' },
      WECHAT_WORK_SECRET: { label: 'Secret' },
      WECHAT_WORK_DEFAULT_OWNER_ID: { label: '默认群主 userid' },
    },
  },
  telegram: {
    title: 'Telegram 配置',
    description: 'Bot Token、超级群组 ID 等 Telegram 集成参数',
    fieldOrder: ['TELEGRAM_BOT_TOKEN', 'TELEGRAM_SUPERGROUP_ID'],
    fields: {
      TELEGRAM_BOT_TOKEN: { label: 'Bot Token' },
      TELEGRAM_SUPERGROUP_ID: { label: '超级群组 ID', placeholder: '-100xxxxxxx' },
    },
  },
  email: {
    title: '邮件配置',
    description: 'SMTP 服务器、端口、账号密码、发件人名称等',
    fieldOrder: ['EMAIL_HOST', 'EMAIL_PORT', 'EMAIL_HOST_USER', 'EMAIL_HOST_PASSWORD', 'EMAIL_FROM_NAME', 'EMAIL_SUBJECT_PREFIX', 'EMAIL_USE_SSL', 'EMAIL_USE_TLS'],
    fields: {
      EMAIL_HOST: { label: 'SMTP 服务器', placeholder: 'smtp.qq.com' },
      EMAIL_PORT: { label: '端口', placeholder: '465' },
      EMAIL_HOST_USER: { label: '发件人邮箱' },
      EMAIL_HOST_PASSWORD: { label: '邮箱密码/授权码' },
      EMAIL_FROM_NAME: { label: '发件人名称', placeholder: '法穿AI系统' },
      EMAIL_SUBJECT_PREFIX: { label: '邮件主题前缀', placeholder: '[法穿AI]' },
      EMAIL_USE_SSL: { label: '使用 SSL (true/false)', placeholder: 'true' },
      EMAIL_USE_TLS: { label: '使用 TLS (true/false)', placeholder: 'false' },
    },
  },
  court_sms: { title: '法院短信配置', description: '法院短信平台的接口参数配置' },
  ai: {
    title: 'AI 服务配置',
    description: 'Ollama、OpenAI-compatible 等 AI 后端参数，以及全局 LLM 设置',
    groups: [
      { label: '全局 LLM 设置', keys: ['LLM_DEFAULT_BACKEND', 'LLM_TEMPERATURE', 'LLM_MAX_TOKENS', 'LLM_EXTRA_MODELS'] },
      { label: 'Ollama', keys: ['OLLAMA_BASE_URL', 'OLLAMA_MODEL', 'OLLAMA_EMBEDDING_MODEL', 'OLLAMA_TIMEOUT', 'LLM_BACKEND_OLLAMA_ENABLED', 'LLM_BACKEND_OLLAMA_PRIORITY'] },
      { label: 'OpenAI-compatible', keys: ['OPENAI_COMPATIBLE_API_KEY', 'OPENAI_COMPATIBLE_BASE_URL', 'OPENAI_COMPATIBLE_DEFAULT_MODEL', 'OPENAI_COMPATIBLE_EMBEDDING_MODEL', 'OPENAI_COMPATIBLE_TIMEOUT', 'LLM_BACKEND_OPENAI_COMPATIBLE_ENABLED', 'LLM_BACKEND_OPENAI_COMPATIBLE_PRIORITY'] },
    ],
    fieldOrder: [
      'LLM_DEFAULT_BACKEND', 'LLM_TEMPERATURE', 'LLM_MAX_TOKENS', 'LLM_EXTRA_MODELS',
      'OLLAMA_BASE_URL', 'OLLAMA_MODEL', 'OLLAMA_EMBEDDING_MODEL', 'OLLAMA_TIMEOUT',
      'LLM_BACKEND_OLLAMA_ENABLED', 'LLM_BACKEND_OLLAMA_PRIORITY',
      'OPENAI_COMPATIBLE_API_KEY', 'OPENAI_COMPATIBLE_BASE_URL', 'OPENAI_COMPATIBLE_DEFAULT_MODEL', 'OPENAI_COMPATIBLE_EMBEDDING_MODEL', 'OPENAI_COMPATIBLE_TIMEOUT',
      'LLM_BACKEND_OPENAI_COMPATIBLE_ENABLED', 'LLM_BACKEND_OPENAI_COMPATIBLE_PRIORITY',
    ],
    fields: {
      LLM_DEFAULT_BACKEND: { label: '默认后端', placeholder: 'ollama / openai_compatible' },
      LLM_TEMPERATURE: { label: '生成温度', placeholder: '0.3' },
      LLM_MAX_TOKENS: { label: '最大输出 Token', placeholder: '2000' },
      LLM_EXTRA_MODELS: { label: '额外模型列表', placeholder: 'model1,model2' },
      OLLAMA_BASE_URL: { label: 'Ollama 服务地址', placeholder: 'http://localhost:11434' },
      OLLAMA_MODEL: { label: 'Ollama 模型', placeholder: 'qwen3:0.6b' },
      OLLAMA_EMBEDDING_MODEL: { label: 'Ollama Embedding 模型' },
      OLLAMA_TIMEOUT: { label: 'Ollama 超时(秒)', placeholder: '300' },
      LLM_BACKEND_OLLAMA_ENABLED: { label: '启用 Ollama', placeholder: 'true' },
      LLM_BACKEND_OLLAMA_PRIORITY: { label: 'Ollama 优先级', placeholder: '2' },
      OPENAI_COMPATIBLE_API_KEY: { label: 'OpenAI-compatible API Key' },
      OPENAI_COMPATIBLE_BASE_URL: { label: 'OpenAI-compatible API 地址' },
      OPENAI_COMPATIBLE_DEFAULT_MODEL: { label: 'OpenAI-compatible 默认模型', placeholder: 'moonshot-v1-8k' },
      OPENAI_COMPATIBLE_EMBEDDING_MODEL: { label: 'OpenAI-compatible Embedding 模型' },
      OPENAI_COMPATIBLE_TIMEOUT: { label: 'OpenAI-compatible 超时(秒)', placeholder: '120' },
      LLM_BACKEND_OPENAI_COMPATIBLE_ENABLED: { label: '启用 OpenAI-compatible', placeholder: 'false' },
      LLM_BACKEND_OPENAI_COMPATIBLE_PRIORITY: { label: 'OpenAI-compatible 优先级', placeholder: '3' },
    },
  },
  ocr: {
    title: 'OCR 服务配置',
    description: 'PaddleOCR 的 API 地址、模型类型、Token 等参数',
    fieldOrder: ['OCR_PROVIDER', 'PADDLEOCR_API_MODEL', 'PADDLEOCR_OCR_API_URL', 'PADDLEOCR_VL_API_URL', 'PADDLEOCR_VL15_API_URL', 'PADDLEOCR_API_TOKEN'],
    fields: {
      OCR_PROVIDER: { label: 'OCR 引擎', placeholder: 'local / paddleocr_api' },
      PADDLEOCR_API_MODEL: { label: 'PaddleOCR 模型', placeholder: 'pp_ocrv5' },
      PADDLEOCR_OCR_API_URL: { label: 'OCR 接口地址', fullWidth: true },
      PADDLEOCR_VL_API_URL: { label: 'VL 接口地址', fullWidth: true },
      PADDLEOCR_VL15_API_URL: { label: 'VL-1.5 接口地址', fullWidth: true },
      PADDLEOCR_API_TOKEN: { label: 'API Token' },
    },
  },
  enterprise_data: {
    title: '企业数据配置',
    description: '天眼查等企业信息查询接口的 API Key',
    fields: { TIANYANCHA_MCP_API_KEY: { label: '天眼查 MCP API Key' } },
  },
  scraper: {
    title: '爬虫配置',
    description: '加密密钥、无头模式等网页爬取相关参数',
    fieldOrder: ['SCRAPER_ENCRYPTION_KEY', 'SCRAPER_HEADLESS'],
    fields: {
      SCRAPER_ENCRYPTION_KEY: { label: '加密密钥' },
      SCRAPER_HEADLESS: { label: '无头模式 (true/false)', placeholder: 'True' },
    },
  },
  system: {
    title: '系统连接',
    description: '后端服务地址配置，修改后需刷新页面生效',
    fieldOrder: ['_BACKEND_URL', '_API_BASE_URL'],
    fields: {
      _BACKEND_URL: { label: '后端地址', placeholder: 'http://localhost:8002', fullWidth: true },
      _API_BASE_URL: { label: 'API 基础路径', placeholder: 'http://localhost:8002/api/v1', fullWidth: true },
    },
  },
}
