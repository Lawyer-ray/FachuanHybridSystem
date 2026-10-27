/**
 * 语音听写输入（Web Speech API，zh-CN）：点麦克风开始，说出的内容实时进输入框。
 *
 * 为什么用浏览器原生而不是后端 ASR：律师的听写是「草稿级」输入（说完还会改），
 * 浏览器内置引擎零延迟零成本；Chrome/Edge 对 zh-CN 支持成熟且自动加标点。
 * Firefox 不支持 → supported=false，按钮直接不渲染（而不是渲染一个灰的）。
 *
 * 文本合并模型（关键设计，避免两条经典坑）：
 * - **final 增量采纳**：从 processed 指针起逐条判 isFinal，final 才并入
 *   committed 并推进指针。final 结果只报一次，指针保证不重复计入。
 * - **interim 每次重建**：未 final 的尾巴从 processed 起重拼，refined 版本
 *   （同一句越说越准）天然覆盖旧的，不会叠罗汉。
 * - **rebase 兜底**：听写中用户手动改字（删一个错词、补一句），把「当前完整
 *   草稿」设为新基线、旧结果指针直接跳到末尾——后续听写在编辑后的文本后
 *   追加，不会把用户刚改掉的字念回来（emit 全量覆盖型实现的典型事故）。
 * - onend 时未转正的 interim 直接采纳：结束后不会再有 final 事件，丢弃就会
 *   丢掉用户说的最后半句。
 *
 * 不做静默自动续听：Chrome 连续模式静默几秒会自己 onend，自动 restart 会
 * 在权限边缘场景里循环弹权限框；用户想继续就再点一次，行为可预期。
 */

import { useCallback, useEffect, useRef, useState } from 'react'

/** Web Speech 最小面（lib.dom 未收录 vendor 前缀构造器，按需声明） */
interface SpeechRecognitionLike {
  lang: string
  continuous: boolean
  interimResults: boolean
  start(): void
  stop(): void
  abort(): void
  onresult: ((e: SpeechRecognitionEventLike) => void) | null
  onend: (() => void) | null
  onerror: ((e: { error: string }) => void) | null
}

interface SpeechRecognitionEventLike {
  resultIndex: number
  results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }>
}

type SpeechRecognitionCtor = new () => SpeechRecognitionLike

function getRecognitionCtor(): SpeechRecognitionCtor | null {
  if (typeof window === 'undefined') return null
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor
    webkitSpeechRecognition?: SpeechRecognitionCtor
  }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

export function useSpeechInput({ onText }: { onText: (text: string) => void }) {
  const [supported] = useState(() => Boolean(getRecognitionCtor()))
  const [listening, setListening] = useState(false)
  /** 面向用户的失败原因（权限拒绝等；no-speech 属正常静默，不报） */
  const [error, setError] = useState<string | null>(null)

  const recRef = useRef<SpeechRecognitionLike | null>(null)
  /** 本次听写的基线：开始（或 rebase）时输入框里的完整草稿 */
  const baseRef = useRef('')
  /** 已转正（isFinal）的听写文本 */
  const committedRef = useRef('')
  /** 未转正的尾巴（onresult 每次重建；onend 采纳后清空） */
  const interimRef = useRef('')
  /** results 里已处理到的下标（final 过指针；rebase 时直接跳到末尾） */
  const processedRef = useRef(0)
  /** results 当前长度（rebase 时作为 processed 的新起点） */
  const lastLenRef = useRef(0)
  /** 静默停止：停止后不做最后一次提交（发送场景用——草稿已含全部文本，
   *  输入框随即清空，再 emit 会把发掉的内容「复活」回输入框） */
  const quietStopRef = useRef(false)

  // latest-ref：onText 每次渲染都可能是新闭包（含 setText + autoGrow），
  // 识别回调必须永远拿到最新的
  const onTextRef = useRef(onText)
  useEffect(() => {
    onTextRef.current = onText
  }, [onText])

  const emit = useCallback((suffix: string) => {
    onTextRef.current(baseRef.current + suffix)
  }, [])

  /** 停止本次听写（onend 里完成收尾；quiet=true 时不做最后一次提交） */
  const stop = useCallback((quiet = false) => {
    quietStopRef.current = quiet
    recRef.current?.stop()
  }, [])

  /**
   * 开始听写。base 传「点击那一刻的输入框草稿」，听写内容追加在其后。
   * （按钮 onClick 每次渲染都是新闭包，拿到的是最新草稿，不会 stale。）
   */
  const start = useCallback(
    (base: string) => {
      const Ctor = getRecognitionCtor()
      if (!Ctor || recRef.current) return
      setError(null)
      quietStopRef.current = false
      baseRef.current = base
      committedRef.current = ''
      interimRef.current = ''
      processedRef.current = 0
      lastLenRef.current = 0
      const rec = new Ctor()
      rec.lang = 'zh-CN'
      rec.continuous = true
      rec.interimResults = true
      rec.onresult = (e) => {
        const results = e.results
        for (let i = processedRef.current; i < results.length; i++) {
          const r = results[i]
          if (!r) continue
          if (r.isFinal) {
            committedRef.current += r[0]?.transcript ?? ''
            processedRef.current = i + 1
          }
        }
        let interim = ''
        for (let i = processedRef.current; i < results.length; i++) {
          interim += results[i]?.[0]?.transcript ?? ''
        }
        interimRef.current = interim
        lastLenRef.current = results.length
        emit(committedRef.current + interim)
      }
      rec.onend = () => {
        // 未转正的尾巴直接采纳（结束后不会再有 final 事件，丢掉就是丢字）
        committedRef.current += interimRef.current
        interimRef.current = ''
        recRef.current = null
        setListening(false)
        if (!quietStopRef.current) emit(committedRef.current)
        quietStopRef.current = false
      }
      rec.onerror = (e) => {
        if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
          setError('麦克风权限被拒绝：请在浏览器地址栏对本站允许麦克风后重试')
        } else if (e.error === 'audio-capture') {
          setError('未检测到麦克风设备')
        } else if (e.error === 'network') {
          setError('听写服务网络异常，请稍后重试')
        }
        // no-speech / aborted 属正常结束路径，静默即可
      }
      recRef.current = rec
      try {
        rec.start()
        setListening(true)
      } catch {
        // start 抛错（如已 start 的实例）→ 回滚状态，别卡在「假听写中」
        recRef.current = null
        setListening(false)
      }
    },
    [emit],
  )

  /**
   * 听写中用户手动改了输入框：以编辑后的全文为新基线，旧识别结果全部作废。
   * 后续听写内容追加在编辑后的文本之后，不会覆盖用户的修改。
   */
  const rebase = useCallback((currentText: string) => {
    baseRef.current = currentText
    committedRef.current = ''
    interimRef.current = ''
    processedRef.current = lastLenRef.current
  }, [])

  // 卸载时中止识别，别让麦克风亮着
  useEffect(() => () => recRef.current?.abort(), [])

  return { supported, listening, error, start, stop, rebase }
}
