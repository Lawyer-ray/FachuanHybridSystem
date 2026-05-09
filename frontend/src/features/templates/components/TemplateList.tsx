import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router'
import { Plus, Download, Search, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { EmptyState } from '@/components/shared/EmptyState'
import { PATHS, generatePath } from '@/routes/paths'
import { useTemplates } from '../hooks/use-templates'
import {
  TEMPLATE_TYPE_LABELS, CONTRACT_SUB_TYPE_LABELS, CASE_SUB_TYPE_LABELS, ARCHIVE_SUB_TYPE_LABELS,
  type TemplateType, type Template,
} from '../types'

const TYPE_FILTERS = ['all', 'contract', 'case', 'archive'] as const

function getSubTypeLabel(t: Template): string {
  if (t.template_type === 'contract' && t.contract_sub_type) return CONTRACT_SUB_TYPE_LABELS[t.contract_sub_type] || t.contract_sub_type
  if (t.template_type === 'case' && t.case_sub_type) return CASE_SUB_TYPE_LABELS[t.case_sub_type] || t.case_sub_type
  if (t.template_type === 'archive' && t.archive_sub_type) return ARCHIVE_SUB_TYPE_LABELS[t.archive_sub_type] || t.archive_sub_type
  return '-'
}

function TableSkeleton() {
  return (
    <>{Array.from({ length: 5 }).map((_, i) => (
      <TableRow key={i}>
        {[60, 30, 200, 100, 120, 80, 60, 120, 80, 80].map((w, j) => (
          <TableCell key={j}><div className={`bg-muted h-4 w-${Math.round(w / 8)} animate-pulse rounded`} /></TableCell>
        ))}
      </TableRow>
    ))}</>
  )
}

export function TemplateList() {
  const navigate = useNavigate()
  const { data: templates, isLoading } = useTemplates()
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState<string>('all')
  const [activeOnly, setActiveOnly] = useState(false)

  const filtered = useMemo(() => {
    const list = templates ?? []
    return list.filter((t) => {
      if (search && !t.name.toLowerCase().includes(search.toLowerCase())) return false
      if (typeFilter !== 'all' && t.template_type !== typeFilter) return false
      if (activeOnly && !t.is_active) return false
      return true
    })
  }, [templates, search, typeFilter, activeOnly])

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold">文件模板</h1>
          <p className="text-muted-foreground text-sm mt-1">管理法律文书、合同及归档文件的模板，支持占位符自动填充</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm"><Download className="mr-1.5 size-4" />初始化默认模板</Button>
          <Button size="sm"><Plus className="mr-1.5 size-4" />新建模板</Button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px] max-w-xs">
          <Search className="text-muted-foreground absolute left-3 top-1/2 size-4 -translate-y-1/2" />
          <Input
            type="text"
            placeholder="搜索模板名称..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9 pr-9"
          />
          {search && (
            <Button type="button" variant="ghost" size="sm" onClick={() => setSearch('')} className="absolute right-1 top-1/2 size-7 -translate-y-1/2 p-0 hover:bg-transparent">
              <X className="text-muted-foreground hover:text-foreground size-4" />
            </Button>
          )}
        </div>
        <div className="flex gap-1">
          {TYPE_FILTERS.map((t) => (
            <Button
              key={t}
              variant={t === typeFilter ? 'default' : 'outline'}
              size="sm"
              onClick={() => setTypeFilter(t)}
              className="h-8 text-xs"
            >
              {t === 'all' ? '全部' : TEMPLATE_TYPE_LABELS[t as TemplateType].replace('文件模板', '')}
            </Button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-sm cursor-pointer text-muted-foreground">
          <input type="checkbox" checked={activeOnly} onChange={(e) => setActiveOnly(e.target.checked)} className="accent-primary" />
          仅显示启用
        </label>
      </div>

      {/* Table */}
      {filtered.length === 0 && !isLoading ? (
        <EmptyState icon="file" title="没有匹配的模板" description="尝试调整筛选条件或创建新模板" />
      ) : (
        <div className="overflow-x-auto rounded-md border">
          <Table className="min-w-[800px]">
            <TableHeader>
              <TableRow>
                <TableHead className="w-[60px]">ID</TableHead>
                <TableHead className="w-[40px]">状态</TableHead>
                <TableHead>模板名称</TableHead>
                <TableHead className="w-[120px]">类型</TableHead>
                <TableHead className="w-[130px]">子类型</TableHead>
                <TableHead className="w-[90px]">文件来源</TableHead>
                <TableHead className="w-[70px]">占位符</TableHead>
                <TableHead className="w-[120px]">适用范围</TableHead>
                <TableHead className="w-[90px]">更新时间</TableHead>
                <TableHead className="w-[80px]">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? <TableSkeleton /> : filtered.map((t) => {
                const typeKey = t.template_type as TemplateType
                const phCount = t.placeholders?.length ?? 0
                const undefCount = t.undefined_placeholders?.length ?? 0

                return (
                  <TableRow
                    key={t.id}
                    onClick={() => navigate(generatePath.templateDetail?.(String(t.id)) ?? `${PATHS.ADMIN_TEMPLATES}/${t.id}`)}
                    className="cursor-pointer hover:bg-muted/50 transition-colors"
                  >
                    <TableCell className="text-muted-foreground text-sm">{t.id}</TableCell>
                    <TableCell>
                      {t.is_active
                        ? <span className="text-status-green text-sm">●</span>
                        : <span className="text-muted-foreground text-sm">○</span>}
                    </TableCell>
                    <TableCell className="font-medium text-sm">{t.name}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className="text-xs">{TEMPLATE_TYPE_LABELS[typeKey] ?? t.template_type}</Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground text-sm">{getSubTypeLabel(t)}</TableCell>
                    <TableCell>
                      {t.file
                        ? <span className="text-status-green text-xs">上传文件</span>
                        : t.file_path
                          ? <span className="text-xs text-indigo-500">路径引用</span>
                          : <span className="text-muted-foreground text-xs">-</span>}
                    </TableCell>
                    <TableCell>
                      <span className="text-sm">{phCount}</span>
                      {undefCount > 0 && (
                        <span className="ml-1 text-[10px] text-status-red bg-status-red-bg px-1.5 py-0.5 rounded-full">
                          {undefCount} !
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="text-muted-foreground text-xs truncate max-w-[120px]">
                      {t.case_types?.length || t.contract_types?.length
                        ? [...(t.case_types || []), ...(t.contract_types || [])].join('、')
                        : '通用'}
                    </TableCell>
                    <TableCell className="text-muted-foreground text-sm">{t.updated_at}</TableCell>
                    <TableCell>
                      <Button variant="outline" size="sm" className="h-7 text-xs" onClick={(e) => e.stopPropagation()}>
                        查看
                      </Button>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}

export default TemplateList
