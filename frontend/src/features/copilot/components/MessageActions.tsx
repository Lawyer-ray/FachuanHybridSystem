/**
 * 消息级操作条：复制 Markdown / 复制纯文本 / 点赞点踩 / 时间戳。
 *
 * 从 `MessageList.tsx` 的 `Bubble` 里抽出来的（那里原来散着 `CopyButton` 与
 * `RateButtons` 两份各自处理置灰逻辑的代码）。抽出来的真正理由不是行数：
 * 「不可用」在两条路径上的处理方式**曾经不一致**——复制按钮悬浮才出现、
 * 评分按钮用原生 `disabled` 变灰，而原生 `disabled` 收不到 hover/focus，
 * 于是「为什么不能点」的说明（title/tooltip）永远弹不出来，界面上就是
 * 「按钮在、点了没反应」。
 *
 * 现在统一成 DSH `MessageIconActions.tsx:66-84` 的做法：**可见但不可用**，
 * 用 `aria-disabled` + `aria-describedby` 指到一句具体原因上（原生 disabled
 * 只保留给「真的不存在」的场景，这里一个都没有）。原因必须说人话：
 * 不是「不可用」，而是「这条还没落库，刷新后可评分」——律师能据此行动。
 */

import { useId } from 'react'
import { Check, Copy, ThumbsDown, ThumbsUp, Type } from 'lucide-react'

import { useCopyFeedback } from '@/hooks/use-copy-feedback'

import { formatClock } from '../domain'
import { useCopilot } from '../store'

/**
 * Markdown 源码 → 给剪贴板用的纯文本。
 *
 * 刻意**不**写完整解析器：这里只需要「粘到 Word/邮件里不难看」，任何一处
 * 改写都不该丢字。因此只剥结构性标记（标题井号、强调星号、行内反引号、
 * 列表/引用前缀、表格分隔行、链接语法），保留文字与段落换行。
 *
 * 为什么不用 DOM 的 `innerText` 取渲染结果：jsdom 不实现 `innerText`（测试里
 * 拿到 undefined），而且流式期间正文还在变，取 DOM 会把「正在增长的最后一帧」
 * 复制进去，与「复制这条回答」的语义不符。
 */
