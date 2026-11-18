/**
 * 流式 markdown 的「安全分块」纯函数（无 React，可单测）。
 *
 * 背景：流式输出时每来一个 token 都会重新解析**整篇** markdown，解析成本随回复
 * 长度线性增长，长回复明显掉帧。若只重解析正在生长的尾块，成本就退化成
 * 「一块的长度」。
 *
 * 但分块渲染只有在「分块渲染结果」与「整篇一次渲染」等价时才安全，否则会把
 * 列表、表格、嵌套结构拆坏。本文件只找**一定安全**的空行切点，找不到就把整篇
 * 当一块返回——宁可慢一点，也不能渲染错。
 *
 * 硬不变量（本文件存在的前提，测试里逐条验证）：
 *
 * 1. `splitStreamingMarkdownBlocks(text).join('') === text` —— 一字不差。
 *    切点只吃空行里的第一个换行，换行不丢不重。
 * 2. 各块单独解析得到的 AST 序列拼接，等价于整篇一次解析。保证方式是
 *    **只在块级结构确定不跨界时空行切**：CommonMark 的块级边界只可能来自空行、
 *    围栅代码块、容器块（列表 / 引用）的开闭、链接引用定义与脚注定义。这些来源
 *    里只要有一个可能跨越空行，本函数就放弃切分。剩下「孤立段落之间的空行」——
 *    解析器不可能把两段普通文字粘成同一个块，在那里切是安全的。
 *
 * 判据取自 CommonMark 0.31 的块级规则：
 *
 * - **围栅代码块**：围栏内空行不结束代码块，故围栏内一律不切；收尾围栏不许带
 *   语言名（带 info string 的 ` ```js ` 只是围栏内的一行代码）。流式未闭合时
 *   整篇保持一块。
 * - **松散列表 / 缩进续行**：空行后接列表项或缩进行仍属于上一个列表 / 段落，
 *   拆开会把「一个松散列表」变成「两个列表」、把续行变成孤立段落。
 * - **链接引用定义 / 脚注定义**：定义可出现在任意位置被任意块引用，拆块会让
 *   别的块里的引用失去定义。
 * - **原始 HTML 块**（`<pre>`/`<script>`/`<style>`/`<textarea>`）：空行不结束它，
 *   未闭合时空行后的内容仍属于同一个 HTML 块。
 */

