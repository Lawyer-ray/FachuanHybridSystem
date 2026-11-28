/**
 * 技能抽屉外壳：两个 tab（我的 / 系统）、加载/错误态、编辑器二级视图、删除确认。
 *
 * 开关从 `../skill-drawer` 读（会话侧栏的「技能」按钮与 `/` 菜单的
 * `manage-skills` 命令都写同一个 store），所以本组件不接 props。
 *
 * 取数只有一份清单查询（`['agent-skills']`，与 Composer 的 `/` 菜单同键）：
 * 写动作后的缓存失效由 `use-skill-mutations` 统一做，这里不另建缓存。
 *
 * 未保存改动的 `dirty` 由本组件持有，因为 Sheet 的 Esc / 点遮罩关闭不经过
 * `SkillEditor` 的取消按钮——不在这一层拦一道，律师写了几百字的正文会静默丢失。
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Sparkles } from 'lucide-react'
import { toast } from 'sonner'

import { fetchAgentSkills } from '../../skill-api'
import { useSkillDrawer } from '../../skill-drawer'
import type { AgentSkill } from '../../types'
import { ErrorBlock, LoadingBlock } from '@/components/shared/AsyncState'
import { ConfirmDialog } from '@/components/shared/ConfirmDialog'
import { Sheet, SheetBody, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { errMessage } from '@/lib/errors'
import { SkillEditor, type SkillEditorTarget } from './SkillEditor'
import { SkillList, type SkillTab } from './SkillList'
import { SKILLS_QUERY_KEY, useSkillMutations } from './use-skill-mutations'

const TABS: { id: SkillTab; label: string }[] = [
  { id: 'mine', label: '我的' },
  { id: 'system', label: '系统' },
]

export function SkillDrawer() {
  const open = useSkillDrawer((s) => s.open)
  const closeDrawer = useSkillDrawer((s) => s.closeDrawer)
  const [tab, setTab] = useState<SkillTab>('mine')
  /** 二级视图：有值时不显示 tab 与列表 */
  const [editor, setEditor] = useState<SkillEditorTarget | null>(null)
  const [editorDirty, setEditorDirty] = useState(false)
  /** 未保存改动时点关闭（X / Esc / 遮罩）：先问一句再关抽屉 */
  const [confirmClose, setConfirmClose] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<AgentSkill | null>(null)

  const skillsQuery = useQuery({
    queryKey: SKILLS_QUERY_KEY,
    queryFn: fetchAgentSkills,
    enabled: open,
    staleTime: 30_000,
  })
  const { deleteMutation, duplicateMutation, toggleMutation } = useSkillMutations()

  const skills = skillsQuery.data?.skills ?? []
  const mine = skills.filter((skill) => skill.source === 'user')
  const system = skills.filter((skill) => skill.source === 'builtin')
  /** 只有正在写的那一行置忙；其余行照常可点 */
  const busyKey =
    (toggleMutation.isPending ? toggleMutation.variables?.key : null) ??
    (deleteMutation.isPending ? deleteMutation.variables : null) ??
    (duplicateMutation.isPending ? duplicateMutation.variables : null) ??
    null

  const closeEditor = () => {
    setEditor(null)
    setEditorDirty(false)
  }
  const closeAll = () => {
    closeEditor()
    closeDrawer()
  }
  /** Sheet 的关闭（X / Esc / 遮罩）：有未保存改动先问一句 */
  const requestClose = () => {
    if (editor && editorDirty) setConfirmClose(true)
    else closeAll()
  }

  const handleToggle = (skill: AgentSkill, enabled: boolean) =>
    toggleMutation.mutate({ key: skill.key, title: skill.title, enabled })

  const handleDuplicate = (skill: AgentSkill) =>
    duplicateMutation.mutate(skill.key, {
      onSuccess: () => {
        toast.success(`已复制「${skill.title}」到我的技能`)
        setTab('mine')
      },
      onError: (error) => toast.error('复制失败', { description: errMessage(error, '请稍后重试') }),
    })

  const handleDelete = () => {
    if (!deleteTarget) return
    deleteMutation.mutate(deleteTarget.key, {
      onSuccess: () => toast.success(`已删除「${deleteTarget.title}」`),
      onError: (error) => toast.error('删除失败', { description: errMessage(error, '请稍后重试') }),
    })
  }

  return (
    <Sheet
      open={open}
      onOpenChange={(next) => {
        if (!next) requestClose()
      }}
    >
      <SheetContent className="max-w-[min(620px,calc(100vw-1.75rem))]">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 opacity-70" />
            个人技能
          </SheetTitle>
          <p className="mt-1 text-[12px] leading-relaxed text-muted-foreground">
            技能是交给 AI 执行的做法说明，用 <code className="font-mono text-[11px]">/skill:名字</code> 点名使用；
            描述会在启用索引后进入系统提示。它<strong className="font-medium text-foreground">不会</strong>
            改变审批等级，启停从下一轮对话生效。
          </p>
        </SheetHeader>

        <SheetBody className="px-6 pt-4">
          {editor ? (
            <SkillEditor
              target={editor}
              onClose={closeEditor}
              onDirtyChange={setEditorDirty}
              // 新建可能在「系统」tab 里发起：保存成功后切回「我的」，否则新技能看不见
              onSaved={() => setTab('mine')}
            />
          ) : (
            <>
              <div role="tablist" aria-label="技能来源" className="mb-3 flex gap-1 rounded-[7px] bg-secondary/60 p-[3px]">
                {TABS.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    role="tab"
                    aria-selected={tab === item.id}
                    onClick={() => setTab(item.id)}
                    className={`flex-1 rounded-[5px] px-2 py-1 text-[11.5px] font-medium transition-colors ${
                      tab === item.id ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>

              {skillsQuery.isLoading ? (
                <LoadingBlock size="sm" />
              ) : skillsQuery.isError ? (
                <ErrorBlock error={skillsQuery.error} fallback="技能清单加载失败" onRetry={() => void skillsQuery.refetch()} />
              ) : (
                <SkillList
                  tab={tab}
                  skills={tab === 'mine' ? mine : system}
                  busyKey={busyKey}
                  onCreate={() => setEditor({ mode: 'create' })}
                  onEdit={(skill) => setEditor({ mode: 'edit', skill })}
                  onDelete={setDeleteTarget}
                  onDuplicate={handleDuplicate}
                  onToggle={handleToggle}
                />
              )}
            </>
          )}
        </SheetBody>
      </SheetContent>

      <ConfirmDialog
        open={confirmClose}
        onOpenChange={(next) => {
          if (!next) setConfirmClose(false)
        }}
        title="放弃未保存的修改？"
        description="关掉之后，这次填写的内容不会保留。"
        confirmText="放弃修改"
        cancelText="继续编辑"
        tone="destructive"
        onConfirm={() => {
          setConfirmClose(false)
          closeAll()
        }}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(next) => {
          if (!next) setDeleteTarget(null)
        }}
        title={`删除「${deleteTarget?.title ?? ''}」？`}
        description="删除后不能恢复；只是暂时不想让它生效的话，关掉开关即可。"
        confirmText="删除"
        cancelText="取消"
        tone="destructive"
        pending={deleteMutation.isPending}
        onConfirm={handleDelete}
      />
    </Sheet>
  )
}
