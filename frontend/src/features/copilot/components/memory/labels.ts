/**
 * 记忆界面的类型名 / 作用域名 / 字符上限（抽屉与策展对话框共用）。
 *
 * `KIND_LABEL` 原先在 MemoryDrawer 与 MemoryPromoteDialog 各写一份（值完全相同），
 * 改一处忘一处的风险是实际发生过的，故抽到本文件做单一来源。
 */

import type { MemoryKind, MemoryScope } from '../../memory-api'

/** 类型中文名与注入优先级一致：纠正 > 偏好 > 惯例 > 事实 */
export const KIND_LABEL: Record<MemoryKind, string> = {
  correction: '纠正',
  preference: '偏好',
  procedure: '惯例',
  fact: '事实',
  // 策展不提供「操作指引」：指引是该由管理员直接撰写的长篇规范，
  // 从个人短记忆「提炼」成 8000 字 SOP 不合理（见 MEMORY_KINDS 注释）。
  playbook: '操作指引',
}

export const SCOPE_LABEL: Record<MemoryScope, string> = {
  lawyer: '我的记忆',
  team: '团队记忆',
  law_firm: '律所记忆',
}

/** 律所层只接受惯例/偏好——具体事实进律所层没有正当理由（与后端同口径） */
export const LAW_FIRM_KINDS: MemoryKind[] = ['procedure', 'preference']

/** 团队层可接受惯例/偏好/事实（事实只在团队内共享） */
export const TEAM_KINDS: MemoryKind[] = ['procedure', 'preference', 'fact']

/** 策展规则内容的字符上限（与后端 promote_memory 同口径） */
export const MAX_RULE_CHARS = 500

/** 短规则的字符上限（后端 create_memory：200 字 × 5） */
export const MAX_CONTENT = 1000
/** 操作指引的上限（后端 PLAYBOOK_MAX_CHARS） */
export const MAX_PLAYBOOK = 8000
