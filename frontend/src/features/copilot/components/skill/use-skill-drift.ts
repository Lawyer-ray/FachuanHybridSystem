/**
 * 命令名漂移：`/skill:<name>` 的生效赢家跨层换人时的行内徽标与一次性提示。
 *
 * 为什么这件事只能在抽屉里做、且必须只读服务端字段：赢家是 `resolve.
 * list_visible_skills` 算出来的（「先按偏好过滤 enabled，再按 name 级联去重」这个
 * 顺序本身是语义——停用个人版要能回落到所内版）。前端若自己比 `scope_weight` 重算
 * 一遍级联，上面那条顺序一旦写错就会给出与模型实际执行不同的答案，而且不报错。
 * 所以本文件只读条目的 `effective`（服务端已判「本轮真的胜出」）与 `key`。
 *
 * 「跨层切换」的判定：同一个 name 的胜出条目 **key 变了**。key 里带作用域
 * （`skill:<uuid>` / `builtin:<name>`），换 key 就是换了一条实际交付的技能——典型
 * 场景是律师把个人版关掉、所内版顶上来。
 *
 * 提示去重口径：`localStorage` 按 **user + name** 记一次（键名见
 * `skillDriftToastKey`），不用裸 name——同一台机器换个人登录时，那个名字的层级
 * 归属是另一件事，拿裸 name 记会让第二个人永远收不到提示。同一次挂载内另有
 * 内存去重：清单每次刷新都会重算赢家，没有这一层会在同一次停留里连弹好几遍。
 */

import { useEffect, useMemo, useRef } from 'react'
import { toast } from 'sonner'

import { useAuth } from '@/features/auth'

import type { AgentSkill } from '../../skill-types'
import { skillScopeLabel } from './skill-status'

/** 存储键前缀：`fachuan:skill-drift-toast:v1:<userKey>:<name>` */
const DRIFT_STORAGE_PREFIX = 'fachuan:skill-drift-toast:v1'

/** 存储键（导出给测试与排障用）：user 优先用不可变的 id，退到用户名，都没有才 `anon` */
export function skillDriftToastKey(userKey: string, name: string): string {
  return `${DRIFT_STORAGE_PREFIX}:${userKey}:${name}`
}

function toastSeen(key: string): boolean {
  try {
    return localStorage.getItem(key) === '1'
  } catch {
    // 隐私模式读不到存储：当作「已提示过」，避免每次重渲染都重弹一遍
    return true
  }
}

function markToastSeen(key: string): void {
  try {
    localStorage.setItem(key, '1')
  } catch {
    // 写不进去就下次再提示一次；不能因此阻断抽屉的使用
  }
}

/** 当前用户在这一台机器上的稳定标识（换人登录必须换键，见文件头） */
function useUserKey(): string {
  return useAuth((state) => {
    const user = state.user
    if (!user) return 'anon'
    // id=0 是 `init()` 的占位（还没回填 /organization/me），这时用用户名
    return user.id ? `u${user.id}` : user.username ? `n${user.username}` : 'anon'
  })
}

/** name → 本轮真正胜出的那一条（`effective` 是服务端事实，前端不推算级联） */
function winnersByName(skills: AgentSkill[]): Map<string, AgentSkill> {
  const winners = new Map<string, AgentSkill>()
  for (const skill of skills) {
    if (skill.effective) winners.set(skill.name, skill)
  }
  return winners
}

/**
 * 同名条目 ≥2 的 command name。
 *
 * 只有这种名字才值得在行上标「当前生效」：同一个名字只有一条时，标了等于把「已生效」
 * 徽标再说一遍；有同名竞争时，律师才真的需要知道 `/skill:名字` 现在展开的是哪一条。
 */
export function contendedSkillNames(skills: AgentSkill[]): Set<string> {
  const counts = new Map<string, number>()
  for (const skill of skills) counts.set(skill.name, (counts.get(skill.name) ?? 0) + 1)
  return new Set([...counts.entries()].filter(([, count]) => count > 1).map(([name]) => name))
}

/**
 * 观察清单里的赢家变化：换人就 toast 一次，并把「同名竞争」的名字集合返回给列表行。
 *
 * 第一次观察只记基线不提示：挂载时还不知道「之前是谁」，把首次渲染当成漂移会在每次
 * 打开抽屉时都弹一遍。
 */
export function useSkillDrift(skills: AgentSkill[]): Set<string> {
  const userKey = useUserKey()
  const previous = useRef<Map<string, AgentSkill> | null>(null)
  /**
   * 本次挂载已提示过的键。存**存储键**（user + name）而不是裸 name：同一台机器换人
   * 登录时，那个名字的层级归属是另一件事，裸 name 去重会让第二个人永远收不到提示。
   */
  const notified = useRef(new Set<string>())

  useEffect(() => {
    const current = winnersByName(skills)
    const baseline = previous.current
    previous.current = current
    if (!baseline) return

    for (const [name, winner] of current) {
      const before = baseline.get(name)
      if (!before || before.key === winner.key) continue
      if (notified.current.has(name)) continue
      const storageKey = skillDriftToastKey(userKey, name)
      if (notified.current.has(storageKey) || toastSeen(storageKey)) continue
      notified.current.add(storageKey)
      markToastSeen(storageKey)
      toast.info(`/skill:${name} 改由「${skillScopeLabel(winner.scope)}」版生效`, {
        description: `原来是「${skillScopeLabel(before.scope)}」版；下一轮对话起按「${winner.title}」执行`,
      })
    }
  }, [skills, userKey])

  return useMemo(() => contendedSkillNames(skills), [skills])
}
