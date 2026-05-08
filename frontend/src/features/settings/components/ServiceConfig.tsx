import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { ArrowLeft, Save, Eye, EyeOff, Loader2, Plus, Pencil, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { PATHS } from '@/routes/paths'
import { getApiBaseUrl, getBackendUrl } from '@/lib/api'
import {
  useSystemConfigs, useUpdateSystemConfigs,
  useCreateSystemConfig, usePatchSystemConfig, useDeleteSystemConfig,
} from '../hooks/use-system-configs'
import type { SystemConfigItem } from '../api'
import { toast } from 'sonner'

// ─── Category hints：仅提供 UI 优化，不决定字段列表 ───────────────────────────

interface FieldHint {
  label?: string
  placeholder?: string
  fullWidth?: boolean
}

interface CategoryHints {
  title: string
  description: string
  fields?: Record<string, FieldHint>
  fieldOrder?: string[]
}

const CATEGORY_HINTS: Record<string, CategoryHints> = {
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
    description: 'SiliconFlow、Ollama、OpenAI-compatible 等 AI 后端参数，以及全局 LLM 设置',
    fieldOrder: [
      'LLM_DEFAULT_BACKEND', 'LLM_TEMPERATURE', 'LLM_MAX_TOKENS', 'LLM_EXTRA_MODELS',
      'SILICONFLOW_API_KEY', 'SILICONFLOW_BASE_URL', 'SILICONFLOW_DEFAULT_MODEL', 'SILICONFLOW_EMBEDDING_MODEL', 'SILICONFLOW_TIMEOUT',
      'LLM_BACKEND_SILICONFLOW_ENABLED', 'LLM_BACKEND_SILICONFLOW_PRIORITY',
      'OLLAMA_BASE_URL', 'OLLAMA_MODEL', 'OLLAMA_EMBEDDING_MODEL', 'OLLAMA_TIMEOUT',
      'LLM_BACKEND_OLLAMA_ENABLED', 'LLM_BACKEND_OLLAMA_PRIORITY',
      'OPENAI_COMPATIBLE_API_KEY', 'OPENAI_COMPATIBLE_BASE_URL', 'OPENAI_COMPATIBLE_DEFAULT_MODEL', 'OPENAI_COMPATIBLE_EMBEDDING_MODEL', 'OPENAI_COMPATIBLE_TIMEOUT',
      'LLM_BACKEND_OPENAI_COMPATIBLE_ENABLED', 'LLM_BACKEND_OPENAI_COMPATIBLE_PRIORITY',
    ],
    fields: {
      LLM_DEFAULT_BACKEND: { label: '默认后端', placeholder: 'siliconflow / ollama / openai_compatible' },
      LLM_TEMPERATURE: { label: '生成温度', placeholder: '0.3' },
      LLM_MAX_TOKENS: { label: '最大输出 Token', placeholder: '2000' },
      LLM_EXTRA_MODELS: { label: '额外模型列表', placeholder: 'model1,model2', fullWidth: true },
      SILICONFLOW_API_KEY: { label: 'SiliconFlow API Key' },
      SILICONFLOW_BASE_URL: { label: 'SiliconFlow API 地址', placeholder: 'https://api.siliconflow.cn/v1', fullWidth: true },
      SILICONFLOW_DEFAULT_MODEL: { label: 'SiliconFlow 默认模型', placeholder: 'Pro/Qwen/Qwen3-0.6B' },
      SILICONFLOW_EMBEDDING_MODEL: { label: 'SiliconFlow Embedding 模型' },
      SILICONFLOW_TIMEOUT: { label: 'SiliconFlow 超时(秒)', placeholder: '900' },
      LLM_BACKEND_SILICONFLOW_ENABLED: { label: '启用 SiliconFlow', placeholder: 'true' },
      LLM_BACKEND_SILICONFLOW_PRIORITY: { label: 'SiliconFlow 优先级', placeholder: '1' },
      OLLAMA_BASE_URL: { label: 'Ollama 服务地址', placeholder: 'http://localhost:11434', fullWidth: true },
      OLLAMA_MODEL: { label: 'Ollama 模型', placeholder: 'qwen3:0.6b' },
      OLLAMA_EMBEDDING_MODEL: { label: 'Ollama Embedding 模型' },
      OLLAMA_TIMEOUT: { label: 'Ollama 超时(秒)', placeholder: '300' },
      LLM_BACKEND_OLLAMA_ENABLED: { label: '启用 Ollama', placeholder: 'true' },
      LLM_BACKEND_OLLAMA_PRIORITY: { label: 'Ollama 优先级', placeholder: '2' },
      OPENAI_COMPATIBLE_API_KEY: { label: 'OpenAI-compatible API Key' },
      OPENAI_COMPATIBLE_BASE_URL: { label: 'OpenAI-compatible API 地址', fullWidth: true },
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

// ─── Component ─────────────────────────────────────────────────────────────────

export function ServiceConfig() {
  const navigate = useNavigate()
  const { category } = useParams<{ category: string }>()
  const hints = CATEGORY_HINTS[category ?? '']

  const { data: backendGroups, isLoading } = useSystemConfigs()
  const updateMutation = useUpdateSystemConfigs()
  const createMutation = useCreateSystemConfig()
  const patchMutation = usePatchSystemConfig()
  const deleteMutation = useDeleteSystemConfig()

  // Dialog state
  const [createOpen, setCreateOpen] = useState(false)
  const [editItem, setEditItem] = useState<SystemConfigItem | null>(null)
  const [deleteKey, setDeleteKey] = useState<string | null>(null)

  // Create form state
  const [newKey, setNewKey] = useState('')
  const [newValue, setNewValue] = useState('')
  const [newDescription, setNewDescription] = useState('')
  const [newIsSecret, setNewIsSecret] = useState(false)

  // Edit form state
  const [editValue, setEditValue] = useState('')
  const [editDescription, setEditDescription] = useState('')
  const [editIsSecret, setEditIsSecret] = useState(false)
  const [editIsActive, setEditIsActive] = useState(true)

  // 从后端数据构建 key → item 映射
  const backendItemMap = useMemo(() => {
    const map: Record<string, SystemConfigItem> = {}
    if (backendGroups) {
      for (const group of backendGroups) {
        for (const item of group.items) {
          map[item.key] = item
        }
      }
    }
    return map
  }, [backendGroups])

  // 后端返回的当前类别的配置项
  const backendItems = useMemo((): SystemConfigItem[] => {
    if (!backendGroups || !category || category === 'system') return []
    const group = backendGroups.find(g => g.category === category)
    return group?.items ?? []
  }, [backendGroups, category])

  // 渲染用的字段列表：以后端为准，schema hints 仅提供 UI 优化和排序
  const renderFields = useMemo(() => {
    if (category === 'system') {
      return [
        { key: '_BACKEND_URL', label: '后端地址', placeholder: 'http://localhost:8002', fullWidth: true, isSecret: false },
        { key: '_API_BASE_URL', label: 'API 基础路径', placeholder: 'http://localhost:8002/api/v1', fullWidth: true, isSecret: false },
      ]
    }

    const fieldHints = hints?.fields ?? {}
    const fieldOrder = hints?.fieldOrder ?? []

    const fields = backendItems.map(item => {
      const hint = fieldHints[item.key]
      return {
        key: item.key,
        label: hint?.label || item.description || item.key,
        placeholder: hint?.placeholder,
        fullWidth: hint?.fullWidth,
        isSecret: item.is_secret,
      }
    })

    const orderIndex = new Map(fieldOrder.map((k, i) => [k, i]))
    fields.sort((a, b) => {
      const ai = orderIndex.get(a.key)
      const bi = orderIndex.get(b.key)
      if (ai !== undefined && bi !== undefined) return ai - bi
      if (ai !== undefined) return -1
      if (bi !== undefined) return 1
      return 0
    })

    return fields
  }, [category, hints, backendItems])

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
    setModified({})
    setShowSecrets({})
  }, [category])

  const getDisplayValue = (key: string): string => {
    if (category === 'system') return systemValues[key] ?? ''
    if (key in modified) return modified[key]
    return backendItemMap[key]?.value ?? ''
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
      const backendUrl = systemValues._BACKEND_URL?.trim()
      const apiBaseUrl = systemValues._API_BASE_URL?.trim()
      if (backendUrl) localStorage.setItem('backend_url', backendUrl)
      else localStorage.removeItem('backend_url')
      if (apiBaseUrl) localStorage.setItem('api_base_url', apiBaseUrl)
      else localStorage.removeItem('api_base_url')
      toast.success('系统连接配置已保存，刷新页面后生效')
      return
    }

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

  const handleCreate = () => {
    if (!newKey.trim()) { toast.error('请输入配置项 Key'); return }
    createMutation.mutate({
      key: newKey.trim().toUpperCase(),
      value: newValue,
      category: category ?? 'general',
      description: newDescription,
      is_secret: newIsSecret,
    }, {
      onSuccess: () => {
        toast.success(`配置项 ${newKey} 已创建`)
        setCreateOpen(false)
        setNewKey(''); setNewValue(''); setNewDescription(''); setNewIsSecret(false)
      },
      onError: (err) => { toast.error(`创建失败：${err.message}`) },
    })
  }

  const openEdit = (item: SystemConfigItem) => {
    setEditItem(item)
    setEditValue(item.is_secret ? '' : item.value)
    setEditDescription(item.description)
    setEditIsSecret(item.is_secret)
    setEditIsActive(item.is_active)
  }

  const handleEdit = () => {
    if (!editItem) return
    const data: Partial<SystemConfigItem> = {}
    if (editDescription !== editItem.description) data.description = editDescription
    if (editIsSecret !== editItem.is_secret) data.is_secret = editIsSecret
    if (editIsActive !== editItem.is_active) data.is_active = editIsActive
    if (!editItem.is_secret && editValue !== editItem.value) data.value = editValue
    if (editItem.is_secret && editValue) data.value = editValue

    if (Object.keys(data).length === 0) {
      toast.info('没有需要保存的修改')
      setEditItem(null)
      return
    }
    patchMutation.mutate({ key: editItem.key, data }, {
      onSuccess: () => {
        toast.success('配置项已更新')
        setEditItem(null)
      },
      onError: (err) => { toast.error(`更新失败：${err.message}`) },
    })
  }

  const handleDelete = () => {
    if (!deleteKey) return
    deleteMutation.mutate(deleteKey, {
      onSuccess: () => {
        toast.success(`配置项 ${deleteKey} 已删除`)
        setDeleteKey(null)
      },
      onError: (err) => { toast.error(`删除失败：${err.message}`) },
    })
  }

  const title = hints?.title ?? category ?? '配置'
  const description = hints?.description ?? ''
  const isSaving = updateMutation.isPending

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => navigate(PATHS.ADMIN_SETTINGS)} className="gap-1">
            <ArrowLeft className="size-4" />
            返回设置
          </Button>
          <div className="w-px h-5 bg-border" />
          <h1 className="text-xl font-semibold">{title}</h1>
          <Badge variant="outline" className="text-[11px]">{category}</Badge>
        </div>
        <div className="flex items-center gap-2">
          {category !== 'system' && (
            <Button variant="outline" size="sm" onClick={() => setCreateOpen(true)}>
              <Plus className="mr-1 size-4" />
              新增配置
            </Button>
          )}
          <Button size="sm" onClick={handleSave} disabled={isSaving}>
            {isSaving ? <Loader2 className="mr-1.5 size-4 animate-spin" /> : <Save className="mr-1.5 size-4" />}
            保存配置
          </Button>
        </div>
      </div>
      {description && <p className="text-muted-foreground text-sm">{description}</p>}

      <div className="border border-border rounded-lg">
        {isLoading && category !== 'system' ? (
          <div className="flex items-center justify-center py-12 text-muted-foreground text-sm">
            <Loader2 className="size-4 animate-spin mr-2" />
            加载中...
          </div>
        ) : renderFields.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 gap-3">
            <p className="text-muted-foreground text-sm">该类别暂无配置项</p>
            {category !== 'system' && (
              <Button variant="outline" size="sm" onClick={() => setCreateOpen(true)}>
                <Plus className="mr-1 size-4" />新增配置
              </Button>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-4 p-6">
            {renderFields.map((field) => {
              const showKey = `show_${field.key}`
              const backendItem = backendItemMap[field.key]
              return (
                <div
                  key={field.key}
                  className={field.fullWidth ? 'sm:col-span-2 space-y-1.5' : 'space-y-1.5'}
                >
                  <div className="flex items-center justify-between">
                    <Label className="text-xs text-muted-foreground">{field.label}</Label>
                    {backendItem && category !== 'system' && (
                      <div className="flex items-center gap-1">
                        <button
                          className="p-0.5 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                          title="编辑配置项"
                          onClick={() => openEdit(backendItem)}
                        >
                          <Pencil className="size-3" />
                        </button>
                        <button
                          className="p-0.5 rounded text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                          title="删除配置项"
                          onClick={() => setDeleteKey(field.key)}
                        >
                          <Trash2 className="size-3" />
                        </button>
                      </div>
                    )}
                  </div>
                  <div className="relative">
                    <Input
                      type={field.isSecret && !showSecrets[showKey] ? 'password' : 'text'}
                      value={getDisplayValue(field.key)}
                      onChange={(e) => handleFieldChange(field.key, e.target.value)}
                      placeholder={field.placeholder ?? `请输入${field.label}`}
                      className={field.isSecret ? 'pr-10' : ''}
                    />
                    {field.isSecret && (
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
      </div>

      {/* ── Create Dialog ── */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>新增配置项</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>Key</Label>
              <Input
                value={newKey}
                onChange={(e) => setNewKey(e.target.value.toUpperCase())}
                placeholder="MY_CONFIG_KEY"
              />
            </div>
            <div className="space-y-1.5">
              <Label>值</Label>
              <Input
                type={newIsSecret ? 'password' : 'text'}
                value={newValue}
                onChange={(e) => setNewValue(e.target.value)}
                placeholder="请输入配置值"
              />
            </div>
            <div className="space-y-1.5">
              <Label>描述</Label>
              <Input
                value={newDescription}
                onChange={(e) => setNewDescription(e.target.value)}
                placeholder="配置项用途说明"
              />
            </div>
            <div className="flex items-center gap-2">
              <Switch checked={newIsSecret} onCheckedChange={setNewIsSecret} />
              <Label className="text-sm">敏感信息（密码遮罩）</Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>取消</Button>
            <Button onClick={handleCreate} disabled={createMutation.isPending}>
              {createMutation.isPending && <Loader2 className="mr-1.5 size-4 animate-spin" />}
              创建
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Edit Dialog ── */}
      <Dialog open={!!editItem} onOpenChange={(open) => !open && setEditItem(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>编辑配置项</DialogTitle>
          </DialogHeader>
          {editItem && (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <Badge variant="outline">{editItem.key}</Badge>
                <Badge variant="secondary" className="text-[10px]">{editItem.category}</Badge>
              </div>
              <div className="space-y-1.5">
                <Label>值</Label>
                <Input
                  type={editIsSecret ? 'password' : 'text'}
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  placeholder={editItem.is_secret ? '留空则不修改' : '请输入配置值'}
                />
              </div>
              <div className="space-y-1.5">
                <Label>描述</Label>
                <Input
                  value={editDescription}
                  onChange={(e) => setEditDescription(e.target.value)}
                  placeholder="配置项用途说明"
                />
              </div>
              <div className="flex items-center gap-2">
                <Switch checked={editIsSecret} onCheckedChange={setEditIsSecret} />
                <Label className="text-sm">敏感信息（密码遮罩）</Label>
              </div>
              <div className="flex items-center gap-2">
                <Switch checked={editIsActive} onCheckedChange={setEditIsActive} />
                <Label className="text-sm">启用</Label>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditItem(null)}>取消</Button>
            <Button onClick={handleEdit} disabled={patchMutation.isPending}>
              {patchMutation.isPending && <Loader2 className="mr-1.5 size-4 animate-spin" />}
              保存
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Delete Dialog ── */}
      <AlertDialog open={!!deleteKey} onOpenChange={() => setDeleteKey(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除配置项</AlertDialogTitle>
            <AlertDialogDescription>
              删除「{deleteKey}」后无法恢复，相关功能可能受影响。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-destructive text-destructive-foreground">
              确认删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

export default ServiceConfig
