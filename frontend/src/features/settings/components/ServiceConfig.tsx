import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import { ArrowLeft, Save, Eye, EyeOff, Loader2, Plus, Pencil, Trash2, Lock, ShieldCheck, ShieldOff } from 'lucide-react'
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

import { CATEGORY_HINTS } from '../constants/config-hints'

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
  type RenderField = {
    key: string
    label: string
    placeholder?: string
    fullWidth?: boolean
    isSecret: boolean
  }
  type RenderGroup = { label: string; fields: RenderField[] }

  const renderGroups = useMemo((): RenderGroup[] => {
    if (category === 'system') {
      return [{
        label: '',
        fields: [
          { key: '_BACKEND_URL', label: '后端地址', placeholder: 'http://localhost:8002', fullWidth: true, isSecret: false },
          { key: '_API_BASE_URL', label: 'API 基础路径', placeholder: 'http://localhost:8002/api/v1', fullWidth: true, isSecret: false },
        ],
      }]
    }

    const fieldHints = hints?.fields ?? {}
    const fieldOrder = hints?.fieldOrder ?? []
    const hintGroups = hints?.groups ?? []

    const allFields: RenderField[] = backendItems.map(item => {
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
    allFields.sort((a, b) => {
      const ai = orderIndex.get(a.key)
      const bi = orderIndex.get(b.key)
      if (ai !== undefined && bi !== undefined) return ai - bi
      if (ai !== undefined) return -1
      if (bi !== undefined) return 1
      return 0
    })

    if (hintGroups.length === 0) {
      return [{ label: '', fields: allFields }]
    }

    const fieldMap = new Map(allFields.map(f => [f.key, f]))
    const grouped = new Set<string>()
    const groups: RenderGroup[] = []

    for (const g of hintGroups) {
      const fields = g.keys.map(k => fieldMap.get(k)).filter((f): f is RenderField => !!f)
      if (fields.length > 0) {
        groups.push({ label: g.label, fields })
        g.keys.forEach(k => grouped.add(k))
      }
    }

    const remaining = allFields.filter(f => !grouped.has(f.key))
    if (remaining.length > 0) {
      groups.push({ label: '其他', fields: remaining })
    }

    return groups
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

      <div className="border border-border rounded-lg overflow-hidden">
        {isLoading && category !== 'system' ? (
          <div className="flex items-center justify-center py-12 text-muted-foreground text-sm">
            <Loader2 className="size-4 animate-spin mr-2" />
            加载中...
          </div>
        ) : renderGroups.length === 0 || renderGroups.every(g => g.fields.length === 0) ? (
          <div className="flex flex-col items-center justify-center py-12 gap-3">
            <p className="text-muted-foreground text-sm">该类别暂无配置项</p>
            {category !== 'system' && (
              <Button variant="outline" size="sm" onClick={() => setCreateOpen(true)}>
                <Plus className="mr-1 size-4" />新增配置
              </Button>
            )}
          </div>
        ) : (
          renderGroups.map((group, gi) => (
            <div key={group.label || gi}>
              {group.label && (
                <div className={`px-6 py-2.5 text-sm font-medium text-foreground bg-muted/50 ${gi > 0 ? 'border-t' : ''}`}>
                  {group.label}
                </div>
              )}
              <div className={`grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-4 p-6 ${group.label && gi > 0 ? 'border-t' : ''}`}>
                {group.fields.map((field) => {
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
                        {field.isSecret && !(field.key in modified) && backendItem ? (
                          <div className="flex items-center gap-2 h-9 px-3 rounded-md border border-input bg-muted/40 text-sm">
                            <Lock className="size-3.5 text-muted-foreground" />
                            {backendItem.has_value ? (
                              <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                                <ShieldCheck className="size-3.5" />已设置
                              </span>
                            ) : (
                              <span className="flex items-center gap-1 text-muted-foreground">
                                <ShieldOff className="size-3.5" />未设置
                              </span>
                            )}
                            <span className="ml-auto text-[11px] text-muted-foreground">点击右侧编辑修改</span>
                          </div>
                        ) : (
                          <>
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
                          </>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          ))
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
