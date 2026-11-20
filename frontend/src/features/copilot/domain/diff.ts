/**
 * 行级 diff（纯函数，node 可测）。
 *
 * **为什么前端自己算 diff**：`rewrite_folder_file` 的原文与改写全文只在
 * `tool_call` 的 arguments 里完整到达（`tool_result.result` 被 SSE 截到 2000
 * 字，见 `domain/reference.ts` 的注释），后端没有、也不会为「显示」再算一遍。
 * 律师最关心的一句话是「这条改写到底动了哪一句」，而这句话的原料当场就齐了。
 *
 * **为什么不用 diff 库**：只需要「行级 + 上下文 3 行」这一种形态。契约形状
 * 对标 unified diff（`oldStart/newStart/oldLines/newLines` + 每行首字符
 * `'+' | '-' | ' '`），渲染层（`HunkRows`）与后端将来若真给出 hunks 可以
 * 完全共用一套。引入一个库只为省 100 行，却多一份「它的行号语义与我们不同」
 * 的风险，不划算。
 *
 * **为什么有预算上限**：LCS 是 O(n·m)。合同动辄几千行，若律师让 AI 整篇
 * 重写，朴素实现会在一帧里分配上百万格。超预算时**不猜**——退化成一个
 * 「整篇替换」的 hunk，并用 `truncated` 明说被截断。宁可少画，不能画错还
 * 不说（这是 `parseFileRewrite` 那段「宁可不刷新，也不能误刷新」的同一条
 * 纪律）。
 */

/** 与 unified diff 同形的 hunk。`lines` 的每行首字符是 `'+' | '-' | ' '`。 */
export interface Hunk {
  /** 旧文件里本 hunk 的起始行号（1 起） */
  oldStart: number
  /** 新文件里本 hunk 的起始行号（1 起） */
  newStart: number
  oldLines: number
  newLines: number
  lines: string[]
}

export interface LineDiff {
  hunks: Hunk[]
  /**
   * 因超出预算而退化成「整篇替换」。
   *
   * 与「改动太多」区分：这是**算不出**，不是**算出来很多**。UI 必须据此换
   * 文案（「改动过大，仅显示整体替换」而不是「无改动」）。
   */
  truncated: boolean
}

/** LCS 表格的格数上限：500×500。超过就退化成整篇替换。 */
const MAX_CELLS = 250_000

/** 默认上下文行数（与 unified diff 一致） */
export const DEFAULT_CONTEXT = 3

type Op = { kind: ' ' | '-' | '+'; text: string }

/** 按 `\n` 切行；末尾换行不产生空行（否则每个文件都会多出一行假改动） */
function splitLines(text: string): string[] {
  if (text === '') return []
  const lines = text.split('\n')
  if (lines[lines.length - 1] === '') lines.pop()
  return lines
}

/**
 * LCS 回溯产出编辑串。
 *
 * `a` 与 `b` 是已经剪掉公共前后缀的中间段——不做这一步，一份「改了一个字」
 * 的合同也要为整篇建表。
 */
function lcsOps(a: string[], b: string[]): Op[] {
  const n = a.length
  const m = b.length
  // dp[i][j] = a[i..] 与 b[j..] 的 LCS 长度；用一维滚动数组换空间
  const width = m + 1
  const dp = new Uint32Array((n + 1) * width)
  // Uint32Array 的下标读取在 `noUncheckedIndexedAccess` 下是 `number | undefined`，
  // 越界恒为 0，这里统一用 `?? 0` 取值（语义与“表格外即无公共子序列”一致）
  const cell = (i: number, j: number): number => dp[i * width + j] ?? 0
  for (let i = n - 1; i >= 0; i -= 1) {
    for (let j = m - 1; j >= 0; j -= 1) {
      dp[i * width + j] =
        a[i] === b[j] ? cell(i + 1, j + 1) + 1 : Math.max(cell(i + 1, j), cell(i, j + 1))
    }
  }
  const ops: Op[] = []
  let i = 0
  let j = 0
  while (i < n && j < m) {
    const left = a[i] ?? ''
    const right = b[j] ?? ''
    if (left === right) {
      ops.push({ kind: ' ', text: left })
      i += 1
      j += 1
    } else if (cell(i + 1, j) >= cell(i, j + 1)) {
      ops.push({ kind: '-', text: left })
      i += 1
    } else {
      ops.push({ kind: '+', text: right })
      j += 1
    }
  }
  while (i < n) {
    ops.push({ kind: '-', text: a[i] ?? '' })
    i += 1
  }
  while (j < m) {
    ops.push({ kind: '+', text: b[j] ?? '' })
    j += 1
  }
  return ops
}

