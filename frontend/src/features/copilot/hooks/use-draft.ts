/**
 * 输入框草稿：按会话持久化，切会话/刷新都不丢。
 *
 * 为什么不是简单的 `useState('')`：律师的问题往往是一整段事实（当事人、时间、
 * 诉求），写两分钟；切到别的会话查个条款再回来，草稿被清空等于白写一遍。
 *
 * 三个细节：
 * - **切会话先落盘旧 key**：切走那一刻才写，不会把 A 的草稿写进 B 的键；
 * - **写入去抖 300ms**：每次按键都写 localStorage 会阻塞输入（同步 IO）；
 * - **卸载时补写**：去抖窗口内关掉面板，最后一笔也要留住。
 *
 * 返回值与 `useState` 同形，调用方（Composer 与斜杠菜单/选区 intake）无需改签名。
 */

import type { Dispatch, SetStateAction } from 'react'
import { useCallback, useEffect, useRef, useState } from 'react'

import { clearDraft, readDraft, storeDraft } from '../persistence'

/** 去抖窗口（ms）：比人手停顿短、比连续输入长 */
const WRITE_DEBOUNCE_MS = 300

export function useDraft(sessionId: string | null): [string, Dispatch<SetStateAction<string>>] {
  const [text, setText] = useState(() => readDraft(sessionId))
  const latest = useRef(text)
  const sessionRef = useRef(sessionId)
  const timerRef = useRef<number | null>(null)

  const flush = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current)
      timerRef.current = null
    }
    storeDraft(sessionRef.current, latest.current)
  }, [])

  // 切会话：先把旧会话的草稿落盘，再载入新会话的草稿
  useEffect(() => {
    if (sessionRef.current === sessionId) return
    flush()
    sessionRef.current = sessionId
    const next = readDraft(sessionId)
    latest.current = next
    setText(next)
  }, [sessionId, flush])

  // 卸载：去抖窗口内的最后一笔补写（否则「写完立刻关面板」会丢）
  useEffect(() => {
    return () => flush()
  }, [flush])

  // 与 useState 同形（支持函数式更新）：Composer 的斜杠菜单/选区 intake 都按
  // React setState 的签名在调用，换实现不能让调用方改签名
  const update = useCallback<Dispatch<SetStateAction<string>>>((next) => {
    const value = typeof next === 'function' ? next(latest.current) : next
    latest.current = value
    setText(value)
    if (timerRef.current !== null) window.clearTimeout(timerRef.current)
    timerRef.current = window.setTimeout(() => {
      timerRef.current = null
      storeDraft(sessionRef.current, latest.current)
    }, WRITE_DEBOUNCE_MS)
  }, [])

  return [text, update]
}

/** 发送成功后清空草稿（正文已进转录，留着会让下一条重复发送） */
export function dropDraft(sessionId: string | null): void {
  clearDraft(sessionId)
}
