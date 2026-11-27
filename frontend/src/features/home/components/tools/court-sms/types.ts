/**
 * 法院短信流程的**对外类型契约**：阶段枚举、材料来源、状态机快照与 hook 返回形状。
 *
 * 为什么从 use-court-sms.ts 拆出来：状态机（几百行编排逻辑）与「它对外长什么样」
 * 是两件事——弹窗组件、弹窗测试、卡片都只消费这些类型，不该为了拿一个类型而
 * 拖进整个状态机模块。类型单独成文件后：
 * - 消费方 `import type` 只解析这一份声明，改状态机内部不会牵动它们；
 * - 状态机文件也能回到「只有实现」的可读形态。
 *
 * 纯类型文件：运行时无产物（`import type` 全部擦除），不改变任何加载顺序。
 */
import type { CourtSmsDetail, CourtSmsMaterialIntake } from '../../../api'
import type { SmsTerminal } from './stages'

/** 弹窗编排阶段：idle 未提交 / submitting 提交中 / processing 处理中(轮询) / done 终态 / timeout 等待超时 */
export type SmsPhase = 'idle' | 'submitting' | 'processing' | 'done' | 'timeout'

/**
 * 本次流程的**材料来源**，只影响文案不改流程：
 * - ``sms``：法院短信通道（短信原文 → 解析下载链接 → 下载 → 匹配…）
 * - ``material``：客户转交通道（拖入的文件 → 落盘 → 直进匹配，无下载阶段）
 */
export type SmsSource = 'sms' | 'material'

export interface CourtSmsFlowState {
  phase: SmsPhase
  /** 终态语义（phase=done 时有值） */
  outcome: SmsTerminal | null
  smsId: number | null
  /** 最近一次详情（步进器 / 结果区渲染用；提交瞬间可能还没有） */
  detail: CourtSmsDetail | null
  /** 观测到的最大阶段下标（failed 时状态机不告诉停在哪步，用它兜底） */
  stage: number
  /** 提交动作本身的失败（后端没建出记录，没有 id 可轮询） */
  submitError: string | null
  /** assign / retry 按钮的 busy */
  actionBusy: boolean
  /** 材料来源（步进器文案/阶段裁剪用） */
  source: SmsSource
  /** 客户转交通道的入库明细（saved/skipped），短信通道为 null */
  intake: CourtSmsMaterialIntake | null
}

export interface UseCourtSmsResult extends CourtSmsFlowState {
  submit: (content: string) => Promise<boolean>
  /** 提交客户转交的材料（多文件）；成功返回 true，部分文件被跳过时同时回填入参 intake */
  submitFiles: (files: File[], note?: string) => Promise<boolean>
  /** 历史记录直接进入跟进态：按 id 拉详情并轮询（终态立即呈现，可继续人工分配/重试/下载） */
  openExisting: (smsId: number) => void
  /** 人工分配案件；成功后回到 processing 继续轮询到终态 */
  assignCase: (caseId: number) => Promise<void>
  /** 重新处理；同样回到 processing */
  retry: () => Promise<void>
  /** 超时后继续等待（只恢复轮询，不重跑后端流程） */
  resume: () => void
  /** 终止并彻底删除任务（含 Django-Q 重试），成功后流程回到 idle */
  abortAndRemove: () => Promise<void>
  /** 重开弹窗时拉一次最新详情；非终态则续上轮询 */
  refresh: () => Promise<void>
  /** 清空流程（回到 idle） */
  reset: () => void
}
