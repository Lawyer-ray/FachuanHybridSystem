/**
 * 输入区：Enter 发送、Shift+Enter 换行；流式期间变为「停止」+ 可插话（steer）。
 *
 * 三种提交路径：
 * - 常规：Enter / 发送钮 → store.send（SSE 流式）
 * - 流式中：输入框保持可用，Enter → store.steer（运行中插话，不改写当前输出）；
 *   已插话的文本以「已插话 N 条」提示，可整体撤回（DELETE /queue）
 * - 后台模式（时钟开关）：提交后立即返回，任务在后台跑完写入会话通知
 *
 * `/` 打头时弹命令菜单（技能补全 `/skill:名字 ` + 内置命令），交互态在
 * use-slash-menu；底栏显示会话上下文水位（done 事件 / stats 接口回填）。
 *
 * 主题：中性灰阶，无 emoji；发送成功静默，失败由 MessageList 的错误行兜底。
 */

import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowUp, Clock, Mic, Paperclip, Square, Undo2 } from 'lucide-react'
import { toast } from 'sonner'

import { fetchAgentSkills } from '../api'
import { formatFileSize } from '../domain'
import { useSlashMenu } from '../hooks/use-slash-menu'
import { useSpeechInput } from '../hooks/use-speech-input'
import { COPILOT_PREFILL_EVENT } from '../launch'
import { useCopilot } from '../store'
import { QuoteChip } from './RefQuote'
import { SlashMenu } from './SlashMenu'
import { TurnStatsView } from './TurnStatsView'

