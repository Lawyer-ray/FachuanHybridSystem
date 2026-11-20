/**
 * Markdown 表格渲染：右上角「复制表格」+ 长表格滚动。
 *
 * **为什么复制要单独做**：律师拿到一张「本金/利息/天数」的表，真实动作是贴进
 * Excel 或 Word 继续算，而不是截图或手抄。整条回答的「复制 Markdown 源码」
 * 复制出来的是 `| 甲 | 100 |`，粘进 Excel 只会得到一列竖线。
 * 所以复制格式取 **TSV**：制表符分列、换行分行，Excel / Word 表格粘上去
 * 自动分列，不需要任何粘贴向导。
 *
 * **为什么要 `max-h` + 滚动**：模型很爱输出几十行的明细表，不夹住高度会把
 * 600px 宽的气泡撑成一条竖线长廊，后面的结论全被挤出视野。
 *
 * 单元格内的制表符/换行先压成空格：TSV 里它们会直接撕开列，粘过去错位比
 * 复制失败更难发现。
 */

import { memo } from 'react'
import { Check, Copy } from 'lucide-react'

import { useCopyFeedback } from '@/hooks/use-copy-feedback'

/** 从 React 节点树里取纯文本（表格单元格里可能有 strong/code/span） */
function textOf(node: React.ReactNode): string {
  if (node === null || node === undefined || typeof node === 'boolean') return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return (node as React.ReactNode[]).map(textOf).join('')
  if (typeof node === 'object' && 'props' in node) {
    const element = node as React.ReactElement<{ children?: React.ReactNode }>
    // 单元格内的软换行（GFM 渲染成 <br>）当空格：直接跳过会把「甲 乙」粘成「甲乙」
    if (element.type === 'br') return ' '
    return textOf(element.props.children)
  }
  return ''
}

/** 取一行的单元格文本（`th` / `td` 都算；表头的列名必须带上，否则粘进 Excel 没表头） */
function cellsOf(row: React.ReactElement<{ children?: React.ReactNode }>): string[] {
  const cells: string[] = []
  const walk = (node: React.ReactNode) => {
    if (Array.isArray(node)) {
      for (const child of node as React.ReactNode[]) walk(child)
      return
    }
    if (node === null || typeof node !== 'object' || !('props' in node)) return
    const element = node as React.ReactElement<{ children?: React.ReactNode }>
    if (element.type === 'td' || element.type === 'th') {
      // 单元格内的换行/制表符压成单空格：TSV 的列与行只由 \t \n 决定
      cells.push(textOf(element).replace(/\s+/g, ' ').trim())
      return
    }
    walk(element.props.children)
  }
  walk(row.props.children)
  return cells
}

/** 收集所有行（跳过 thead/tbody 这层包裹，只认 tr） */
function collectRows(node: React.ReactNode, rows: string[][]): void {
  if (Array.isArray(node)) {
    for (const child of node as React.ReactNode[]) collectRows(child, rows)
    return
  }
  if (node === null || typeof node !== 'object' || !('props' in node)) return
  const element = node as React.ReactElement<{ children?: React.ReactNode }>
  if (element.type === 'tr') {
    rows.push(cellsOf(element))
    return
  }
  collectRows(element.props.children, rows)
}

/**
 * 把表格子树转成 TSV。
 *
 * 不导出：react-refresh 只允许组件从 `.tsx` 导出，多一个函数导出会让
 * `pnpm lint` 直接挂。所以单测走「点复制按钮 → 断言剪贴板收到什么」，
 * 顺带把按钮接线一起验了。
 */
function tableToTsv(node: React.ReactNode): string {
  const rows: string[][] = []
  collectRows(node, rows)
  // 全空的行（尾行常见）不带：粘进 Excel 会多出一行空行
  return rows
    .filter((cells) => cells.some((cell) => cell.length > 0))
    .map((cells) => cells.join('\t'))
    .join('\n')
}

export const TableBlock = memo(function TableBlock({ children }: { children?: React.ReactNode }) {
  const { copied, copy } = useCopyFeedback()
  const payload = tableToTsv(children)

  return (
    <div className="group relative my-2">
      <div className="max-h-80 overflow-auto rounded-[9px] border border-border">
        {/*
          display/margin 用内联样式压掉 `.copilot-md table` 的 `display:block` +
          `overflow-x:auto`：滚动交给外层容器统一管，表格自己再开一层横向滚动
          会出现「外横内横」两条滚动条，触控板上根本滚不动。
        */}
        <table className="w-full border-collapse text-[12px]" style={{ display: 'table', margin: 0, overflow: 'visible' }}>
          {children}
        </table>
      </div>
      {payload.length > 0 && (
        <button
          type="button"
          // 不用「hover 才显形」：平板 / 触屏上手没有 hover，按钮永远不出来
          // 等于没有复制功能（与 CodeBlock 的复制钮保持一致，常驻可见）
          className="absolute top-1 right-1 flex items-center gap-1 rounded-[5px] border border-border bg-background/90 px-1.5 py-0.5 text-[11px] text-muted-foreground transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          title={copied ? '已复制' : '复制为表格（可直接粘贴到 Excel/Word）'}
          aria-label={copied ? '已复制表格' : '复制表格'}
          onClick={() => void copy(payload)}
        >
          {copied ? <Check className="size-3" aria-hidden /> : <Copy className="size-3" aria-hidden />}
          {copied ? '已复制' : '复制表格'}
        </button>
      )}
    </div>
  )
})