function toPlainText(markdown: string): string {
  return markdown
    // 围栏代码块：保留代码本身，只去掉 ```lang / ``` 这两行围栏
    .replace(/^[ \t]*```.*$/gm, '')
    // 表格对齐行（|---|---|）：整行都是结构，没有文字
    .replace(/^[ \t]*\|?[\s:|-]+\|[\s:|-]*$/gm, '')
    // 标题井号
    .replace(/^[ \t]{0,3}#{1,6}[ \t]+/gm, '')
    // 引用前缀（> 可嵌套）
    .replace(/^[ \t]*(?:>[ \t]?)+/gm, '')
    // 无序列表标记
    .replace(/^[ \t]*[-*+][ \t]+/gm, '')
    // 有序列表标记
    .replace(/^[ \t]*\d+[.)][ \t]+/gm, '')
    // 图片 → alt、链接 → 文字
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    // 强调/删除线/行内代码：**必须成对**才剥标记，不能无条件删字符。
    // 无条件删 `_` 会把标识符吃掉：`list_contracts` 变 `listcontracts`、
    // 文件名 `合同_终稿.docx` 变 `合同终稿.docx`——复制出去就是另一个东西了（有单测锁）。
    .replace(/(\*\*\*|\*\*|__|~~)(?=\S)([\s\S]*?)(?<=\S)\1/g, '$2')
    .replace(/(\*|_)(?=\S)([^*_\n]*?)(?<=\S)\1(?=[\s.,;:!?，。；：！？)）」』]|$)/g, '$2')
    .replace(/`([^`\n]+)`/g, '$1')
    // 表格竖线当分隔符（单元格之间原本就是空格语义）
    .replace(/[ \t]*\|[ \t]*/g, ' ')
    .replace(/[ \t]+$/gm, '')
    // 压掉多余空行（Markdown 常用两行空行分段，粘出去会变成大空隙）
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

/** 可及名/原因 id 的公共前缀（同一气泡里多个实例也不能撞 id） */
const A11Y_ID_PREFIX = 'copilot-msg-action'

export interface MessageActionsProps {
  /** 助手回答的 Markdown 源码（复制用；也是纯文本的来源） */
  content: string
  /**
   * 落库主键；`null` = 这条还没落库（实时气泡）。
   *
   * 只在能评分时才是数字：由 `ratableMessageId` 判定，详见 `domain/message-id.ts`
   * ——那里记录了「直接 Number(id.slice(3)) 得到 NaN，按钮可点但必然失败」的来历。
   */
  messageId: number | null
  /** 当前评分（store 的乐观值） */
  rating?: 'up' | 'down'
  /** 发生时刻（ms）；缺失则不渲染时间戳 */
  createdAt?: number
}

export function MessageActions({ content, messageId, rating, createdAt }: MessageActionsProps) {
  const rate = useCopilot((s) => s.rateMessage)
  const { copied, copy } = useCopyFeedback({ resetMs: 1500 })
  // 同一屏里每条回答都有一份，id 必须逐实例唯一（用 useId，不用下标/内容哈希）
  const reasonId = `${A11Y_ID_PREFIX}-${useId()}`
  const canRate = messageId !== null

  /** 评分按钮：不可用时仍可聚焦/悬浮，只是不生效，并把原因挂到 aria-describedby */
  const rateButton = (r: 'up' | 'down') => {
    const label = r === 'up' ? '有帮助' : '没帮助'
    return (
      <button
        type="button"
        aria-label={label}
        aria-disabled={canRate ? undefined : true}
        aria-describedby={canRate ? undefined : reasonId}
        title={canRate ? label : '本条还没落库，刷新后可评分'}
        className={
          'flex h-6 w-6 items-center justify-center rounded-[6px] text-muted-foreground transition-colors hover:bg-secondary ' +
          (canRate ? (rating === r ? 'text-foreground' : 'opacity-60 hover:opacity-100') : 'cursor-not-allowed opacity-40')
        }
        onClick={() => {
          // aria-disabled 不会拦住点击，这里自己拦——拦的同时原因还挂在 describedby 上
          if (messageId === null) return
          void rate(messageId, rating === r ? 'none' : r)
        }}
      >
        {r === 'up' ? <ThumbsUp className="h-3 w-3" aria-hidden /> : <ThumbsDown className="h-3 w-3" aria-hidden />}
      </button>
    )
  }

  return (
    <span className="ml-1.5 inline-flex items-center gap-0.5 align-middle" data-testid="message-actions">
      {rateButton('up')}
      {rateButton('down')}
      {/* 复制动作 hover/focus 才浮现：常显会让每条回答下面都挂一排灰图标，
          长转录里视觉噪音盖过正文。opacity 而非 display，不产生布局跳动。 */}
      <span className="inline-flex items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
        <button
          type="button"
          aria-label="复制回答"
          title="复制 Markdown 源码"
          className="flex h-6 w-6 items-center justify-center rounded-[6px] text-muted-foreground hover:bg-secondary hover:text-foreground"
          onClick={() => void copy(content)}
        >
          {copied ? <Check className="h-3 w-3 text-emerald-600" aria-hidden /> : <Copy className="h-3 w-3" aria-hidden />}
        </button>
        <button
          type="button"
          aria-label="复制纯文本"
          title="复制纯文本（去掉 Markdown 标记，贴到 Word/邮件里用）"
          className="flex h-6 w-6 items-center justify-center rounded-[6px] text-muted-foreground hover:bg-secondary hover:text-foreground"
          onClick={() => void copy(toPlainText(content))}
        >
          <Type className="h-3 w-3" aria-hidden />
        </button>
      </span>
      {createdAt ? (
        <time
          className="ml-1 text-[10.5px] text-muted-foreground tabular-nums"
          dateTime={new Date(createdAt).toISOString()}
          title={new Date(createdAt).toLocaleString('zh-CN')}
        >
          {formatClock(createdAt)}
        </time>
      ) : null}
      {/* 不可用原因的落点：sr-only 而不是 title——tooltip 要悬浮才出现，
          读屏与键盘用户永远看不到它，而支配 aria-describedby 的元素必须常驻。 */}
      <span id={reasonId} className="sr-only">
        这条回答还没落库，暂不能评分，刷新本会话后可评分
      </span>
    </span>
  )
}
