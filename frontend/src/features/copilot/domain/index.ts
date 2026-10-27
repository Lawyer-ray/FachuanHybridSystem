/**
 * Copilot 纯领域逻辑的统一出口（barrel）。
 *
 * 域内调用方一律 `from './domain'` / `from '../domain'`，不直接引子模块——
 * 这样按职责拆文件对调用点是零改动，后续再调整子模块划分也不会波及全域。
 *
 * 子模块分工：
 * - sse.ts        SSE 帧解析（与 streaming.ts 的帧消费配对）
 * - transcript.ts 转录映射：锚点/引用块的**出站构建 + 回放解析**（成对互逆）
 * - reference.ts  框选引用构建、默认出站提示语、AI 改写落盘识别
 * - approval.ts   审批倒计时窗口（与后端 approval.py 的契约常量）、离线卡映射、状态徽标
 * - attachment.ts 附件预检与大小展示
 * - tokens.ts     输出速度估算
 * - slash.ts      `/` 命令菜单
 * - location.ts   路由 → 页面描述、会话分组
 *
 * 全部为纯函数（无 React、无 IO），vitest 直接覆盖（node 环境，无 DOM）。
 */

export * from './approval'
export * from './attachment'
export * from './location'
export * from './reference'
export * from './slash'
export * from './sse'
export * from './tokens'
export * from './transcript'
