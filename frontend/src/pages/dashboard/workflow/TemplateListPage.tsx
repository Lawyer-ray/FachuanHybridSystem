/**
 * 工作流模板列表页
 */
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  Plus,
  MoreHorizontal,
  Edit,
  Copy,
  Trash2,
  Play,
  Pause,
  GitBranch,
  RefreshCw,
} from 'lucide-react'
import { useTemplates, useDeleteTemplate, useDuplicateTemplate, useUpdateTemplate } from '@/features/workflow/hooks/useTemplates'
import type { WorkflowTemplate } from '@/features/workflow/types'
import { toast } from 'sonner'

const CATEGORY_LABELS: Record<string, string> = {
  litigation: '诉讼',
  preservation: '保全',
  enforcement: '执行',
}

export default function TemplateListPage() {
  const navigate = useNavigate()
  const { data: templates, isLoading, refetch } = useTemplates()
  const deleteMutation = useDeleteTemplate()
  const duplicateMutation = useDuplicateTemplate()
  const updateMutation = useUpdateTemplate()
  const [deleteTarget, setDeleteTarget] = useState<WorkflowTemplate | null>(null)

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      await deleteMutation.mutateAsync(deleteTarget.id)
      toast.success(`已删除「${deleteTarget.name}」`)
    } catch {
      toast.error('删除失败')
    }
    setDeleteTarget(null)
  }

  const handleDuplicate = async (t: WorkflowTemplate) => {
    try {
      const result = await duplicateMutation.mutateAsync(t.id)
      toast.success(result.message)
    } catch {
      toast.error('复制失败')
    }
  }

  const handleToggleActive = async (t: WorkflowTemplate) => {
    try {
      await updateMutation.mutateAsync({ id: t.id, data: { is_active: !t.is_active } })
      toast.success(t.is_active ? '已停用' : '已启用')
    } catch {
      toast.error('操作失败')
    }
  }

  return (
    <div className="container mx-auto py-6 px-4 max-w-6xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">工作流模板</h1>
          <p className="text-sm text-muted-foreground mt-1">
            编排诉讼流程，配置步骤、审批节点和自动化任务
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            <RefreshCw className="h-4 w-4 mr-2" />
            刷新
          </Button>
          <Button size="sm" onClick={() => navigate('/admin/workflows/templates/new')}>
            <Plus className="h-4 w-4 mr-2" />
            新建模板
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-64">
          <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : !templates || templates.length === 0 ? (
        <Card>
          <CardContent className="py-16 text-center">
            <GitBranch className="h-12 w-12 mx-auto mb-4 text-muted-foreground/50" />
            <p className="text-muted-foreground mb-4">还没有工作流模板</p>
            <Button onClick={() => navigate('/admin/workflows/templates/new')}>
              <Plus className="h-4 w-4 mr-2" />
              创建第一个模板
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {templates.map((t) => {
            return (
              <Card
                key={t.id}
                className={`group relative transition-shadow hover:shadow-md cursor-pointer overflow-hidden ${
                  !t.is_active ? 'opacity-60' : ''
                }`}
                onClick={() => navigate(`/admin/workflows/templates/${t.id}/edit`)}
              >
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <CardTitle className="text-base line-clamp-1">{t.name}</CardTitle>
                      <div className="flex items-center gap-2 mt-1">
                        <Badge variant="secondary" className="text-xs">
                          {CATEGORY_LABELS[t.category] || t.category}
                        </Badge>
                        {!t.is_active && (
                          <Badge variant="outline" className="text-xs text-muted-foreground">
                            已停用
                          </Badge>
                        )}
                      </div>
                    </div>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
                        <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                          <MoreHorizontal className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem
                          onClick={(e) => {
                            e.stopPropagation()
                            navigate(`/admin/workflows/templates/${t.id}/edit`)
                          }}
                        >
                          <Edit className="h-4 w-4 mr-2" />
                          编辑
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          onClick={(e) => {
                            e.stopPropagation()
                            handleDuplicate(t)
                          }}
                        >
                          <Copy className="h-4 w-4 mr-2" />
                          复制
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          onClick={(e) => {
                            e.stopPropagation()
                            handleToggleActive(t)
                          }}
                        >
                          {t.is_active ? (
                            <><Pause className="h-4 w-4 mr-2" />停用</>
                          ) : (
                            <><Play className="h-4 w-4 mr-2" />启用</>
                          )}
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem
                          className="text-destructive"
                          onClick={(e) => {
                            e.stopPropagation()
                            setDeleteTarget(t)
                          }}
                        >
                          <Trash2 className="h-4 w-4 mr-2" />
                          删除
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </CardHeader>
                <CardContent className="pt-0">
                  {t.description && (
                    <p className="text-sm text-muted-foreground mb-2 line-clamp-2">{t.description}</p>
                  )}
                  <div className="flex items-center gap-4 text-xs text-muted-foreground min-w-0">
                    <span className="flex items-center gap-1 shrink-0">
                      <GitBranch className="h-3 w-3" />
                      {t.steps_count ?? 0} 个步骤
                    </span>
                    {t.temporal_workflow_name && (
                      <span className="font-mono text-xs bg-muted px-1.5 py-0.5 rounded truncate min-w-0">
                        {t.temporal_workflow_name}
                      </span>
                    )}
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}

      {/* 删除确认弹窗 */}
      <AlertDialog open={!!deleteTarget} onOpenChange={() => setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除</AlertDialogTitle>
            <AlertDialogDescription>
              确定要删除模板「{deleteTarget?.name}」吗？此操作不可撤销。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-destructive text-destructive-foreground">
              删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
