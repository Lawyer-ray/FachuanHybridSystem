/**
 * 会话纪元（module-level 单例，从 store.ts 抽出的编排守卫）。
 *
 * 任何切换/新建会话都 +1。
 *
 * enterContext 的「自动恢复最近会话」要 await 一次列表拉取，期间律师可能
 * 已动了手（点新对话/切会话/发消息建会话）。只比 sessionId 挡不住
 * 「null → 点新对话 → 还是 null」这条隐形路径，所以按**动作次数**计：
 * 拉取回来发现纪元变了，就是有人动过，迟到的自动恢复让位。
 *
 * 归属：session / turn / index(reset) 三处共用同一个计数器，故单独成文件，
 * 避免「哪个 slice 拥有它」的歧义（也避开 slice 之间互相 import 成环）。
 */

let sessionEpoch = 0

/** 读当前纪元（拉取前快照，回来比对） */
export function currentSessionEpoch(): number {
  return sessionEpoch
}

/** 会话动作发生：纪元 +1 */
export function bumpSessionEpoch(): void {
  sessionEpoch += 1
}
