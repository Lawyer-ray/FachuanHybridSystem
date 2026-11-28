/**
 * 技能抽屉的状态与动作：取数（清单 + 配额）、tab、二级视图、两个确认框、行内动作。
 *
 * 为什么从 `SkillDrawer.tsx` 抽出来：那个文件原本 198 行里有一半是这套编排，加 4 tab /
 * 配额 / 双轨徽标后必然撞 350 行软红线；更关键的是「关闭抽屉要不要二次确认」这类
 * 判断只要有一处写错就会丢草稿，把它收在一个 hook 里只需审一次。
 *
 * 未保存改动的 `dirty` 由本 hook 持有：Sheet 的 Esc / 遮罩关闭不经过 `SkillEditor`
 * 的取消按钮，不在这一层拦一道，律师写了几百字的正文会静默丢失。
 *
 * 取数只有一份清单查询（`SKILLS_QUERY_KEY`，与 Composer 的 `/` 菜单同键）：
 * 写动作后的缓存失效由 `use-skill-mutations` 统一做，这里不另建缓存。
 */

import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { toast } from 'sonner'

import { errMessage } from '@/lib/errors'

import { fetchAgentSkillQuota, fetchAgentSkills } from '../../skill-api'
import { useSkillDrawer } from '../../skill-drawer'
import type { AgentSkill, AgentSkillScope } from '../../types'
import type { SkillEditorTarget } from './SkillEditor'
import {
  skillInTab,
  skillTabForScope,
  skillTabQuota,
  skillTabScope,
  visibleSkillTabs,
  type SkillCreateScope,
  type SkillTabId,
} from './skill-tabs'
import { SKILL_QUOTA_QUERY_KEY, SKILLS_QUERY_KEY, useSkillMutations } from './use-skill-mutations'

export function useSkillDrawerState() {
  const open = useSkillDrawer((s) => s.open)
  const closeDrawer = useSkillDrawer((s) => s.closeDrawer)
  const [tab, setTab] = useState<SkillTabId>('mine')
  /** 二级视图：有值时不显示 tab 与列表 */
  const [editor, setEditor] = useState<SkillEditorTarget | null>(null)
  const [editorDirty, setEditorDirty] = useState(false)
  /** 未保存改动时点关闭（X / Esc / 遮罩）：先问一句再关抽屉 */
  const [confirmClose, setConfirmClose] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<AgentSkill | null>(null)

  const skillsQuery = useQuery({
    queryKey: SKILLS_QUERY_KEY,
    queryFn: () => fetchAgentSkills(),
    enabled: open,
    staleTime: 30_000,
  })
  const quotaQuery = useQuery({
    queryKey: SKILL_QUOTA_QUERY_KEY,
    queryFn: fetchAgentSkillQuota,
    enabled: open,
    staleTime: 60_000,
  })
  const { deleteMutation, duplicateMutation, toggleMutation } = useSkillMutations()

  const skills = skillsQuery.data?.skills ?? []
  const quota = quotaQuery.data
  const tabs = visibleSkillTabs(skills, quota)
  // 权限变化后当前 tab 可能已经不在了（例如所内条目清空且不再是管理员）：回落到「我的」
  const activeTab: SkillTabId = tabs.includes(tab) ? tab : 'mine'
  const tabSkills = skills.filter((skill) => skillInTab(skill, activeTab))
  const tabQuota = skillTabQuota(activeTab, quota)

  const activeScope = skillTabScope(activeTab)
  const createScope: SkillCreateScope | null =
    activeScope === 'lawyer' ? 'lawyer' : activeScope === 'law_firm' && quota?.can_create_firm === true ? 'law_firm' : null

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

  const openCreate = () => {
    if (createScope) setEditor({ mode: 'create', scope: createScope })
  }
  const openEdit = (skill: AgentSkill) => setEditor({ mode: 'edit', skill })
  /** 保存成功后切到刚写的那一层（在「所内」新建却停在「我的」会看不见新技能） */
  const handleSaved = (scope: AgentSkillScope) => setTab(skillTabForScope(scope))

  const handleToggle = (skill: AgentSkill, enabled: boolean) =>
    // 个人技能改本体；内置 / 共享技能写的只是本人偏好（服务端语义，见 CONTRACT §4.2）
    toggleMutation.mutate({ key: skill.key, title: skill.title, enabled, preferenceOnly: skill.scope !== 'lawyer' })

  const handleDuplicate = (skill: AgentSkill) =>
    duplicateMutation.mutate(skill.key, {
      onSuccess: () => {
        toast.success(`已复制「${skill.title}」到我的技能`)
        setTab('mine')
      },
      onError: (error) => toast.error('复制失败', { description: errMessage(error, '请稍后重试') }),
    })

  const confirmDelete = () => {
    if (!deleteTarget) return
    deleteMutation.mutate(deleteTarget.key, {
      onSuccess: () => toast.success(`已删除「${deleteTarget.title}」`),
      onError: (error) => toast.error('删除失败', { description: errMessage(error, '请稍后重试') }),
    })
  }

  return {
    // 外壳
    open,
    requestClose,
    closeAll,
    confirmClose,
    setConfirmClose,
    // tab 与配额
    activeTab,
    setTab,
    skills,
    tabSkills,
    tabQuota,
    quota,
    // 列表三态
    skillsLoading: skillsQuery.isLoading,
    skillsError: skillsQuery.isError,
    skillsErrorObject: skillsQuery.error,
    refetchSkills: () => void skillsQuery.refetch(),
    // 二级视图
    editor,
    closeEditor,
    openCreate,
    openEdit,
    createScope,
    handleSaved,
    setEditorDirty,
    // 行内动作
    busyKey,
    handleToggle,
    handleDuplicate,
    deleteTarget,
    setDeleteTarget,
    confirmDelete,
    deletePending: deleteMutation.isPending,
  }
}