/** 把整串编辑切成带上下文的 hunk；相邻/重叠的上下文窗口合并 */
function toHunks(ops: Op[], beforeCount: number, context: number): Hunk[] {
  // 每个 op 在旧/新文件里的行号（1 起），先算一遍再切片
  const oldNo: number[] = []
  const newNo: number[] = []
  let o = 1
  let s = 1
  for (const op of ops) {
    if (op.kind === ' ') {
      oldNo.push(o)
      newNo.push(s)
      o += 1
      s += 1
    } else if (op.kind === '-') {
      oldNo.push(o)
      newNo.push(s)
      o += 1
    } else {
      oldNo.push(o)
      newNo.push(s)
      s += 1
    }
  }

  // 改动点的下标集合；每个改动点前后各留 context 行
  const marked: boolean[] = ops.map(() => false)
  let changed = false
  ops.forEach((op, at) => {
    if (op.kind === ' ') return
    changed = true
    for (let k = Math.max(0, at - context); k <= Math.min(ops.length - 1, at + context); k += 1) {
      marked[k] = true
    }
  })
  if (!changed) return []

  const hunks: Hunk[] = []
  let at = 0
  while (at < ops.length) {
    while (at < ops.length && !marked[at]) at += 1
    if (at >= ops.length) break
    const start = at
    while (at < ops.length && marked[at]) at += 1
    const slice = ops.slice(start, at)
    const oldLines = slice.filter((op) => op.kind !== '+').length
    const newLines = slice.filter((op) => op.kind !== '-').length
    // 空侧仍要有一个可寻址的行号：用该位置「本应插入/删除」的坐标
    const firstOld = oldNo[start] ?? beforeCount + 1
    const firstNew = newNo[start] ?? 1
    hunks.push({
      oldStart: oldLines === 0 ? Math.max(1, firstOld - 1) : firstOld,
      newStart: firstNew,
      oldLines,
      newLines,
      lines: slice.map((op) => `${op.kind}${op.text}`),
    })
  }
  return hunks
}

/**
 * 行级 diff。
 *
 * @param before 原文（`rewrite_folder_file` 的 `original`）
 * @param after 改写全文（同次调用的 `replacement`）
 * @param context 上下文行数，默认 3
 */
export function lineDiff(before: string, after: string, context: number = DEFAULT_CONTEXT): LineDiff {
  const a = splitLines(before)
  const b = splitLines(after)
  if (before === after) return { hunks: [], truncated: false }

  // 剪掉公共前缀/后缀：既省表格，也让「只改一句」的 hunk 落在正确位置
  let head = 0
  while (head < a.length && head < b.length && a[head] === b[head]) head += 1
  let tail = 0
  while (
    tail < a.length - head &&
    tail < b.length - head &&
    a[a.length - 1 - tail] === b[b.length - 1 - tail]
  ) {
    tail += 1
  }
  const midA = a.slice(head, a.length - tail)
  const midB = b.slice(head, b.length - tail)

  if (midA.length * midB.length > MAX_CELLS) {
    // 超预算：把整份内容当作一次替换。行号与行数照实给，UI 据此说「整体替换」
    return {
      truncated: true,
      hunks: [
        {
          oldStart: 1,
          newStart: 1,
          oldLines: a.length,
          newLines: b.length,
          lines: [
            ...a.map((text) => `-${text}`),
            ...b.map((text) => `+${text}`),
          ],
        },
      ],
    }
  }

  const ops: Op[] = [
    ...a.slice(0, head).map((text): Op => ({ kind: ' ', text })),
    ...lcsOps(midA, midB),
    ...a.slice(a.length - tail).map((text): Op => ({ kind: ' ', text })),
  ]
  return { hunks: toHunks(ops, a.length, context), truncated: false }
}

/** 一列表内的一行（供左右/单栏渲染，行号按侧给） */
export interface DiffRow {
  kind: 'add' | 'del' | 'context'
  /** 旧文件行号（新增行为 undefined） */
  old?: number
  /** 新文件行号（删除行为 undefined） */
  new?: number
  text: string
}

/**
 * hunk → 带双侧行号的行。
 *
 * 与 DSH `FileDiff.tsx:66` 的 `hunkRows` 同语义：上下文行两侧都计数，删除只
 * 走旧侧，新增只走新侧。行号由这里算，**不要**在渲染时累加——那样每帧都
 * 重算，长 hunk 会掉帧。
 */
export function hunkRows(hunk: Hunk): DiffRow[] {
  let oldNo = hunk.oldStart
  let newNo = hunk.newStart
  return hunk.lines.map((line) => {
    const text = line.slice(1)
    switch (line[0]) {
      case '+':
        return { kind: 'add', new: newNo++, text }
      case '-':
        return { kind: 'del', old: oldNo++, text }
      default:
        return { kind: 'context', old: oldNo++, new: newNo++, text }
    }
  })
}

/**
 * 折叠到预算行数：头 `ceil(n/2)` + 尾 `floor(n/2)`。
 *
 * 为什么留头尾而不是只留头：改写的关键信息常在被替换段的**两端**（首句被删、
 * 尾句被加），只留头会正好把「加了什么」藏起来。
 */
export function foldRows(
  rows: DiffRow[],
  maxLines: number,
): { rows: DiffRow[]; hidden: number } {
  if (maxLines <= 0 || rows.length <= maxLines) return { rows, hidden: 0 }
  const headCount = Math.ceil(maxLines / 2)
  const tailCount = maxLines - headCount
  return {
    rows: [...rows.slice(0, headCount), ...rows.slice(rows.length - tailCount)],
    hidden: rows.length - maxLines,
  }
}
