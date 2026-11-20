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
 * use-slash-menu；`@` 弹引用菜单（案件/合同/文书/文件夹），交互态在
 * use-mention-menu；底栏显示会话上下文水位（done 事件 / stats 接口回填）。
 *
 * **两个菜单共用一条按键管线**：`use-slash-menu` 与本文件里的 `menuKeyDown` 被
 * 合成一个 `{ onKeyDown }` 塞进 `useComposerSubmit`，于是「IME 守卫 → Shift+Enter
 * 放行 → 菜单是否吃掉这个键 → 发送」的顺序只有一处（use-composer-submit），
 * 两个菜单不可能出现「一个吃 Enter、另一个把 Enter 落到发送」的竞态。
 * `use-mention-menu` 与 `use-slash-menu` 也共用同一个 token 检测器
 * （`detectMentionToken`）与同一个草稿改写原语（`applyMention`）。
 *
 * 主题：中性灰阶，无 emoji；发送成功静默，失败由 MessageList 的错误行兜底。
 *
 * 拆分记录（本文件已收敛到 ≤200 行）：ComposerFooter / ComposerQuote / PendingChips /
 * ComposerToolbar（左侧三个工具按钮 + 隐藏 file input）、use-composer-submit
 * （submit + handleKeyDown + autoGrow）、use-composer-intake（框选引用 / 选区预填
 * 两条事件通道）。submit 牵动 speech / slash / send 三个 hook 的协调顺序，
 * 改它之前先读 use-composer-submit.ts 的文件头。
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowUp, Square, Undo2 } from 'lucide-react'
import { toast } from 'sonner'

import { fetchAgentSkills } from '../api'
import { applyMention, detectMentionToken, type MentionInsert, type MentionToken } from '../domain'
import { useComposerIntake } from '../hooks/use-composer-intake'
import { useDraft } from '../hooks/use-draft'
import { useComposerSubmit } from '../hooks/use-composer-submit'
import { useMentionMenu } from '../hooks/use-mention-menu'
import { useSlashMenu } from '../hooks/use-slash-menu'
import { useSpeechInput } from '../hooks/use-speech-input'
import { defaultAgentKind } from '../store/backends'
import { useCopilot } from '../store'
import type { CopilotScope } from '../types'
import { ComposerFooter } from './ComposerFooter'
import { ComposerQuote } from './ComposerQuote'
import { ComposerToolbar } from './ComposerToolbar'
import { MentionMenu } from './MentionMenu'
import { PendingChips } from './PendingChips'
import { SlashMenu } from './SlashMenu'

/** 引用候选 listbox 的 id：textarea 的 aria-controls 指向它 */
const MENTION_LISTBOX_ID = 'composer-mention-listbox'

/**
 * textarea 自适应高度（1–5 行）。
 *
 * 与 use-composer-submit 的 autoGrow 同口径：`@` 选中后要立即长个儿，而那条路径的
 * autoGrow 在 useComposerSubmit 返回后才有（它依赖 mention.onKeyDown，与这里是一个
 * 环）。两处的高度上限必须一致，改一处必须同步另一处。
 */
