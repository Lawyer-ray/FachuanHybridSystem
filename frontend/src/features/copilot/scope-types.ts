/**
 * Copilot 业务范围类型：会话归属哪个案件 / 合同。
 *
 * 从 `types.ts` 拆出（后者贴近 350 行软红线）。这里的两个类型是「进项目页
 * 打开助手」的入参形状：`CopilotScope` 是纯归属，`CopilotContext` 多带一个
 * 用于标题展示的业务名。
 */

/** 会话归属的业务范围（案件内 / 合同内）；不带则为普通对话 */
export interface CopilotScope {
  origin: 'case' | 'contract'
  refId: number
}

/** 业务内会话上下文（案件/合同页打开时携带）：范围 + 展示名 */
export interface CopilotContext extends CopilotScope {
  title: string
}
