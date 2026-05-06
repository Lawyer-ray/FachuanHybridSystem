import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { ArrowLeft, Save, Eye, EyeOff, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { PATHS } from '@/routes/paths'
import { getApiBaseUrl, getBackendUrl } from '@/lib/api'
import { useSystemConfigs, useUpdateSystemConfigs } from '../hooks/use-system-configs'
import { toast } from 'sonner'

// ─── CONFIG_SCHEMAS：字段 key 与后端 SystemConfig.key 完全一致 ─────────────────

interface FieldSchema {
  key: string
  label: string
  secret?: boolean
  placeholder?: string
  fullWidth?: boolean
}

interface CategorySchema {
  title: string
  description: string
  fields: FieldSchema[]
}

const CONFIG_SCHEMAS: Record<string, CategorySchema> = {
  feishu: {
    title: '飞书配置',
    description: 'App ID、App Secret、默认负责人等飞书集成参数',
    fields: [
      { key: 'FEISHU_APP_ID', label: 'App ID', placeholder: 'cli_xxxxx' },
      { key: 'FEISHU_APP_SECRET', label: 'App Secret', secret: true },
      { key: 'FEISHU_DEFAULT_OWNER_ID', label: '默认负责人', placeholder: 'ou_xxxxxx' },
      { key: 'CASE_CHAT_NAME_TEMPLATE', label: '群聊名称模板', placeholder: '[{stage}]{case_name}', fullWidth: true },
    ],
  },
  dingtalk: {
    title: '钉钉配置',
    description: 'App Key、App Secret、Agent ID 等钉钉集成参数',
    fields: [
      { key: 'DINGTALK_APP_KEY', label: 'App Key' },
      { key: 'DINGTALK_APP_SECRET', label: 'App Secret', secret: true },
      { key: 'DINGTALK_AGENT_ID', label: 'Agent ID' },
      { key: 'DINGTALK_DEFAULT_OWNER_ID', label: '默认群主 userid' },
    ],
  },
  wechat_work: {
    title: '企业微信配置',
    description: 'Corp ID、Agent ID、Secret 等企业微信集成参数',
    fields: [
      { key: 'WECHAT_WORK_CORP_ID', label: 'Corp ID' },
      { key: 'WECHAT_WORK_AGENT_ID', label: 'Agent ID' },
      { key: 'WECHAT_WORK_SECRET', label: 'Secret', secret: true },
      { key: 'WECHAT_WORK_DEFAULT_OWNER_ID', label: '默认群主 userid' },
    ],
  },
  telegram: {
    title: 'Telegram 配置',
    description: 'Bot Token、超级群组 ID 等 Telegram 集成参数',
    fields: [
      { key: 'TELEGRAM_BOT_TOKEN', label: 'Bot Token', secret: true },
      { key: 'TELEGRAM_SUPERGROUP_ID', label: '超级群组 ID', placeholder: '-100xxxxxxx' },
    ],
  },
  email: {
    title: '邮件配置',
    description: 'SMTP 服务器、端口、账号密码、发件人名称等',
    fields: [
      { key: 'EMAIL_HOST', label: 'SMTP 服务器', placeholder: 'smtp.qq.com' },
      { key: 'EMAIL_PORT', label: '端口', placeholder: '465' },
      { key: 'EMAIL_HOST_USER', label: '发件人邮箱' },
      { key: 'EMAIL_HOST_PASSWORD', label: '邮箱密码/授权码', secret: true },
      { key: 'EMAIL_FROM_NAME', label: '发件人名称', placeholder: '法穿AI系统' },
      { key: 'EMAIL_SUBJECT_PREFIX', label: '邮件主题前缀', placeholder: '[法穿AI]' },
      { key: 'EMAIL_USE_SSL', label: '使用 SSL (true/false)', placeholder: 'true' },
      { key: 'EMAIL_USE_TLS', label: '使用 TLS (true/false)', placeholder: 'false' },
    ],
  },
  court_sms: {
    title: '法院短信配置',
    description: '法院短信平台的接口参数配置',
    fields: [],
  },
  ai: {
    title: 'AI 服务配置',
    description: 'SiliconFlow API Key、默认模型、Ollama 等 AI 接口参数',
    fields: [
      { key: 'SILICONFLOW_API_KEY', label: 'SiliconFlow API Key', secret: true },
      { key: 'SILICONFLOW_DEFAULT_MODEL', label: '默认模型', placeholder: 'Pro/Qwen/Qwen3-0.6B' },
      { key: 'OLLAMA_MODEL', label: 'Ollama 模型', placeholder: 'qwen3.5:0.8b' },
      { key: 'OPENAI_COMPATIBLE_API_KEY', label: 'OpenAI-compatible API Key', secret: true },
    ],
  },
  ocr: {
    title: 'OCR 服务配置',
    description: 'PaddleOCR 的 API 地址、模型类型、Token 等参数',
    fields: [
      { key: 'OCR_PROVIDER', label: 'OCR 引擎', placeholder: 'local / paddleocr_api' },
      { key: 'PADDLEOCR_API_MODEL', label: 'PaddleOCR 模型', placeholder: 'pp_ocrv5' },
      { key: 'PADDLEOCR_OCR_API_URL', label: 'OCR 接口地址', fullWidth: true },
      { key: 'PADDLEOCR_VL_API_URL', label: 'VL 接口地址', fullWidth: true },
      { key: 'PADDLEOCR_VL15_API_URL', label: 'VL-1.5 接口地址', fullWidth: true },
      { key: 'PADDLEOCR_API_TOKEN', label: 'API Token', secret: true },
    ],
  },
  enterprise_data: {
    title: '企业数据配置',
    description: '天眼查等企业信息查询接口的 API Key',
    fields: [
      { key: 'TIANYANCHA_MCP_API_KEY', label: '天眼查 MCP API Key', secret: true },
    ],
  },
  scraper: {
    title: '爬虫配置',
    description: '加密密钥、无头模式等网页爬取相关参数',
    fields: [
      { key: 'SCRAPER_ENCRYPTION_KEY', label: '加密密钥', secret: true },
      { key: 'SCRAPER_HEADLESS', label: '无头模式 (true/false)', placeholder: 'True' },
    ],
  },
  system: {
    title: '系统连接',
    description: '后端服务地址配置，修改后需刷新页面生效',
    fields: [
      { key: '_BACKEND_URL', label: '后端地址', placeholder: 'http://localhost:8002', fullWidth: true },
      { key: '_API_BASE_URL', label: 'API 基础路径', placeholder: 'http://localhost:8002/api/v1', fullWidth: true },
    ],
  },
}

// ─── Component ─────────────────────────────────────────────────────────────────

export function ServiceConfig() {
  const navigate = useNavigate()
  const { category } = useParams<{ category: string }>()
  const schema = CONFIG_SCHEMAS[category ?? '']

  const { data: backendGroups, isLoading } = useSystemConfigs()
  const updateMutation = useUpdateSystemConfigs()

  // 从后端数据构建 key → value 映射
  const backendValues = useMemo(() => {
    const map: Record<string, string> = {}
    if (backendGroups) {
      for (const group of backendGroups) {
        for (const item of group.items) {
          map[item.key] = item.value
        }
      }
    }
    return map
  }, [backendGroups])

  // 用户修改过的值（只存变更）
  const [modified, setModified] = useState<Record<string, string>>({})
  const [showSecrets, setShowSecrets] = useState<Record<string, boolean>>({})

  // system 类别：从 localStorage 读取
  const [systemValues, setSystemValues] = useState<Record<string, string>>({})

  useEffect(() => {
    if (category === 'system') {
      setSystemValues({
        _BACKEND_URL: getBackendUrl(),
        _API_BASE_URL: getApiBaseUrl(),
      })
    }
  }, [category])

  // 获取字段当前显示值
  const getDisplayValue = (field: FieldSchema): string => {
    if (category === 'system') {
      return systemValues[field.key] ?? ''
    }
    if (field.key in modified) {
      return modified[field.key]
    }
    return backendValues[field.key] ?? ''
  }

  const handleFieldChange = (key: string, value: string) => {
    if (category === 'system') {
      setSystemValues((prev) => ({ ...prev, [key]: value }))
    } else {
      setModified((prev) => ({ ...prev, [key]: value }))
    }
  }

  const handleSave = () => {
    if (category === 'system') {
      // 保存到 localStorage
      const backendUrl = systemValues._BACKEND_URL?.trim()
      const apiBaseUrl = systemValues._API_BASE_URL?.trim()
      if (backendUrl) localStorage.setItem('backend_url', backendUrl)
      else localStorage.removeItem('backend_url')
      if (apiBaseUrl) localStorage.setItem('api_base_url', apiBaseUrl)
      else localStorage.removeItem('api_base_url')
      toast.success('系统连接配置已保存，刷新页面后生效')
      return
    }

    // 只发送有变更的字段
    if (Object.keys(modified).length === 0) {
      toast.info('没有需要保存的修改')
      return
    }
    updateMutation.mutate({ category: category ?? '', updates: modified }, {
      onSuccess: (res) => {
        toast.success(`已保存 ${res.updated_count} 项配置`)
        setModified({})
      },
      onError: (err) => {
        toast.error(`保存失败：${err.message}`)
      },
    })
  }

  if (!schema) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" size="sm" onClick={() => navigate(PATHS.ADMIN_SETTINGS)} className="gap-1">
          <ArrowLeft className="size-4" />
          返回设置
        </Button>
        <Card>
          <CardContent className="pt-12 pb-12 text-center">
            <p className="text-muted-foreground text-sm">未找到配置类别：{category}</p>
          </CardContent>
        </Card>
      </div>
    )
  }

  const isSaving = updateMutation.isPending
  const hasFields = schema.fields.length > 0

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={() => navigate(PATHS.ADMIN_SETTINGS)} className="gap-1">
          <ArrowLeft className="size-4" />
          返回设置
        </Button>
        <div className="w-px h-5 bg-border" />
        <h1 className="text-xl font-semibold">{schema.title}</h1>
        <Badge variant="outline" className="text-[11px]">{category}</Badge>
      </div>
      <p className="text-muted-foreground text-sm">{schema.description}</p>

      {!hasFields ? (
        <Card>
          <CardContent className="pt-12 pb-12 text-center">
            <p className="text-muted-foreground text-sm">该类别暂无配置项</p>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader className="py-3 px-4 border-b border-border">
            <CardTitle className="text-[13px] font-semibold">配置参数</CardTitle>
          </CardHeader>
          <CardContent className="px-4 py-4">
            {isLoading && category !== 'system' ? (
              <div className="flex items-center justify-center py-8 text-muted-foreground text-sm">
                <Loader2 className="size-4 animate-spin mr-2" />
                加载中...
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {schema.fields.map((field) => {
                  const isSecret = field.secret
                  const showKey = `show_${field.key}`
                  return (
                    <div
                      key={field.key}
                      className={field.fullWidth ? 'sm:col-span-2 space-y-1.5' : 'space-y-1.5'}
                    >
                      <Label className="text-xs text-muted-foreground">{field.label}</Label>
                      <div className="relative">
                        <Input
                          type={isSecret && !showSecrets[showKey] ? 'password' : 'text'}
                          value={getDisplayValue(field)}
                          onChange={(e) => handleFieldChange(field.key, e.target.value)}
                          placeholder={field.placeholder ?? `请输入${field.label}`}
                          className={isSecret ? 'pr-10' : ''}
                        />
                        {isSecret && (
                          <button
                            type="button"
                            onClick={() => setShowSecrets((prev) => ({ ...prev, [showKey]: !prev[showKey] }))}
                            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                          >
                            {showSecrets[showKey] ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                          </button>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}

            <div className="flex justify-end pt-4 mt-4 border-t border-border">
              <Button size="sm" onClick={handleSave} disabled={isSaving}>
                {isSaving ? (
                  <Loader2 className="mr-1.5 size-4 animate-spin" />
                ) : (
                  <Save className="mr-1.5 size-4" />
                )}
                保存配置
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

export default ServiceConfig
