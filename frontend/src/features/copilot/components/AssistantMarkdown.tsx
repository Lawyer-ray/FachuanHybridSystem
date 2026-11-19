/**
 * assistant 正文的 Markdown 渲染（从 MessageList 拆出，控文件规模）。
 *
 * 两条渲染路径：
 *
 * - **非流式**（历史消息）：整篇一次渲染。拆开只多一层节点，没有收益。
 * - **流式中**：只重解析**最后一个块**，前面已完成的块用 memo 封住跳过重算。
 *
 * 为什么流式要分块：每来一个 token 就把整篇交给 ReactMarkdown，解析成本随回复
 * 长度线性增长，长回复明显掉帧。分块后成本退化成「一块的长度」。
 *
 * 为什么分块是安全的：切点只能落在 `splitStreamingMarkdownBlocks` 判定为**一定
 * 安全**的空行处（围栏代码块内、松散列表、缩进续行、引用块、定义行、原始 HTML
 * 块内部一律不切），并保证 `blocks.join('') === text`。这两条不变量在
 * `lib/stream-blocks.test.ts` 里逐条锁死。
 *
 * 背景与事故记录见 docs/harness/pitfalls.md PIT-007 / PIT-009。
 */

import { memo } from 'react'
import ReactMarkdown from 'react-markdown'
import rehypeHighlight from 'rehype-highlight'
import remarkGfm from 'remark-gfm'

import { splitStreamingMarkdownBlocks } from '../lib/stream-blocks'
import { CodeBlock } from './markdown/CodeBlock'

/**
 * 渲染配置只建一次。
 * 每次 render 新建 plugins 数组会让 ReactMarkdown 每次都比对出新引用，
 * 等于放弃它内部的 memo 能力。
 */
const REMARK_PLUGINS = [remarkGfm]
const REHYPE_PLUGINS = [rehypeHighlight]

/** 外链一律新窗口打开：WebView 内跳转会顶掉整个应用 */
const MD_COMPONENTS = {
  a: (props: React.ComponentProps<'a'>) => <a {...props} target="_blank" rel="noreferrer" />,
  // `pre` 接管整块代码（含高亮后的 span 树）：语言标签 + 单块复制。
  // 只映射 `pre`、不映射 `code`：行内 `code` 不该出现复制按钮。
  pre: CodeBlock,
}

/**
 * 单个 markdown 块的渲染。
 *
 * `memo` 是关键：流式过程中前缀块的内容不变（块只会在末尾增长或分裂），
 * 引用相等即可 bail out，省下的正是分块带来的那部分收益。
 */
const MarkdownBlock = memo(function MarkdownBlock({ text }: { text: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={REMARK_PLUGINS}
      rehypePlugins={REHYPE_PLUGINS}
      components={MD_COMPONENTS}
    >
      {text}
    </ReactMarkdown>
  )
})

export const AssistantMarkdown = memo(function AssistantMarkdown({
  text,
  streaming,
}: {
  /** 要渲染的（已经过平滑放字的）正文 */
  text: string
  /** 是否正在直播。非直播走整篇渲染，不做分块 */
  streaming: boolean
}) {
  // 非流式直接整篇渲染：历史消息不拆，少一层包裹也少一份维护面
  if (!streaming) return <MarkdownBlock text={text} />

  const blocks = splitStreamingMarkdownBlocks(text)
  // 只有一块（流式刚开始 / 这一帧拿不到安全切点）时不必走分块路径
  if (blocks.length <= 1) return <MarkdownBlock text={text} />

  return (
    <>
      {blocks.map((block, i) => (
        // key 用下标：块只会在末尾增长或分裂，前缀块的 key 保持稳定，
        // 于是 memo 能对已完成的块 bail out —— 这正是省下来的解析量。
        <MarkdownBlock key={i} text={block} />
      ))}
    </>
  )
})
