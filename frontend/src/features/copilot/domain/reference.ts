/**
 * 引用与改写信号：框选引用的出站构建、默认出站提示语、AI 改写落盘识别。
 *
 * 纯函数，无 React 依赖。框选块（buildSelectionQuoteBlock）的**回放解析**
 * 是 splitQuoteBlock，与其它锚点块一起放在 transcript.ts（成对互逆）；
 * 这里只放发送侧与 tool_result 侧的识别逻辑。
 */

import type { FolderRefDraft, SelectionQuote } from '../types'

/** 框选文本进引用块前的整形：换行归一、限长（太长对齐卡片显示与块内文本） */
export function normalizeSelectionText(raw: string, cap = 400): string {
  const oneLine = raw.replace(/\s*\n\s*/g, ' ').trim()
  return oneLine.length > cap ? oneLine.slice(0, cap) + '……' : oneLine
}

/** 构建框选引用块（发送侧；与 transcript.ts 的 SENT_QUOTE_RE 严格互逆） */
export function buildSelectionQuoteBlock(q: SelectionQuote): string {
  const idKey = q.kind === 'case' ? 'case_id' : 'contract_id'
  const text = normalizeSelectionText(q.text).replace(/"/g, '”')
  return `[已引用选段："${text}" (${idKey}=${q.ownerId}, subpath="${q.subpath}")]`
}

/**
 * 空正文发送时的默认指令：只带引用/附件/选段也能发，但模型需要一句话知道
 * 律师要什么。措辞按「引用了什么」选——目录引用是浏览梳理，文件引用是
 * 分析，附件是分析，选段是结合原文件分析。
 */
export function defaultOutgoingPrompt(
  refs: FolderRefDraft[],
  fileCount: number,
  quote: SelectionQuote | null,
): string {
  if (refs.length > 0) {
    return refs.every((r) => r.isFolder) ? '请浏览我引用的目录并梳理其中的材料。' : '请分析我引用的文件。'
  }
  if (fileCount > 0) return '请分析我上传的附件。'
  if (quote) return '请结合原文件，分析我引用的这段内容。'
  return ''
}

/** rewrite_folder_file 落盘成功的信号（后端 apply 结果里能带出的字段） */
export interface FileRewriteSignal {
  /** 被覆写文件的归属：合同绑定文件夹 / 案件绑定文件夹 */
  kind: 'contract' | 'case'
  /** 被覆写的合同或案件 id */
  ownerId: number
  /** 绑定根下的相对路径 */
  subpath: string
  /** 文件名 */
  name: string
  /**
   * 原文片段 / 改写全文（来自 tool_call 的 arguments，非 apply 结果）。
   *
   * tool_result 的 result 在 SSE 里被截到 2000 字读不回全文，调用参数
   * 却完整到达。带上这对字段时，打开中的画布可**就地**落修订（插件桥
   * apply-revision），免掉整页重载；缺失则回退换 key 重载。
   */
  original?: string
  replacement?: string
}

/** rewrite_folder_file 调用参数里提取原文/改写全文；形状不对或为空返回 null（宁缺勿错） */
export function extractRewriteArgs(args: unknown): { original: string; replacement: string } | null {
  let parsed: unknown = args
  if (typeof parsed === 'string') {
    try {
      parsed = JSON.parse(parsed)
    } catch {
      return null
    }
  }
  if (!parsed || typeof parsed !== 'object') return null
  const { original, replacement } = parsed as Record<string, unknown>
  if (typeof original !== 'string' || typeof replacement !== 'string') return null
  if (!original.trim() || !replacement.trim()) return null
  return { original, replacement }
}

/**
 * 从 tool_result 事件里识别「AI 已把修订写回文件夹文件」。
 *
 * 后端 apply 成功返回 `{"applied": true, "contract_id": N, "subpath": …,
 * "name": …}`（合同直改）或带 `case_id`（案件直改）——MCP 工具名带
 * `mcp__fachuan__` 前缀，结尾匹配即可。结果字符串可能被 SSE 截断（bridge
 * 限 2000 字符）——JSON.parse 失败、applied 不为 true、缺归属 id/subpath
 * 一律返回 null：**宁可不刷新，也不能误刷新**（误刷新会把正在编辑的画布
 * 无谓重载）。
 *
 * `args` 是同一次调用的 tool_call 参数（原文/改写全文的唯一完整来源），
 * 用于画布内就地落修订；缺了也能用，只是退回整页重载。
 */
export function parseFileRewrite(
  toolName: string | undefined,
  resultText: string,
  isError = false,
  args?: { original: string; replacement: string } | null,
): FileRewriteSignal | null {
  if (isError || !toolName || !toolName.endsWith('rewrite_folder_file')) return null
  try {
    const parsed = JSON.parse(resultText) as {
      applied?: unknown
      contract_id?: unknown
      case_id?: unknown
      subpath?: unknown
      name?: unknown
    }
    if (parsed.applied !== true) return null
    // 归属 id 二选一：合同直改回 contract_id，案件直改回 case_id
    const contractId = Number(parsed.contract_id)
    const caseId = Number(parsed.case_id)
    const hasContract = Number.isInteger(contractId) && contractId > 0
    const hasCase = Number.isInteger(caseId) && caseId > 0
    const subpath = typeof parsed.subpath === 'string' ? parsed.subpath : ''
    if (subpath === '' || (!hasContract && !hasCase)) return null
    const kind: 'contract' | 'case' = hasCase && !hasContract ? 'case' : 'contract'
    return {
      kind,
      ownerId: kind === 'case' ? caseId : contractId,
      subpath,
      name: typeof parsed.name === 'string' && parsed.name ? parsed.name : subpath.split('/').pop() || subpath,
      ...(args ? { original: args.original, replacement: args.replacement } : {}),
    }
  } catch {
    return null
  }
}

/** 工具名去掉 pi 的 mcp__fachuan__ 前缀（纯展示层归一） */
export function shortToolName(name: string | undefined): string {
  if (!name) return '工具'
  const marker = 'mcp__fachuan__'
  const i = name.indexOf(marker)
  return i >= 0 ? name.slice(i + marker.length) : name
}
