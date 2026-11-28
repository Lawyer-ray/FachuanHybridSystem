/**
 * 技能抽屉的五个写入动作：新建 / 修改 / 删除 / 复制 / 启停。
 *
 * 与 `memory/use-memory-mutations` 同构：所有写动作共用同一个缓存失效口径，
 * 各写一遍迟早漏一条（表现是「保存后列表不变」「复制出来的看不到」）。
 *
 * 启停是**乐观更新**：开关是个一眼就能看出结果的控件，等一次往返再变色
 * 会让人以为没点到。失败回滚到请求前的清单并提示原因（服务端状态才是真相，
 * `onSettled` 再拉一次对齐）；成功 toast 明说「下一轮对话生效」——可用技能集合
 * 是每轮开始前由 `resolve_for_user` 解析的，当前这一轮不会变。
 *
 * 共享技能（团队 / 所内）的启停写的**只是本人偏好**（服务端只 upsert
 * `AgentSkillPreference`），所以 toast 必须补一句「仅对你生效」：说成「已停用」会
 * 让律师以为把全所的这一条关了。
 */

import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { errMessage } from '@/lib/errors'
import {
  createAgentSkill,
  deleteAgentSkill,
  duplicateAgentSkill,
  setAgentSkillEnabled,
  updateAgentSkill,
} from '../../skill-api'
import type { AgentSkillCreateInput, AgentSkillList, AgentSkillUpdateInput } from '../../types'

/**
 * 技能清单的查询键：与 `Composer` 的 `['agent-skills']`（`/` 菜单数据源）**必须同键**。
 * 抽屉里改完这里失效它，输入框的 `/skill:` 候选才跟着变。
 */
export const SKILLS_QUERY_KEY = ['agent-skills']

/**
 * 技能配额的查询键：与清单分开缓存（启停不改变占用，不必连带重拉）。
 *
 * 但**新建 / 删除 / 下线会改变占用**，所以 `invalidate` 必须连它一起失效——否则
 * 配额条要等 60s staleTime 才更新，刚建完一条却还显示「已用 3 / 20」。
 */
export const SKILL_QUOTA_QUERY_KEY = ['agent-skill-quota']

/** 启停参数：`title` 只用于 toast 文案（key 是人看不懂的 `builtin:…` / `skill:…`） */
interface ToggleVars {
  key: string
  title: string
  enabled: boolean
  /** 共享技能的开关只写本人偏好（不影响其他律师），文案要照实说 */
  preferenceOnly: boolean
}

export function useSkillMutations() {
  const queryClient = useQueryClient()

  /** 失效口径本体：写动作成功、启停落定都走它（清单 + 配额一起，口径只写一处） */
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: SKILLS_QUERY_KEY })
    void queryClient.invalidateQueries({ queryKey: SKILL_QUOTA_QUERY_KEY })
  }

  const createMutation = useMutation({
    mutationFn: (input: AgentSkillCreateInput) => createAgentSkill(input),
    onSuccess: invalidate,
  })

  const updateMutation = useMutation({
    mutationFn: (vars: { key: string; input: AgentSkillUpdateInput }) => updateAgentSkill(vars.key, vars.input),
    onSuccess: invalidate,
  })

  const deleteMutation = useMutation({
    mutationFn: (key: string) => deleteAgentSkill(key),
    onSuccess: invalidate,
  })

  const duplicateMutation = useMutation({
    mutationFn: (key: string) => duplicateAgentSkill(key),
    onSuccess: invalidate,
  })

  const toggleMutation = useMutation({
    mutationFn: ({ key, enabled }: ToggleVars) => setAgentSkillEnabled(key, enabled),
    onMutate: async ({ key, enabled }) => {
      // 先停掉在途的清单请求，否则它回来会把乐观值覆盖回旧值
      await queryClient.cancelQueries({ queryKey: SKILLS_QUERY_KEY })
      const previous = queryClient.getQueryData<AgentSkillList>(SKILLS_QUERY_KEY)
      queryClient.setQueryData<AgentSkillList>(SKILLS_QUERY_KEY, (old) =>
        old ? { skills: old.skills.map((skill) => (skill.key === key ? { ...skill, enabled } : skill)) } : old,
      )
      return { previous }
    },
    onError: (error, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(SKILLS_QUERY_KEY, context.previous)
      toast.error('启停失败', { description: errMessage(error, '请求失败，请稍后重试') })
    },
    onSuccess: (_receipt, { title, enabled, preferenceOnly }) => {
      toast.success(enabled ? `已启用「${title}」` : `已停用「${title}」`, {
        description: preferenceOnly ? '仅对你生效，不影响其他律师；下一轮对话生效' : '下一轮对话生效',
      })
    },
    onSettled: invalidate,
  })

  return { createMutation, updateMutation, deleteMutation, duplicateMutation, toggleMutation, invalidate }
}
