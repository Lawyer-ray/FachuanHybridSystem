import type { CopilotState } from '../types'

/** 一次 setState 的「部分更新」形状：含哪些键就给哪些键 */
export type StatePatch<S> = { [K in keyof S]?: S[K] }

/**
 * Zustand setState 的等价签名：比 store 的精确签名**更宽松**（不必 replace 分支），
 * 因此既能接收真实 setState（它是子类型），也能让 slice 里 `(s) => {...}` 的
 * 回调参数推断为 CopilotState。
 */
export type SetState<S> = (patch: StatePatch<S> | ((state: S) => StatePatch<S>)) => void

/** getState：无参函数（与 store 的 getState 同形，闭包里拿到的永远是最新 state） */
export type GetState<S> = () => S

export type Slice<T> = (set: SetState<CopilotState>, get: GetState<CopilotState>) => T