export function Composer() {
  const [text, setText] = useState('')
  const [bgMode, setBgMode] = useState(false)
  const streaming = useCopilot((s) => s.streaming)
  const queuedSteers = useCopilot((s) => s.queuedSteers)
  const pendingFiles = useCopilot((s) => s.pendingFiles)
  const pendingRefs = useCopilot((s) => s.pendingRefs)
  const uploading = useCopilot((s) => s.uploadingAttachments)
  const contextUsage = useCopilot((s) => s.contextUsage)
  const compacting = useCopilot((s) => s.compacting)
  const compactContext = useCopilot((s) => s.compactContext)
  const sessionId = useCopilot((s) => s.sessionId)
  const messageCount = useCopilot((s) => s.messages.length)
  const addAttachmentFiles = useCopilot((s) => s.addAttachmentFiles)
  const removeAttachmentFile = useCopilot((s) => s.removeAttachmentFile)
  const removeFolderRef = useCopilot((s) => s.removeFolderRef)
  const send = useCopilot((s) => s.send)
  const stop = useCopilot((s) => s.stop)
  const steer = useCopilot((s) => s.steer)
  const revokeQueuedSteers = useCopilot((s) => s.revokeQueuedSteers)
  const submitTask = useCopilot((s) => s.submitTask)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  /**
   * 语音听写（Chrome/Edge 原生，zh-CN）：说出的内容实时追加进输入框草稿。
   * onText 每次带上 autoGrow——语音进来也要长个儿，不能等用户敲键才撑高。
   */
  const speech = useSpeechInput({
    onText: (t) => {
      setText(t)
      requestAnimationFrame(autoGrow)
    },
  })

  // 权限拒绝这类用户必须知道原因的失败，弹一次 toast（悬停 title 太隐蔽）
  useEffect(() => {
    if (speech.error) toast.error('语音输入失败', { description: speech.error })
  }, [speech.error])

  /**
   * 接收「选区预填」：编辑器里框选一段后，把带引用的指令模板放进输入框。
   *
   * 用事件而不是 store：输入框文本是本地草稿 state（用户正在打字时不该被全局状态
   * 覆盖），只需要一次性的「塞一段文字」。
   */
  useEffect(() => {
    function onPrefill(e: Event) {
      const d = (e as CustomEvent<{ text?: string }>).detail
      const t = d?.text?.trim()
      if (!t) return
      // 追加而不是覆盖：律师可能已经写了半句，别把他打的字冲掉
      setText((prev) => (prev.trim() ? `${prev.trim()}\n${t}` : t))
      requestAnimationFrame(() => {
        const el = textareaRef.current
        if (!el) return
        el.focus()
        el.setSelectionRange(el.value.length, el.value.length)
      })
    }
    window.addEventListener(COPILOT_PREFILL_EVENT, onPrefill)
    return () => window.removeEventListener(COPILOT_PREFILL_EVENT, onPrefill)
  }, [])

  // 技能清单（`/` 菜单数据源）：菜单打开才被消费，失败静默降级为「只有内置命令」
  const skillsQuery = useQuery({
    queryKey: ['agent-skills'],
    queryFn: () => fetchAgentSkills(),
    staleTime: 5 * 60_000,
    retry: false,
  })
  const skills = skillsQuery.data?.skills ?? []

  const slash = useSlashMenu({
    text,
    skills,
    hasSession: Boolean(sessionId && messageCount > 0),
    onSkill: (name) => {
      setText(`/skill:${name} `)
      textareaRef.current?.focus()
    },
    onCommand: (id) => {
      if (id === 'compact') {
        setText('')
        void compactContext()
      }
    },
  })

  const submit = () => {
    // 听写中直接发送：静默停止（草稿里已含说到的最后一个字，interim 每次
    // onresult 都实时 emit 进了输入框），停止后再 emit 会把发掉的内容
    // 「复活」回已清空的输入框
    if (speech.listening) speech.stop(true)
    const value = text.trim()
    if (!value && pendingFiles.length === 0 && pendingRefs.length === 0) return
    if (uploading) return
    if (streaming) {
      // 运行中插话：不改写当前输出，在工具调用后、下次模型调用前生效
      void steer(value)
      setText('')
      return
    }
    if (bgMode) {
      setBgMode(false)
      setText('')
      void submitTask(value)
      return
    }
    // 先清空正文腾出输入位；早失败（建会话/附件上传失败）时回填，别让
    // 用户重打一遍。期间用户又输入了新内容则不打扰（只补空）。
    setText('')
    const outgoing =
      value ||
      (pendingRefs.length > 0
        ? pendingRefs.every((r) => r.isFolder)
          ? '请浏览我引用的目录并梳理其中的材料。'
          : '请分析我引用的文件。'
        : '请分析我上传的附件。')
    void send(outgoing, (sent) => {
      if (!sent) setText((prev) => (prev.trim() ? prev : outgoing))
    })
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      // 菜单开着时 Enter 是「选中菜单项」不是「发送」；其余菜单键同理短路
      if (slash.onKeyDown(e)) {
        e.preventDefault()
        return
      }
      e.preventDefault()
      submit()
      return
    }
    if (slash.onKeyDown(e)) {
      e.preventDefault()
    }
  }

  /** 跟随内容自适应高度（1–5 行） */
  const autoGrow = () => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`
  }

  const placeholder = speech.listening
    ? '正在听写…说完点麦克风结束，可手动修改后发送'
    : streaming
      ? '插话补充指令，Enter 送达当前对话…'
      : bgMode
        ? '后台运行：提交后可关闭页面，跑完会在会话里通知你…'
        : '问点什么…'

  return (
    <div className="flex-none border-t border-border p-2.5">
      {/* 内容限宽居中：与消息栏同宽对齐（两边都走 max-w-6xl，宽度一致不错位） */}
      <div className="mx-auto w-full max-w-6xl">
      {(pendingRefs.length > 0 || pendingFiles.length > 0) && (
        <div className="mb-1.5 flex flex-wrap gap-1.5">
          {pendingRefs.map((ref, i) => (
            <QuoteChip
              key={`${ref.kind}-${ref.ownerId}-${ref.subpath}`}
              source={ref}
              onRemove={() => removeFolderRef(i)}
              removeLabel={`移除引用 ${ref.name}`}
            />
          ))}
          {pendingFiles.map((file, i) => (
            <QuoteChip
              key={`${file.name}-${i}`}
              source={{ kind: 'contract', subpath: file.name, name: file.name }}
              meta={formatFileSize(file.size)}
              icon="attachment"
              onRemove={() => removeAttachmentFile(i)}
              removeLabel={`移除附件 ${file.name}`}
            />
          ))}
        </div>
      )}
      {streaming && queuedSteers.length > 0 && (
        <div className="mb-1.5 flex items-center gap-1.5 px-1 text-[11.5px] text-muted-foreground">
          <span className="min-w-0 flex-1 truncate">已插话 {queuedSteers.length} 条，将在本轮生效</span>
          <button
            type="button"
            className="flex h-6 flex-none items-center gap-1 rounded-[6px] px-1.5 transition-colors hover:bg-secondary hover:text-foreground"
            onClick={() => void revokeQueuedSteers()}
            aria-label="撤回插话"
            title="撤回已排队、尚未生效的插话"
          >
            <Undo2 className="h-3 w-3" />
            撤回
          </button>
        </div>
      )}
      <div className="relative flex items-end gap-2 rounded-[14px] border border-border bg-background px-2.5 py-1.5 shadow-sm transition-[border-color,box-shadow] duration-150 focus-within:border-foreground/30 focus-within:ring-4 focus-within:ring-foreground/10">
        {slash.open && (
          <SlashMenu
            items={slash.items}
            selectedIndex={slash.index}
            onHover={slash.setIndex}
            onSelect={(item) => slash.apply(item)}
          />
        )}
        <button
          type="button"
          className={`flex h-7 w-7 flex-none items-center justify-center rounded-[8px] transition-colors disabled:opacity-40 ${
            bgMode ? 'bg-secondary text-foreground' : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
          }`}
          onClick={() => setBgMode((v) => !v)}
          disabled={streaming || pendingFiles.length > 0 || pendingRefs.length > 0}
          aria-label={bgMode ? '关闭后台运行模式' : '切换为后台运行'}
          aria-pressed={bgMode}
          title={
            pendingFiles.length > 0
              ? '带附件/引用的消息只能即时对话（后台任务暂不支持）'
              : bgMode
                ? '后台运行已开启：提交的任务在后台执行'
                : '切换为后台运行：适合要跑几分钟的长任务'
          }
        >
          <Clock className="h-4 w-4" />
        </button>
        <button
          type="button"
          className="flex h-7 w-7 flex-none items-center justify-center rounded-[8px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-40"
          onClick={() => fileInputRef.current?.click()}
          disabled={streaming || uploading}
          aria-label="添加附件"
          title="添加附件（PDF / Word / 图片 / 文本，≤20MB；也可直接拖入面板）"
        >
          <Paperclip className="h-4 w-4" />
        </button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.docx,.doc,.png,.jpg,.jpeg,.tif,.tiff,.txt"
          className="hidden"
          onChange={(e) => {
            if (e.target.files) addAttachmentFiles(e.target.files)
            e.target.value = ''
          }}
        />
        {speech.supported && (
          <button
            type="button"
            className={`flex h-7 w-7 flex-none items-center justify-center rounded-[8px] transition-colors ${
              speech.listening
                ? 'bg-destructive/10 text-destructive'
                : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
            }`}
            onClick={() => (speech.listening ? speech.stop() : speech.start(text))}
            aria-label={speech.listening ? '停止语音输入' : '语音输入'}
            aria-pressed={speech.listening}
            title={
              speech.listening
                ? '正在听写，点击结束（内容已实时进入输入框，可随口修改后发送）'
                : '语音输入：中文听写，内容实时进入输入框'
            }
          >
            <Mic className={`h-4 w-4 ${speech.listening ? 'animate-pulse' : ''}`} />
          </button>
        )}
        <textarea
          ref={textareaRef}
          value={text}
          rows={1}
          placeholder={placeholder}
          className="max-h-30 min-h-6 flex-1 resize-none bg-transparent text-[13px] leading-relaxed text-foreground outline-none placeholder:text-muted-foreground"
          onChange={(e) => {
            // 听写中手动改字：以编辑后的全文为新基线，后续听写在其后追加
            if (speech.listening) speech.rebase(e.target.value)
            setText(e.target.value)
            autoGrow()
          }}
          onKeyDown={handleKeyDown}
        />
        {streaming ? (
          <button
            type="button"
            className="flex h-7 w-7 flex-none items-center justify-center rounded-full bg-foreground text-background transition-opacity hover:opacity-85"
            onClick={stop}
            aria-label="停止生成"
            title="停止生成（已生成部分会保留）"
          >
            <Square className="h-3 w-3 fill-current" />
          </button>
        ) : (
          <button
            type="button"
            className="copilot-send flex h-7 w-7 flex-none items-center justify-center rounded-full disabled:opacity-30 disabled:shadow-none"
            onClick={submit}
            disabled={uploading || (!text.trim() && pendingFiles.length === 0 && pendingRefs.length === 0)}
            aria-label={bgMode ? '提交后台任务' : '发送'}
            title={uploading ? '附件上传中…' : undefined}
          >
            <ArrowUp className="h-3.5 w-3.5" strokeWidth={2.5} />
          </button>
        )}
      </div>
      <p className="mt-1.5 flex items-center gap-2 px-1 text-[11px] text-muted-foreground">
        <span className="min-w-0 flex-1 truncate">
          {compacting
            ? '正在压缩上下文…'
            : bgMode
              ? '后台任务跑完会写入会话通知；高危操作会等你回来审批。'
              : 'AI 回答仅供参考，法律判断需由律师复核。'}
        </span>
        {contextUsage.used !== null && contextUsage.total && contextUsage.total > 0 && !compacting && (
          <span
            className={`flex-none tabular-nums ${contextUsage.used / contextUsage.total >= 0.8 ? 'text-amber-600 dark:text-amber-400' : ''}`}
            title={`上下文窗口占用：${contextUsage.used} / ${contextUsage.total} tokens；用 / 压缩命令可手动释放`}
          >
            上下文 {Math.round((contextUsage.used / contextUsage.total) * 100)}%
          </span>
        )}
        <TurnStatsView />
      </p>
      </div>
    </div>
  )
}
