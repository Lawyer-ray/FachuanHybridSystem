/**
 * Copilot 全局状态：转录、审批卡与流式收发。
 *
 * 流的生命周期归 store（模块级 Zustand）而非组件——收起面板不中断流；
 * 会话列表这类服务端状态走 react-query（SessionSidebar），不进本 store。
 *
 * 本文件只做**装配**：state 形状与语义见 types.ts 的 CopilotState，动作按
 * 关注点分片在同目录：
 * - session.ts       会话生命周期（进入业务范围/切换/历史回放与分页）
 * - turn.ts          一轮对话（发送、流生命周期、插话、后台任务）
 * - approval.ts      审批卡（加载合并/决策/失效清理）
 * - attachment.ts    待发草稿（附件/文件夹引用/框选引用 chips，无网络）
 * - context-usage.ts 上下文水位与消息反馈
 * - session-epoch.ts 会话纪元守卫（跨 slice 共享的模块级计数器）
 * 领域细节在域根目录：streaming.ts（帧消费）、turn-handlers.ts（轮处理器）、
 * outgoing.ts（附件出站）、transitions.ts（视图过渡）、persistence.ts（会话
 * 持久化）、launch.ts（跨域启动入口）。
 */

import { create } from 'zustand'

import { resetUploadReceipts } from '../outgoing'
import { readStoredSession, storeSession } from '../persistence'
import type { CopilotState } from '../types'
import { createApprovalSlice } from './approval'
import { createAttachmentSlice } from './attachment'
import { createContextUsageSlice } from './context-usage'
import { createSessionSlice } from './session'
import { bumpSessionEpoch } from './session-epoch'
import { createTurnSlice, EMPTY_STATS } from './turn'

export const useCopilot = create<CopilotState>((set, get) => ({
  // ── state 初值 ──────────────────────────────────────────────────────
  sessionId: readStoredSession(),
  messages: [],
  approvals: [],
  streaming: false,
  loadingHistory: false,
  lastError: null,
  turnStats: EMPTY_STATS,
  contextUsage: { used: null, total: null },
  compacting: false,
  queuePosition: null,
  queuedSteers: [],
  steering: false,
  context: null,
  pendingFiles: [],
  pendingRefs: [],
  pendingQuote: null,
  pageHint: null,
  lastPageHintSent: null,
  uploadingAttachments: false,
  sending: false,
  draggingFiles: false,
  noMoreHistory: false,
  loadingOlder: false,

  // ── 页面感知（AppShell 路由兜底写粗粒度值，详情页挂载后写精确值覆盖） ──
  setPageHint: (hint) => {
    if (get().pageHint === hint) return
    set({ pageHint: hint })
  },

  // ── 各关注点分片 ────────────────────────────────────────────────────
  ...createSessionSlice(set, get),
  ...createTurnSlice(set, get),
  ...createApprovalSlice(set, get),
  ...createAttachmentSlice(set, get),
  ...createContextUsageSlice(set, get),

  // ── 全局清理（登出） ────────────────────────────────────────────────
  reset: () => {
    get().stop()
    bumpSessionEpoch()
    set({
      sessionId: null,
      messages: [],
      approvals: [],
      streaming: false,
      loadingHistory: false,
      lastError: null,
      turnStats: { ...EMPTY_STATS },
      contextUsage: { used: null, total: null },
      compacting: false,
      queuePosition: null,
      queuedSteers: [],
      steering: false,
      context: null,
      pendingFiles: [],
      pendingRefs: [],
      pendingQuote: null,
      uploadingAttachments: false,
      sending: false,
      draggingFiles: false,
    })
    resetUploadReceipts()
    storeSession(null)
  },
}))
