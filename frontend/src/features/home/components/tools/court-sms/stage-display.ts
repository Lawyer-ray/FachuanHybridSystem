/**
 * 「后端详情 + 观测到的最大阶段」→ 步进器要用的 `(当前下标, 失败位)`。
 *
 * 为什么从 use-court-sms.ts 拆出来：状态机负责「跑流程」（提交、轮询、分配、重试），
 * 而这个函数是**纯换算**——同一个状态在不同阶段表（短信五步 / 客户转交四步）下落在
 * 第几步，取值只依赖入参，不碰任何 React 状态，也没有副作用。弹窗与测试直接调它，
 * 不该为此把整台状态机一并加载。
 *
 * 为什么放这里而不是 `stages.ts`：`stages.ts` 是纯 domain（不依赖 api 层），而这个
 * 函数要读 `CourtSmsDetail`。放进 stages 会让纯 domain 反向依赖 api 层。
 */
import type { CourtSmsDetail } from '../../../api'
import {
  failedStageFor,
  smsStageInfo,
  stageIndexFor,
  stageIndexFromRaw,
  stagesFor,
  type SmsStageSource,
} from './stages'

/** 详情 + 观测最大阶段 → 步进器要用的 (steps 当前下标, failedAt)
 *
 * ``source`` 决定阶段表：客户转交通道没有下载环节，用四步表并做下标重映射，
 * 否则 downloading/matching 会错位到错误的步骤上。
 * ``maxStage`` 记的是**后端原始下标**（流程里按 smsStageInfo 累计），
 * 展示时同样经 stageIndexFor 换算。
 */
export function stageForDisplay(
  detail: CourtSmsDetail | null,
  maxStage: number,
  source: SmsStageSource = 'sms',
): { current: number; failedAt: number | null } {
  const total = stagesFor(source).length
  if (!detail) return { current: 0, failedAt: null }
  const info = smsStageInfo(detail.status)
  if (info.terminal === 'completed') return { current: total, failedAt: null }
  const failed = failedStageFor(detail.status, source)
  if (failed !== null) return { current: failed, failedAt: failed }
  // 阶段只进不退：取「当前状态换算后的阶段」与「观测到的最大阶段」的较大值。
  // maxStage 记的是后端原始下标，同样经 stageIndexFromRaw 换算。
  const observed = stageIndexFor(detail.status, source)
  const remembered = stageIndexFromRaw(maxStage, source)
  return { current: Math.min(total, Math.max(observed, remembered)), failedAt: null }
}