/** 围栅代码块开场：3 个以上反引号，允许 0–3 个前导空格，后可带 info string */
const FENCE = /^ {0,3}(`{3,})(.*)$/

/** 空行：换行后紧跟一行只有空白（`\r` 算空白）再是换行 */
const BLANK_GAP = /\n\r?\n/

/** 列表项：`-`/`*`/`+` 或「数字 + `.`/`)`」，后接空白或行尾（0–3 个前导空格） */
const LIST_ITEM = /^ {0,3}(?:[-*+]|\d{1,9}[.)])(?:[ \t]|$)/

/** 引用块的行首 `>`（允许 0–3 个前导空格） */
const BLOCKQUOTE = /^ {0,3}>/

/** 链接引用定义：行首（0–3 空格）`[label]:`；`[^label]:` 归脚注定义 */
const LINK_REFERENCE_DEFINITION = /^ {0,3}\[(?!\^)[^\]]*\]:/

/** 脚注定义：行首（0–3 空格）`[^label]:` */
const FOOTNOTE_DEFINITION = /^ {0,3}\[\^[^\]]*\]:/

/** 会吞掉空行的原始 HTML 块开场（CommonMark 类型 1 块，空行不结束它） */
const HTML_RAW_BLOCK = /^ {0,3}<(pre|script|style|textarea)(?:[ \t>]|$)/i

/** 从 `from` 起取第一行（不含换行符）与下一行起点 */
function lineAt(text: string, from: number): { line: string; next: number } {
  const newline = text.indexOf('\n', from)
  if (newline < 0) return { line: text.slice(from), next: text.length }
  return { line: text.slice(from, newline), next: newline + 1 }
}

/**
 * 从 `from` 起是否落在一个**未闭合的原始 HTML 块**里（`<pre>` 等）。
 *
 * 这类块的空行不结束它：块内出现空行时，后面的行仍属于同一个 HTML 块，
 * 在该空行处切会把一整块 HTML 拆成「HTML + 若干段落」。
 *
 * 返回「该块未闭合」的交点：若 `from` 处开了一个原始 HTML 块且到文末都没闭合，
 * 返回 true。注意 `from` 必须正好是块的开场行首——调用方负责扫描到那一行。
 */
function insideUnclosedRawHtml(text: string, from: number): boolean {
  const opened = HTML_RAW_BLOCK.exec(lineAt(text, from).line)
  if (opened === null) return false
  const tag = opened[1] ?? ''
  const closer = new RegExp(`</${tag}>`, 'i')
  // 开场行自己就闭合（`<pre>x</pre>`）只是普通段落，不构成 HTML 块
  if (closer.test(opened[0])) return false
  let pos = from + opened[0].length
  while (pos < text.length) {
    const { line, next } = lineAt(text, pos)
    if (closer.test(line)) return false
    pos = next
  }
  return true
}

/**
 * 切点 `cut` 是否落在一个尚未闭合的原始 HTML 块**内部**。
 *
 * 从 `blockStart` 逐行扫到 `cut`，遇到 HTML 块开场行就用
 * `insideUnclosedRawHtml` 判断它是否延伸到文末；若是，则该块覆盖了 `cut`，
 * 此处不能切。扫过开场行后要跳到它的下一行继续找下一个可能的开场。
 *
 * 2026-11-18 修正：原实现只在 `cut` 处判断，漏了「HTML 块开在切点之前」
 * 这种形态（`a\n\n<pre>\nraw\n\nstill raw\n</pre>` 会被从中间劈开）。
 */
function cutSplitsRawHtml(text: string, blockStart: number, cut: number): boolean {
  let pos = blockStart
  while (pos < cut) {
    const { line, next } = lineAt(text, pos)
    const opened = HTML_RAW_BLOCK.exec(line)
    if (opened === null) {
      pos = next
      continue
    }
    const tag = opened[1] ?? ''
    const closer = new RegExp(`</${tag}>`, 'i')
    // 开场行自己就闭合（`<pre>x</pre>`）只是普通段落，不是块
    if (closer.test(line)) {
      pos = next
      continue
    }
    // 从开场行的下一行起找闭合标签。若在找到之前先碰到了切点，
    // 说明 `cut` 落在这个 HTML 块内部 → 不能在这里切。
    let scan = next
    while (scan < text.length) {
      const { line: inner, next: innerNext } = lineAt(text, scan)
      if (closer.test(inner)) {
        // 闭合标签行本身也在块里，块结束于该行之后
        if (scan < cut) {
          pos = innerNext
          break
        }
        return cut >= scan && cut < innerNext
      }
      if (scan >= cut) return true // 切点在块内（尚未遇到闭合）
      scan = innerNext
    }
    // 扫到文末仍未闭合
    if (scan >= text.length) return cut >= pos
  }
  return false
}

/**
 * 判断「从 `from` 开始的那一块」里是否存在跨空行的结构，出现就说明 `from`
 * 之前的空行不是块边界。
 *
 * 两类陷阱：
 *
 * - **定义行**（链接引用定义 / 脚注定义）：定义可被任意块引用，整篇保持一块；
 * - **容器块**（列表 / 引用 / 原始 HTML）：内容跨过空行时才危险（松散列表、
 *   缩进续行、HTML 块吞空行）。所以按行扫到下一个空行为止——容器块在空行处
 *   结束的话，那个空行本身就是合法边界。原始 HTML 块由
 *   `insideUnclosedRawHtml` 单独兜住（它跨空行，本循环的「见空行即停」不适用）。
 */
function spansAcrossBlank(text: string, from: number): boolean {
  if (insideUnclosedRawHtml(text, from)) return true
  let pos = from
  while (pos < text.length) {
    const { line, next } = lineAt(text, pos)
    if (LINK_REFERENCE_DEFINITION.test(line) || FOOTNOTE_DEFINITION.test(line)) return true
    if (line.trim().length === 0) return false
    // 列表 / 引用的续行可能跨空行（松散列表、懒续行），保守地不在这里切
    if (LIST_ITEM.test(line) || BLOCKQUOTE.test(line)) return true
    pos = next
  }
  return false
}

/**
 * 空行（`newlineAt` 处那个换行）能否作为切点，可以返回切点下标，否则 `-1`。
 *
 * 三条否决：空行后没有内容、下一行不顶格（缩进续行）、下一行是列表项或开启了
 * 跨空行的容器块 / 定义行（会拆断松散列表、引用、HTML 块或引用定义）。
 */
/**
 * 空行（`newlineAt` 处那个换行）能否作为切点，可以返回切点下标，否则 `-1`。
 *
 * 否决条件：空行后没有内容、下一行不顶格（缩进续行）、下一行是列表项或开启了
 * 跨空行的容器块 / 定义行（会拆断松散列表、引用、HTML 块或引用定义），
 * 以及**切点本身落在一个未闭合 HTML 块内部**（见 `cutSplitsUnclosedRawHtml`）。
 */
function cutAtBlankGap(text: string, newlineAt: number, blockStart: number): number {
  // 切点不得落在任何原始 HTML 块（闭合或未闭合）内部

  const gap = BLANK_GAP.exec(text.slice(newlineAt))
  if (!gap) return -1
  const cut = newlineAt + gap[0].length
  if (cut >= text.length) return -1

  const { line: after } = lineAt(text, cut)
  const indented = after.startsWith(' ') || after.startsWith('\t')
  if (indented || LIST_ITEM.test(after) || spansAcrossBlank(text, cut)) return -1
  if (cutSplitsRawHtml(text, blockStart, cut)) return -1
  return cut
}

/**
 * 把流式 markdown 文本切成可独立渲染的块，切点只落在安全的空行处。
 *
 * 返回值满足 `blocks.join('') === text`；没有安全切点时返回整篇一块。
 * 连续多个空行只切一次：多余的换行留在上一块尾部（解析器同样视作块末尾空白）。
 */
export function splitStreamingMarkdownBlocks(text: string): string[] {
  if (text.length === 0) return []

  const blocks: string[] = []
  let blockStart = 0
  let pos = 0
  let insideFence = false

  while (pos < text.length) {
    const { line, next } = lineAt(text, pos)
    const fence = FENCE.exec(line)
    if (fence !== null) {
      if (!insideFence) insideFence = true
      // 收尾围栏必须是纯反引号：带语言名的只是围栏内的一行代码
      else if ((fence[2] ?? '').trim().length === 0) insideFence = false
    } else if (!insideFence) {
      const cut = cutAtBlankGap(text, next - 1, blockStart)
      if (cut >= 0) {
        blocks.push(text.slice(blockStart, cut))
        blockStart = cut
        pos = cut
        continue
      }
    }
    pos = next
  }

  blocks.push(text.slice(blockStart))
  return blocks
}