function growTextarea(el: HTMLTextAreaElement): void {
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 120)}px`
}

/** 流式中的「已插话 N 条」提示条（撤回按钮在前一排，两者共用一行） */
const STEER_BAR_CLASS = 'mb-1.5 flex items-center gap-1.5 px-1 text-[11.5px] text-muted-foreground'
const REVOKE_BUTTON_CLASS = 'flex h-6 flex-none items-center gap-1 rounded-[6px] px-1.5 transition-colors hover:bg-secondary hover:text-foreground'
const STOP_BUTTON_CLASS = 'flex h-7 w-7 flex-none items-center justify-center rounded-full bg-foreground text-background transition-opacity hover:opacity-85'
const SEND_BUTTON_CLASS = 'copilot-send flex h-7 w-7 flex-none items-center justify-center rounded-full disabled:opacity-30 disabled:shadow-none'

/**
 * @param steerEnabled 当前后端是否支持运行中插话（`BackendCapabilities.steer`）。
 *   由 CopilotPanel 按会话/待建会话的后端能力传入——`false` 时流式中不再提示
 *   「插话补充指令」，Enter 改为明确告知等本轮结束（见 use-composer-submit）。
 *   为什么不由本组件自己从 store 算：已建会话的后端只存在于会话列表缓存里，
 *   那是 CopilotPanel 的数据源。
 */
export function Composer({ steerEnabled = true }: { steerEnabled?: boolean }) {
  // 草稿按会话持久化：切会话/刷新都不丢（律师常写一整段事实，重打一遍代价很高）
  const [text, setText] = useDraft(useCopilot((s) => s.sessionId))
  const [bgMode, setBgMode] = useState(false)
  const streaming = useCopilot((s) => s.streaming)
  const queuedSteers = useCopilot((s) => s.queuedSteers)
  const pendingFiles = useCopilot((s) => s.pendingFiles)
  const pendingRefs = useCopilot((s) => s.pendingRefs)
  const pendingQuote = useCopilot((s) => s.pendingQuote)
  const setPendingQuote = useCopilot((s) => s.setPendingQuote)
  const uploading = useCopilot((s) => s.uploadingAttachments)
  // 发送全过程在途（建会话/上传附件期间）：与 uploading 一起置忙，堵住
  // 「上传完成 → 消息入列」这段两者都为 false 的窗口里的二次提交
  const sending = useCopilot((s) => s.sending)
  const compactContext = useCopilot((s) => s.compactContext)
  const sessionId = useCopilot((s) => s.sessionId)
  const messageCount = useCopilot((s) => s.messages.length)
  const addAttachmentFiles = useCopilot((s) => s.addAttachmentFiles)
  // 本轮跑哪几个 AI（多答）：清单 + 已选 + 默认项，「选满 4 个」由菜单自己置灰
  const backends = useCopilot((s) => s.backends)
  const answerAgents = useCopilot((s) => s.answerAgents)
  // 各栏的模型（与勾选分存：勾选决定跑不跑，模型决定跑哪个）
  const answerModels = useCopilot((s) => s.answerModels)
  const toggleAnswerAgent = useCopilot((s) => s.toggleAnswerAgent)
  const setAnswerModel = useCopilot((s) => s.setAnswerModel)
  const defaultKind = useCopilot((s) => defaultAgentKind(s.backends))
  const send = useCopilot((s) => s.send)
  const stop = useCopilot((s) => s.stop)
  const steer = useCopilot((s) => s.steer)
  const revokeQueuedSteers = useCopilot((s) => s.revokeQueuedSteers)
  const submitTask = useCopilot((s) => s.submitTask)
  // 业务范围与 `@` 引用（文书/文件夹取当前案件/合同的绑定文件夹）
  const context = useCopilot((s) => s.context)
  const addMention = useCopilot((s) => s.addMention)
  const clearMentions = useCopilot((s) => s.clearMentions)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  /** 光标位置：`@`/`/` 的 token 识别要的是「光标前」而不是「草稿末尾」 */
  const [caret, setCaret] = useState(0)

  /** 语音听写（Chrome/Edge 原生，zh-CN）：内容实时进草稿；onText 带 autoGrow
   *  ——语音进来也要长个儿，不能等用户敲键才撑高 */
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

  // 技能清单（`/` 菜单数据源）：菜单打开才被消费，失败静默降级为「只有内置命令」
  const skillsQuery = useQuery({ queryKey: ['agent-skills'], queryFn: () => fetchAgentSkills(), staleTime: 5 * 60_000, retry: false })
  const skills = skillsQuery.data?.skills ?? []

  const slash = useSlashMenu({
    text,
    skills,
    hasSession: Boolean(sessionId && messageCount > 0),
    onSkill: (name) => {
      // 与 `@` 用**同一个改写原语**（applyMention + detectMentionToken）：
      // 命令的 token 按「整行」算（命令语义是整行 = 命令 + 参数，不看光标在哪），
      // 所以这里显式传 text.length 而不是跟随 caret
      const token = detectMentionToken(text, text.length)
      const next = token?.trigger === '/' ? applyMention(text, token, { insertText: `/skill:${name} ` }) : null
      const value = next?.text ?? `/skill:${name} `
      const caretAt = next?.caret ?? value.length
      setText(value)
      // 光标落到补全后的位置（原先只 focus，光标留在开头，再打参数会插到 /skill: 前面）
      requestAnimationFrame(() => {
        const el = textareaRef.current
        if (!el) return
        el.focus()
        el.setSelectionRange(caretAt, caretAt)
        setCaret(caretAt)
      })
    },
    onCommand: (id) => {
      if (id !== 'compact') return
      setText('')
      void compactContext()
    },
  })

  /** 业务范围（对象形状要稳定：源列表按它 memo，变了会重拉候选） */
  const scope = useMemo<CopilotScope | undefined>(
    () => (context ? { origin: context.origin, refId: context.refId } : undefined),
    [context],
  )

  /**
   * `@` 选中：改写草稿 + 落进 pendingMentions。
   *
   * 草稿里只放人能读的 `@名字 `（`insertText`），协议块留在 `clipboardText`，
   * 由 outgoing 在发送时缀到正文后——否则一行正文被十几个不可读字符打断。
   */
  const onPickMention = useCallback(
    (insert: MentionInsert, token: MentionToken) => {
      const next = applyMention(text, token, insert)
      setText(next.text)
      addMention(insert)
      // 受控值下一帧才提交，光标必须那时再复位（现在设会被 React 覆写）
      requestAnimationFrame(() => {
        const el = textareaRef.current
        if (!el) return
        el.focus()
        el.setSelectionRange(next.caret, next.caret)
        setCaret(next.caret)
        growTextarea(el)
      })
    },
    [addMention, setText, text],
  )

  const mention = useMentionMenu({ text, caret, scope, onPick: onPickMention })

  /**
   * 菜单按键的**唯一**裁决点：先 `@` 引用菜单，再 `/` 命令菜单。
   * 返回 true = 已被菜单消费，`use-composer-submit` 会 preventDefault 并短路发送。
   */
  const menuKeyDown = (event: React.KeyboardEvent): boolean =>
    mention.onKeyDown(event) === 'consumed' || slash.onKeyDown(event)

  /**
   * 发送 + 成功清引用：`onQueued(true)` 表示消息已入列（store/turn.ts 那里也在此
   * 清 pendingFiles/pendingRefs）。失败时保留 chips，重试不丢引用。
   */
  const sendWithMentions = useCallback(
    async (outgoing: string, onQueued?: (sent: boolean) => void) => {
      await send(outgoing, (sent) => {
        if (sent) clearMentions()
        onQueued?.(sent)
      })
    },
    [clearMentions, send],
  )

  const { submit, handleKeyDown, autoGrow, onCompositionStart, onCompositionEnd } = useComposerSubmit({
    text, setText, textareaRef, pendingFiles, pendingRefs, pendingQuote, uploading, sending,
    streaming, steerEnabled, bgMode, setBgMode, speech, steer, submitTask,
    // 两个菜单合一个入口进提交管线：顺序与互斥只由这一处决定
    slash: { onKeyDown: menuKeyDown },
    send: sendWithMentions,
  })

  // 两条外部写入通道：框选引用（挂引用卡）与选区预填（追加文字），见 hook 文件头
  useComposerIntake({ setText, setPendingQuote, textareaRef, autoGrow })

  /** 点快捷 pill：直接替换草稿（是明确动作，别把两条指令拼在一起），光标落末尾 */
  const applyPrompt = (prompt: string) => {
    setText(prompt)
    requestAnimationFrame(() => {
      const el = textareaRef.current
      if (!el) return
      el.focus()
      el.setSelectionRange(el.value.length, el.value.length)
      autoGrow()
    })
  }

  const placeholder = speech.listening
    ? '正在听写…说完点麦克风结束，可手动修改后发送'
    : streaming
      ? steerEnabled
        ? '插话补充指令，Enter 送达当前对话…'
        : '当前后端不支持中途插话，本轮结束后再发送…'
      : bgMode
        ? '后台运行：提交后可关闭页面，跑完会在会话里通知你…'
        : '问点什么…'
  /** 已挂附件/文件夹引用：有它们时后台任务不适用，发送钮也不算空 */
  const hasPendingAttachments = pendingFiles.length > 0 || pendingRefs.length > 0
  /** 输入框是否有内容（正文 / 附件 / 文件夹引用 / 框选引用任一） */
  const hasPayload = Boolean(text.trim()) || hasPendingAttachments || Boolean(pendingQuote)

  return (
    <div className="flex-none border-t border-border p-2.5">
      {/* 内容限宽居中：与消息栏同宽对齐（两边都走 max-w-6xl，宽度一致不错位） */}
      <div className="mx-auto w-full max-w-6xl">
        {/* 框选引用（豆包式）：选区挂成引用条、输入框保持空白；快捷 pills 一键补指令，随消息出站 */}
        {pendingQuote && (
          <ComposerQuote quote={pendingQuote} onRemove={() => setPendingQuote(null)} onPickPrompt={applyPrompt} />
        )}
        <PendingChips />
        {streaming && queuedSteers.length > 0 && (
          <div className={STEER_BAR_CLASS}>
            <span className="min-w-0 flex-1 truncate">已插话 {queuedSteers.length} 条，将在本轮生效</span>
            <button type="button" className={REVOKE_BUTTON_CLASS} onClick={() => void revokeQueuedSteers()} aria-label="撤回插话" title="撤回已排队、尚未生效的插话">
              <Undo2 className="h-3 w-3" />
              撤回
            </button>
          </div>
        )}
        <div className="relative flex items-end gap-2 rounded-[14px] border border-border bg-background px-2.5 py-1.5 shadow-sm transition-[border-color,box-shadow] duration-150 focus-within:border-foreground/30 focus-within:ring-4 focus-within:ring-foreground/10">
          {slash.open && !mention.open && (
            <SlashMenu items={slash.items} selectedIndex={slash.index} onHover={slash.setIndex} onSelect={slash.apply} />
          )}
          {mention.open && (
            <MentionMenu
              id={MENTION_LISTBOX_ID}
              groups={mention.groups}
              highlight={mention.highlight}
              onHover={mention.onHover}
              onPick={(target) => mention.pick(target)}
            />
          )}
          <ComposerToolbar
            bgMode={bgMode}
            onToggleBgMode={() => setBgMode((v) => !v)}
            bgToggleDisabled={streaming || hasPendingAttachments || sending}
            backends={backends}
            answerAgents={answerAgents}
            answerModels={answerModels}
            defaultAgentKind={defaultKind}
            onToggleAnswerAgent={toggleAnswerAgent}
            onSelectAnswerModel={setAnswerModel}
            // 流式中不能改：本轮已开流，改了只会让按钮与已发出的那一轮对不上
            answerDisabled={streaming || sending}
            answerHint=""
            attachDisabled={streaming || uploading || sending}
            onPickFiles={() => fileInputRef.current?.click()}
            fileInputRef={fileInputRef}
            onFilesPicked={addAttachmentFiles}
            speech={speech}
            speechBase={text}
          />
          {/* 焦点始终在 textarea（combobox 模式）：菜单只挂 aria-activedescendant。
              不把 role 改成 combobox —— 那会让「按文本框跳转」的读屏用户找不到这个框，
              且既有测试与交互都以 textbox 为准 */}
          <textarea
            ref={textareaRef}
            value={text}
            rows={1}
            placeholder={placeholder}
            aria-autocomplete="list"
            aria-haspopup="listbox"
            aria-expanded={mention.open}
            aria-controls={mention.open ? MENTION_LISTBOX_ID : undefined}
            className="max-h-30 min-h-6 flex-1 resize-none bg-transparent text-[13px] leading-relaxed text-foreground outline-none placeholder:text-muted-foreground"
            onChange={(e) => {
              // 听写中手动改字：以编辑后的全文为新基线，后续听写在其后追加
              if (speech.listening) speech.rebase(e.target.value)
              setText(e.target.value)
              setCaret(e.target.selectionStart ?? e.target.value.length)
              autoGrow()
            }}
            // 点选/方向键移动光标后 token 会变：不跟踪就只在「敲字」那天才认得引用
            onSelect={(e) => setCaret(e.currentTarget.selectionStart ?? 0)}
            onKeyDown={handleKeyDown}
            onCompositionStart={onCompositionStart}
            onCompositionEnd={onCompositionEnd}
          />
          {streaming ? (
            <button type="button" className={STOP_BUTTON_CLASS} onClick={stop} aria-label="停止生成" title="停止生成（已生成部分会保留）">
              <Square className="h-3 w-3 fill-current" />
            </button>
          ) : (
            <button type="button" className={SEND_BUTTON_CLASS} onClick={submit} disabled={uploading || sending || !hasPayload} aria-label={bgMode ? '提交后台任务' : '发送'} title={uploading ? '附件上传中…' : undefined}>
              <ArrowUp className="h-3.5 w-3.5" strokeWidth={2.5} />
            </button>
          )}
        </div>
        <ComposerFooter bgMode={bgMode} />
      </div>
    </div>
  )
}
