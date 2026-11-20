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
 * **入站引用的注入方式**：正文里的 `[Kn]` 不是靠 remark 插件在 AST 阶段改写的，
 * 而是在 `components` 映射里把**文本节点**换成 `<CitationMark>`（见
 * `annotateCitations`）。三条理由：
 *
 * 1. 不新增依赖、也不碰 remark/rehype 插件链——插件要处理 HAST 的 position
 *    映射，写错了会静默吞字；文本节点替换是纯 React，出问题一眼看得见。
 * 2. 分块 memo 结构原样保留：只有正在生长的尾块会重新走一遍替换。
 * 3. 不用 `dangerouslySetInnerHTML`：react-markdown 默认不执行原始 HTML，这是
 *    整个气泡唯一的注入面防线，不能为了加个角标把它拆了。
 *
 * 背景与事故记录见 docs/harness/pitfalls.md PIT-007 / PIT-009。
 */

import { cloneElement, isValidElement, memo, useMemo } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import rehypeHighlight from 'rehype-highlight'
import remarkGfm from 'remark-gfm'

import {
  hasPendingCiteMarker,
  splitCiteSegments,
  type CitationRef,
} from '../domain/knowledge'
import { splitStreamingMarkdownBlocks } from '../lib/stream-blocks'
import { CitationMark } from './markdown/CitationMark'
import { CodeBlock } from './markdown/CodeBlock'
import { TableBlock } from './markdown/TableBlock'

/**
 * 渲染配置只建一次。
 * 每次 render 新建 plugins 数组会让 ReactMarkdown 每次都比对出新引用，
 * 等于放弃它内部的 memo 能力。
 */
const REMARK_PLUGINS = [remarkGfm]
const REHYPE_PLUGINS = [rehypeHighlight]

/** 外链一律新窗口打开：WebView 内跳转会顶掉整个应用 */
const BASE_COMPONENTS: Components = {
  a: (props: React.ComponentProps<'a'>) => <a {...props} target="_blank" rel="noreferrer" />,
  // `pre` 接管整块代码（含高亮后的 span 树）：语言标签 + 单块复制。
  // 只映射 `pre`、不映射 `code`：行内 `code` 不该出现复制按钮。
  pre: CodeBlock,
  // 表格：右上角「复制表格」（TSV）+ 长表格滚动
  table: TableBlock,
}

/**
 * 去掉 react-markdown 塞给自定义组件的 `node`（mdast/hast 节点）。
 *
 * 它只给组件用来读位置信息，透传到 DOM 会变成 `node="[object Object]"` 之类的
 * 脏属性（React 19 对未知属性是透传，不再自动丢弃）。`children` 一并摘掉，
 * 由调用方换成注入了角标的版本。
 */
function containerProps<T extends { node?: unknown; children?: React.ReactNode }>(
  props: T,
): Omit<T, 'node' | 'children'> {
  const { node, children, ...rest } = props
  void node
  void children
  return rest
}

/** 这些标签里的 `[K1]` 是代码或链接文字，不是来源引用 */
const CITE_SKIP_TAGS = new Set<string>(['code', 'pre', 'a'])

/**
 * 把子树里的文本节点按 `[Kn]` 切成「文字 / 角标」，其余节点原样向下递归。
 *
 * 为什么必须递归而不是只处理段落顶层：`**结论见 [K1]**`、`| 甲 | [K2] |`、
 * `- [K3] 另见` 都让标记落在 strong/td/li 里面，只看顶层字符串会漏。
 */
function annotateCitations(
  children: React.ReactNode,
  byNo: ReadonlyMap<number, CitationRef>,
): React.ReactNode {
  const known = new Set(byNo.keys())

  const annotateNode = (node: React.ReactNode): React.ReactNode => {
    if (typeof node === 'string') {
      const segments = splitCiteSegments(node, known)
      if (!segments.some((segment) => segment.kind === 'cite')) return node
      return segments.map((segment, index) => {
        if (segment.kind === 'text') return segment.text
        const citation = byNo.get(segment.citeNo)
        // splitCiteSegments 已按 known 过滤，这里只是收窄类型；真走到就退回原文
        if (citation === undefined) return `[K${segment.citeNo}]`
        return (
          <CitationMark key={`${segment.citeNo}-${index}`} citeNo={segment.citeNo} citation={citation} />
        )
      })
    }
    if (Array.isArray(node)) return node.map(annotateNode)
    if (!isValidElement(node)) return node
    if (CITE_SKIP_TAGS.has(String(node.type))) return node
    const element = node as React.ReactElement<{ children?: React.ReactNode }>
    if (element.props.children === undefined) return node
    return cloneElement(element, undefined, annotateNode(element.props.children))
  }

  return annotateNode(children)
}

