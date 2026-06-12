/**
 * 工作流模板可视化编排器
 *
 * 布局：左侧步骤面板 | 中间画布 | 右侧属性面板
 */
import { useState, useCallback, useEffect, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router'
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
  DragOverlay,
} from '@dnd-kit/core'
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import {
  ArrowLeft,
  Save,
  Undo2,
  Redo2,
  ZoomIn,
  ZoomOut,
  Search,
  X,
  ChevronDown,
  ChevronRight,
  GripVertical,
  Trash2,
  Copy,
  Plus,
  Play,
  ShieldCheck,
  Clock,
  GitFork,
  Timer,
  Brain,
  Globe,
  Code,
  FileSearch,
  Files,
  BookOpen,
  Microscope,
  BarChart3,
  ArrowUpDown,
  CheckCircle,
  ScrollText,
  Shield,
  CheckSquare,
  Download,
  Package,
  Lock,
  Database,
  Send,
  Umbrella,
  MessageSquare,
  Building2,
  SearchCode,
  BookCheck,
  Bell,
  AlarmClock,
  Mail,
  Zap,
  RefreshCw,
  Calculator,
  Percent,
  GitBranch,
  Scale,
  type LucideIcon,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'
import {
  useTemplate,
  useCreateTemplate,
  useUpdateTemplate,
  useStepRegistry,
} from '@/features/workflow/hooks/useTemplates'
import type { StepNode, StepCategory, StepDefinition, StepType, ConfigField } from '@/features/workflow/types'
import { SortableStepNode } from './components/SortableStepNode'
import { StepNodeCard } from './components/StepNodeCard'

// ── 图标映射 ──────────────────────────────────────────────────────────────────

const ICON_MAP: Record<string, LucideIcon> = {
  GitBranch, ShieldCheck, Clock, GitFork, Timer, Brain, Globe, Code,
  FileSearch, Files, BookOpen, Microscope, BarChart3, ArrowUpDown, CheckCircle,
  ScrollText, Shield, CheckSquare, Download, Package, Lock, Database,
  Send, Umbrella, MessageSquare, Building2, SearchCode, BookCheck,
  Bell, AlarmClock, Mail, Zap, RefreshCw, Calculator, Percent,
  Search, Play, Scale,
}

function getIcon(name?: string): LucideIcon {
  return ICON_MAP[name] || Play
}

// ── 内联步骤卡片（用于拖拽预览和画布节点） ────────────────────────────────────

// ── 场景分组映射 ──────────────────────────────────────────────────────────────

interface ScenarioGroup {
  id: string
  name: string
  icon: LucideIcon
  /** 原始 category.id → 映射到哪个场景组 */
  categoryIds: string[]
}

const SCENARIO_GROUPS: ScenarioGroup[] = [
  { id: 'preparation', name: '起诉准备', icon: ScrollText, categoryIds: ['documents', 'cases'] },
  { id: 'evidence', name: '证据处理', icon: Microscope, categoryIds: ['evidence'] },
  { id: 'litigation', name: '诉讼流程', icon: Scale, categoryIds: ['litigation'] },
  { id: 'investigation', name: '调查检索', icon: SearchCode, categoryIds: ['enterprise', 'legal_research'] },
  { id: 'flow', name: '流程控制', icon: GitBranch, categoryIds: ['flow'] },
  { id: 'automation', name: '自动化工具', icon: Zap, categoryIds: ['automation', 'notifications'] },
]

function groupRegistryByScenario(
  registry: StepCategory[],
  groups: ScenarioGroup[],
): { group: ScenarioGroup; categories: StepCategory[] }[] {
  const catMap = new Map(registry.map((c) => [c.id, c]))
  const used = new Set<string>()
  const result: { group: ScenarioGroup; categories: StepCategory[] }[] = []

  for (const g of groups) {
    const cats = g.categoryIds
      .map((id) => catMap.get(id))
      .filter((c): c is StepCategory => !!c)
    if (cats.length > 0) {
      result.push({ group: g, categories: cats })
      g.categoryIds.forEach((id) => used.add(id))
    }
  }
  // 未映射的分类放到最后
  const remaining = registry.filter((c) => !used.has(c.id))
  if (remaining.length > 0) {
    result.push({
      group: { id: 'other', name: '其他', icon: Play, categoryIds: [] },
      categories: remaining,
    })
  }
  return result
}

// ── 主组件 ────────────────────────────────────────────────────────────────────

export default function TemplateEditorPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const isNew = !id || id === 'new'
  const templateId = isNew ? null : Number(id)

  // 数据
  const { data: template, isLoading: templateLoading } = useTemplate(templateId)
  const { data: registry, isLoading: registryLoading } = useStepRegistry()
  const createMutation = useCreateTemplate()
  const updateMutation = useUpdateTemplate()

  // 表单状态
  const [name, setName] = useState('')
  const [slug, setSlug] = useState('')
  const [category, setCategory] = useState('litigation')
  const [description, setDescription] = useState('')
  const [temporalName, setTemporalName] = useState('')
  const [isActive, setIsActive] = useState(true)
  const [steps, setSteps] = useState<StepNode[]>([])
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set(['preparation', 'evidence', 'litigation', 'flow']))
  const [dragActiveId, setDragActiveId] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [insertAtIndex, setInsertAtIndex] = useState<number | null>(null)

  // 加载模板数据
  useEffect(() => {
    if (template) {
      setName(template.name)
      setSlug(template.slug)
      setCategory(template.category)
      setDescription(template.description)
      setTemporalName(template.temporal_workflow_name)
      setIsActive(template.is_active)
      setSteps(Array.isArray(template.steps_schema) ? template.steps_schema : [])
    }
  }, [template])

  // DnD 传感器
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  )

  // 选中的步骤
  const selectedStep = useMemo(
    () => steps.find((s) => s.id === selectedStepId) || null,
    [steps, selectedStepId]
  )

  // 搜索过滤步骤
  const filteredRegistry = useMemo(() => {
    if (!registry) return []
    if (!searchQuery.trim()) return registry
    const q = searchQuery.toLowerCase()
    return registry
      .map((cat) => ({
        ...cat,
        steps: cat.steps.filter(
          (s) =>
            s.name.toLowerCase().includes(q) ||
            s.description.toLowerCase().includes(q) ||
            (s.mcp_tool && s.mcp_tool.toLowerCase().includes(q))
        ),
      }))
      .filter((cat) => cat.steps.length > 0)
  }, [registry, searchQuery])

  // 场景分组
  const scenarioGroups = useMemo(
    () => (filteredRegistry.length > 0 ? groupRegistryByScenario(filteredRegistry, SCENARIO_GROUPS) : []),
    [filteredRegistry],
  )

  // ── 操作 ─────────────────────────────────────────────────────────────────

  const generateStepId = (baseId: string) => {
    const existing = steps.filter((s) => s.id.startsWith(baseId))
    return existing.length === 0 ? baseId : `${baseId}-${existing.length}`
  }

  const addStep = useCallback(
    (def: StepDefinition, insertIndex?: number) => {
      const newStep: StepNode = {
        id: generateStepId(def.id),
        name: def.name,
        type: def.type,
        description: def.description,
        icon: def.icon,
        mcp_tool: def.mcp_tool,
        config: {},
        timeout: def.type === 'gate' || def.type === 'wait' ? undefined : '30s',
        retry_max: def.type === 'gate' || def.type === 'wait' ? 0 : 3,
        on_fail: 'abort',
        position_x: 0,
        position_y: (insertIndex ?? steps.length) * 120,
      }
      setSteps((prev) => {
        if (insertIndex !== undefined && insertIndex >= 0 && insertIndex <= prev.length) {
          const next = [...prev]
          next.splice(insertIndex, 0, newStep)
          return next
        }
        return [...prev, newStep]
      })
      setSelectedStepId(newStep.id)
    },
    [steps]
  )

  const removeStep = useCallback(
    (stepId: string) => {
      setSteps((prev) => prev.filter((s) => s.id !== stepId))
      if (selectedStepId === stepId) setSelectedStepId(null)
    },
    [selectedStepId]
  )

  const duplicateStep = useCallback(
    (stepId: string) => {
      const source = steps.find((s) => s.id === stepId)
      if (!source) return
      const newStep = { ...source, id: generateStepId(source.id) + '-copy' }
      const idx = steps.findIndex((s) => s.id === stepId)
      const newSteps = [...steps]
      newSteps.splice(idx + 1, 0, newStep)
      setSteps(newSteps)
      setSelectedStepId(newStep.id)
    },
    [steps]
  )

  const updateStep = useCallback(
    (stepId: string, updates: Partial<StepNode>) => {
      setSteps((prev) => prev.map((s) => (s.id === stepId ? { ...s, ...updates } : s)))
    },
    []
  )

  // DnD 结束
  const handleDragEnd = (event: DragEndEvent) => {
    setDragActiveId(null)
    const { active, over } = event
    if (!over || active.id === over.id) return

    // 如果是从面板拖入的（active.id 以 "palette-" 开头）
    if (typeof active.id === 'string' && active.id.startsWith('palette-')) {
      const stepDefId = active.id.replace('palette-', '')
      const def = registry?.flatMap((c) => c.steps).find((s) => s.id === stepDefId)
      if (def) addStep(def)
      return
    }

    // 否则是排序
    setSteps((prev) => {
      const oldIndex = prev.findIndex((s) => s.id === active.id)
      const newIndex = prev.findIndex((s) => s.id === over.id)
      if (oldIndex === -1 || newIndex === -1) return prev
      return arrayMove(prev, oldIndex, newIndex)
    })
  }

  // 保存
  const handleSave = async () => {
    if (!name.trim()) {
      toast.error('请输入模板名称')
      return
    }
    setSaving(true)
    try {
      const payload = {
        name,
        slug: slug || undefined,
        category,
        description,
        temporal_workflow_name: temporalName || 'DynamicWorkflow',
        steps,
        is_active: isActive,
      }
      if (isNew) {
        const result = await createMutation.mutateAsync(payload)
        toast.success(result.message)
        navigate(`/admin/workflows/templates/${result.id}/edit`)
      } else {
        const result = await updateMutation.mutateAsync({ id: templateId!, data: payload })
        toast.success(result.message)
      }
    } catch {
      toast.error('保存失败')
    } finally {
      setSaving(false)
    }
  }

  // 切换分类展开
  const toggleCategory = (catId: string) => {
    setExpandedCategories((prev) => {
      const next = new Set(prev)
      if (next.has(catId)) next.delete(catId)
      else next.add(catId)
      return next
    })
  }

  // ── 渲染 ─────────────────────────────────────────────────────────────────

  if (templateLoading || registryLoading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="animate-spin h-8 w-8 border-2 border-primary border-t-transparent rounded-full" />
      </div>
    )
  }

  return (
    <div className="h-screen flex flex-col bg-background">
      {/* 顶部工具栏 */}
      <header className="h-14 border-b flex items-center justify-between px-4 bg-background/95 backdrop-blur shrink-0">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => navigate('/admin/workflows/templates')}>
            <ArrowLeft className="h-4 w-4 mr-1" />
            返回
          </Button>
          <Separator orientation="vertical" className="h-6" />
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="模板名称"
            className="text-lg font-semibold border-none shadow-none h-auto p-0 w-64 focus-visible:ring-0"
          />
          <Badge variant="outline">{category === 'litigation' ? '诉讼' : category === 'preservation' ? '保全' : '执行'}</Badge>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground mr-2">{steps.length} 个步骤</span>
          <Button variant="outline" size="sm" onClick={() => toast.info('撤销功能开发中')}>
            <Undo2 className="h-4 w-4" />
          </Button>
          <Button variant="outline" size="sm" onClick={() => toast.info('重做功能开发中')}>
            <Redo2 className="h-4 w-4" />
          </Button>
          <Separator orientation="vertical" className="h-6" />
          <Button size="sm" onClick={handleSave} disabled={saving}>
            <Save className="h-4 w-4 mr-1" />
            {saving ? '保存中...' : '保存'}
          </Button>
        </div>
      </header>

      {/* 主区域：三栏布局 */}
      <div className="flex-1 flex overflow-hidden">
        {/* 左侧：步骤面板 */}
        <aside className="w-72 border-r bg-muted/30 flex flex-col shrink-0">
          <div className="p-3 border-b">
            <div className="relative">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="搜索步骤或 MCP 工具..."
                className="pl-8 h-9 text-sm"
              />
              {searchQuery && (
                <button
                  className="absolute right-2.5 top-2.5"
                  onClick={() => setSearchQuery('')}
                >
                  <X className="h-4 w-4 text-muted-foreground" />
                </button>
              )}
            </div>
          </div>
          <ScrollArea className="flex-1">
            <div className="p-2">
              {scenarioGroups.map(({ group, categories }) => {
                const GroupIcon = group.icon
                const isExpanded = expandedCategories.has(group.id) || !!searchQuery
                const totalSteps = categories.reduce((n, c) => n + c.steps.length, 0)
                return (
                  <div key={group.id} className="mb-1">
                    <button
                      className="w-full flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-accent text-sm font-medium"
                      onClick={() => toggleCategory(group.id)}
                    >
                      {isExpanded ? (
                        <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                      ) : (
                        <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                      )}
                      <GroupIcon className="h-4 w-4 text-muted-foreground" />
                      <span className="flex-1 text-left">{group.name}</span>
                      <Badge variant="secondary" className="text-xs h-5 px-1.5">
                        {totalSteps}
                      </Badge>
                    </button>
                    {isExpanded && (
                      <div className="ml-4 space-y-0.5 mt-0.5">
                        {categories.map((cat) => (
                          <div key={cat.id}>
                            {categories.length > 1 && (
                              <div className="text-xs text-muted-foreground/60 px-2 pt-1.5 pb-0.5 font-medium">
                                {cat.name}
                              </div>
                            )}
                            {cat.steps.map((step) => {
                              const StepIcon = getIcon(step.icon)
                              return (
                                <button
                                  key={step.id}
                                  className="w-full flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-accent text-left text-sm group"
                                  onClick={() => addStep(step, insertAtIndex ?? undefined)}
                                  title={step.description}
                                >
                                  <StepIcon className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                                  <div className="flex-1 min-w-0">
                                    <div className="truncate">{step.name}</div>
                                    {step.mcp_tool && (
                                      <div className="text-xs text-muted-foreground font-mono truncate">
                                        {step.mcp_tool}
                                      </div>
                                    )}
                                  </div>
                                  <Plus className="h-3.5 w-3.5 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                                </button>
                              )
                            })}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}
              {/* 插入模式提示 */}
              {insertAtIndex !== null && (
                <div className="mx-2 mt-2 p-2 bg-primary/10 border border-primary/30 rounded-lg text-xs text-primary flex items-center justify-between">
                  <span>点击步骤插入到位置 {insertAtIndex + 1}</span>
                  <button className="underline" onClick={() => setInsertAtIndex(null)}>取消</button>
                </div>
              )}
            </div>
          </ScrollArea>
        </aside>

        {/* 中间：画布 */}
        <main className="flex-1 overflow-auto bg-[radial-gradient(circle,_#e5e7eb_1px,_transparent_1px)] bg-[length:20px_20px]" onClick={() => setSelectedStepId(null)}>
          <div className="p-8 max-w-2xl mx-auto">
            {/* 模板基本信息卡片 */}
            <div className="mb-6 p-4 bg-card rounded-lg border shadow-sm">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label className="text-xs">分类</Label>
                  <Select value={category} onValueChange={setCategory}>
                    <SelectTrigger className="h-8 mt-1">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="litigation">诉讼</SelectItem>
                      <SelectItem value="preservation">保全</SelectItem>
                      <SelectItem value="enforcement">执行</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs">Temporal Workflow</Label>
                  <Input
                    value={temporalName}
                    onChange={(e) => setTemporalName(e.target.value)}
                    placeholder="DynamicWorkflow"
                    className="h-8 mt-1 text-sm"
                  />
                </div>
                <div className="col-span-2">
                  <Label className="text-xs">描述</Label>
                  <Textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="描述这个工作流模板的用途..."
                    className="h-16 mt-1 text-sm resize-none"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <Switch checked={isActive} onCheckedChange={setIsActive} id="active" />
                  <Label htmlFor="active" className="text-sm">启用</Label>
                </div>
              </div>
            </div>

            {/* 流程画布 */}
            <DndContext
              sensors={sensors}
              collisionDetection={closestCenter}
              onDragStart={(e: DragStartEvent) => setDragActiveId(String(e.active.id))}
              onDragEnd={handleDragEnd}
            >
              <SortableContext items={steps.map((s) => s.id)} strategy={verticalListSortingStrategy}>
                {steps.length === 0 ? (
                  <div className="border-2 border-dashed rounded-xl p-12 text-center">
                    <Play className="h-10 w-10 mx-auto mb-3 text-muted-foreground/40" />
                    <p className="text-muted-foreground font-medium">从左侧拖入步骤，或点击添加</p>
                    <p className="text-sm text-muted-foreground/70 mt-1">
                      步骤会按顺序执行，支持 activity、审批门、等待事件等类型
                    </p>
                  </div>
                ) : (
                  <div className="space-y-0">
                    {steps.map((step, index) => (
                      <div key={step.id}>
                        {/* 连接线 + 插入按钮 */}
                        {index > 0 && (
                          <div className="flex justify-center py-1 group/insert relative">
                            <div className="w-0.5 h-6 bg-border" />
                            <button
                              className="absolute inset-0 flex items-center justify-center opacity-0 group-hover/insert:opacity-100 transition-opacity"
                              onClick={(e) => {
                                e.stopPropagation()
                                setInsertAtIndex(index)
                                setExpandedCategories(new Set(scenarioGroups.map((g) => g.group.id)))
                              }}
                            >
                              <div className="bg-primary text-primary-foreground rounded-full h-5 w-5 flex items-center justify-center shadow-sm hover:scale-110 transition-transform">
                                <Plus className="h-3 w-3" />
                              </div>
                            </button>
                          </div>
                        )}
                        <SortableStepNode
                          step={step}
                          isSelected={selectedStepId === step.id}
                          onSelect={() => setSelectedStepId(step.id)}
                          onRemove={() => removeStep(step.id)}
                          onDuplicate={() => duplicateStep(step.id)}
                          stepIndex={index}
                        />
                      </div>
                    ))}
                    {/* 添加步骤按钮 */}
                    <div className="flex justify-center py-4">
                      <div className="w-0.5 h-4 bg-border" />
                    </div>
                    <button
                      className="w-full border-2 border-dashed rounded-lg p-4 text-center hover:border-primary/50 hover:bg-accent/50 transition-colors"
                      onClick={() => {
                        setInsertAtIndex(null)
                        setExpandedCategories(new Set(scenarioGroups.map((g) => g.group.id)))
                      }}
                    >
                      <Plus className="h-5 w-5 mx-auto mb-1 text-muted-foreground" />
                      <span className="text-sm text-muted-foreground">添加步骤</span>
                    </button>
                  </div>
                )}
              </SortableContext>

              <DragOverlay>
                {dragActiveId && dragActiveId.startsWith('palette-') ? (
                  <div className="bg-card border rounded-lg p-3 shadow-lg opacity-80">
                    <span className="text-sm font-medium">拖入添加步骤</span>
                  </div>
                ) : null}
              </DragOverlay>
            </DndContext>
          </div>
        </main>

        {/* 右侧：属性面板 */}
        <aside
          className={cn(
            'border-l bg-background flex flex-col shrink-0 transition-all duration-200',
            selectedStep ? 'w-80' : 'w-0 overflow-hidden'
          )}
        >
          {selectedStep && (
            <>
              <div className="p-4 border-b flex items-center justify-between">
                <h3 className="font-semibold text-sm">步骤属性</h3>
                <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => setSelectedStepId(null)}>
                  <X className="h-4 w-4" />
                </Button>
              </div>
              <ScrollArea className="flex-1">
                <div className="p-4 space-y-4">
                  {/* 基本信息 */}
                  <div>
                    <Label className="text-xs">步骤名称</Label>
                    <Input
                      value={selectedStep.name}
                      onChange={(e) => updateStep(selectedStep.id, { name: e.target.value })}
                      className="h-8 mt-1"
                    />
                  </div>
                  <div>
                    <Label className="text-xs">步骤 ID</Label>
                    <Input
                      value={selectedStep.id}
                      onChange={(e) => updateStep(selectedStep.id, { id: e.target.value })}
                      className="h-8 mt-1 font-mono text-sm"
                    />
                  </div>
                  <div>
                    <Label className="text-xs">类型</Label>
                    <div className="mt-1">
                      <Badge variant="outline">{selectedStep.type}</Badge>
                    </div>
                  </div>
                  {selectedStep.mcp_tool && (
                    <div>
                      <Label className="text-xs">MCP 工具</Label>
                      <div className="mt-1 font-mono text-sm bg-muted px-2 py-1 rounded">
                        {selectedStep.mcp_tool}
                      </div>
                    </div>
                  )}
                  <div>
                    <Label className="text-xs">描述</Label>
                    <Textarea
                      value={selectedStep.description || ''}
                      onChange={(e) => updateStep(selectedStep.id, { description: e.target.value })}
                      className="h-16 mt-1 text-sm resize-none"
                    />
                  </div>

                  <Separator />

                  {/* 超时与重试 */}
                  {selectedStep.type !== 'gate' && selectedStep.type !== 'wait' && (
                    <>
                      <div>
                        <Label className="text-xs">超时时间</Label>
                        <Input
                          value={selectedStep.timeout || '30s'}
                          onChange={(e) => updateStep(selectedStep.id, { timeout: e.target.value })}
                          placeholder="30s / 5m / 1h"
                          className="h-8 mt-1 font-mono text-sm"
                        />
                      </div>
                      <div>
                        <Label className="text-xs">最大重试次数</Label>
                        <Input
                          type="number"
                          value={selectedStep.retry_max ?? 3}
                          onChange={(e) => updateStep(selectedStep.id, { retry_max: Number(e.target.value) })}
                          className="h-8 mt-1"
                          min={0}
                          max={10}
                        />
                      </div>
                      <div>
                        <Label className="text-xs">失败策略</Label>
                        <Select
                          value={selectedStep.on_fail || 'abort'}
                          onValueChange={(v) => updateStep(selectedStep.id, { on_fail: v })}
                        >
                          <SelectTrigger className="h-8 mt-1">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="abort">中止流程</SelectItem>
                            <SelectItem value="skip">跳过继续</SelectItem>
                            <SelectItem value="retry">重试</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                    </>
                  )}

                  {/* Gate 专用配置 */}
                  {selectedStep.type === 'gate' && (
                    <>
                      <div>
                        <Label className="text-xs">Signal Key</Label>
                        <Input
                          value={selectedStep.signal_key || ''}
                          onChange={(e) => updateStep(selectedStep.id, { signal_key: e.target.value })}
                          placeholder="e.g. confirm_facts_approved"
                          className="h-8 mt-1 font-mono text-sm"
                        />
                      </div>
                    </>
                  )}

                  {/* Wait 专用配置 */}
                  {selectedStep.type === 'wait' && (
                    <div>
                      <Label className="text-xs">事件类型</Label>
                      <Select
                        value={(selectedStep.config as Record<string, string>)?.event_type || 'custom'}
                        onValueChange={(v) =>
                          updateStep(selectedStep.id, { config: { ...(selectedStep.config || {}), event_type: v } })
                        }
                      >
                        <SelectTrigger className="h-8 mt-1">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="court_sms">法院短信</SelectItem>
                          <SelectItem value="email_reply">邮件回复</SelectItem>
                          <SelectItem value="document_delivery">文书送达</SelectItem>
                          <SelectItem value="custom">自定义</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  )}

                  {/* 高级配置 JSON */}
                  <Separator />
                  <div>
                    <Label className="text-xs">高级配置 (JSON)</Label>
                    <Textarea
                      value={JSON.stringify(selectedStep.config || {}, null, 2)}
                      onChange={(e) => {
                        try {
                          const parsed = JSON.parse(e.target.value)
                          updateStep(selectedStep.id, { config: parsed })
                        } catch {
                          // 允许无效 JSON 输入中
                        }
                      }}
                      className="h-32 mt-1 font-mono text-xs resize-none"
                      placeholder="{}"
                    />
                  </div>
                </div>
              </ScrollArea>
              {/* 底部操作 */}
              <div className="p-3 border-t flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  className="flex-1"
                  onClick={() => duplicateStep(selectedStep.id)}
                >
                  <Copy className="h-3.5 w-3.5 mr-1" />
                  复制
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="flex-1 text-destructive hover:text-destructive"
                  onClick={() => removeStep(selectedStep.id)}
                >
                  <Trash2 className="h-3.5 w-3.5 mr-1" />
                  删除
                </Button>
              </div>
            </>
          )}
        </aside>
      </div>
    </div>
  )
}