/**
 * 按引用表建 components 映射。
 *
 * 只接管「正文能直接落在里面」的容器：`p`、`li`（紧凑列表不包 `<p>`）、
 * `td`/`th`（表格里的角标）、`h1`~`h4`。blockquote 里的正文同样包在 `<p>` 里，
 * 不必单独列；`code`/`pre`/`a` 明确不接管（见 CITE_SKIP_TAGS）。
 *
 * 引用表为空（历史消息没存来源 / 正文里的 `[K1]` 是模型自己编的）时返回
 * **原样的 BASE_COMPONENTS**：角标点了没有内容可看，就退回普通文本——
 * 「能点但点开是空」比不渲染更伤信任。
 */
function buildComponents(citations: readonly CitationRef[] | undefined): Components {
  if (citations === undefined || citations.length === 0) return BASE_COMPONENTS
  const byNo = new Map(citations.map((citation) => [citation.citeNo, citation]))
  const annotate = (children: React.ReactNode) => annotateCitations(children, byNo)

  return {
    ...BASE_COMPONENTS,
    p: (props) => <p {...containerProps(props)}>{annotate(props.children)}</p>,
    li: (props) => <li {...containerProps(props)}>{annotate(props.children)}</li>,
    td: (props) => <td {...containerProps(props)}>{annotate(props.children)}</td>,
    th: (props) => <th {...containerProps(props)}>{annotate(props.children)}</th>,
    h1: (props) => <h1 {...containerProps(props)}>{annotate(props.children)}</h1>,
    h2: (props) => <h2 {...containerProps(props)}>{annotate(props.children)}</h2>,
    h3: (props) => <h3 {...containerProps(props)}>{annotate(props.children)}</h3>,
    h4: (props) => <h4 {...containerProps(props)}>{annotate(props.children)}</h4>,
  }
}

/**
 * 流式降级：这一段末尾还有半截 `[K` 时整段不给角标。
 *
 * 否则 `[K1` 这一帧不渲染、`[K12]` 闭合后角标突然出现且编号变了——用户刚点开
 * 的可能是另一条来源。只在流式下判断：历史消息末尾真有个 `[K` 是正文本身的
 * 字符，不该连累同段里已经闭合的角标。
 */
function blockCitations(
  text: string,
  streaming: boolean,
  citations: readonly CitationRef[] | undefined,
): readonly CitationRef[] | undefined {
  return streaming && hasPendingCiteMarker(text) ? undefined : citations
}

/**
 * 单个 markdown 块的渲染。
 *
 * `memo` 是关键：流式过程中前缀块的内容不变（块只会在末尾增长或分裂），
 * 引用相等即可 bail out，省下的正是分块带来的那部分收益。
 */
const MarkdownBlock = memo(function MarkdownBlock({
  text,
  citations,
}: {
  text: string
  citations?: readonly CitationRef[]
}) {
  // 组件映射按引用表身份缓存：引用表不变，components 对象就不变，
  // ReactMarkdown 内部对 components 的比对才不会每次判「换了新组件」而全树重挂
  const components = useMemo(() => buildComponents(citations), [citations])
  return (
    <ReactMarkdown
      remarkPlugins={REMARK_PLUGINS}
      rehypePlugins={REHYPE_PLUGINS}
      components={components}
    >
      {text}
    </ReactMarkdown>
  )
})

export const AssistantMarkdown = memo(function AssistantMarkdown({
  text,
  streaming,
  citations,
}: {
  /** 要渲染的（已经过平滑放字的）正文 */
  text: string
  /** 是否正在直播。非直播走整篇渲染，不做分块 */
  streaming: boolean
  /**
   * 本轮的引用表（`message.citations`）。
   * 缺省 / 空数组时正文里的 `[Kn]` 一律当普通文本——角标必须能点出内容，
   * 点了空的等于骗人。
   */
  citations?: readonly CitationRef[]
}) {
  // 非流式直接整篇渲染：历史消息不拆，少一层包裹也少一份维护面
  if (!streaming) return <MarkdownBlock text={text} citations={citations} />

  const blocks = splitStreamingMarkdownBlocks(text)
  // 只有一块（流式刚开始 / 这一帧拿不到安全切点）时不必走分块路径
  if (blocks.length <= 1) {
    return <MarkdownBlock text={text} citations={blockCitations(text, streaming, citations)} />
  }

  return (
    <>
      {blocks.map((block, i) => (
        // key 用下标：块只会在末尾增长或分裂，前缀块的 key 保持稳定，
        // 于是 memo 能对已完成的块 bail out —— 这正是省下来的解析量。
        <MarkdownBlock key={i} text={block} citations={blockCitations(block, streaming, citations)} />
      ))}
    </>
  )
})
