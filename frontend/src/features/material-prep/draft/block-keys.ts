import type { MdSuspect } from './md-suspects'
import type { PositionedBlock, Segment } from '../types'

/**
 * 定位块的稳定 key：`<段 id>:<绝对页号>:<同页内序号>`。
 *
 * ## 为什么单独成模块
 *
 * 这条规则被**两个地方**同时依赖，必须逐字一致，否则「点 Markdown 里的一条 →
 * 原页对应框高亮」就对不上：
 *
 * - `Flow.hitsByPage` 用它作为 `hits[].key` 下发给 PageCell 画框；
 * - `SegmentMarkdown` 用它作为列表项的 key，点中时把同一个值传给 Flow 高亮。
 *
 * 放在 `draft/`（纯逻辑区）而不是组件文件里：组件文件只能导出组件
 * （react-refresh 规则），而且这条规则是纯函数，本就该可单测。
 *
 * ## 为什么序号按页重新开始
 *
 * `hitsByPage` 的结构是「每页一个列表」，`list.length` 是**该页内**的序号。
 * 全局连续编号会让第二页的第一条变成 `:1`，两边就对不上了。
 */
export function blockKeyOf(seg: Segment, block: PositionedBlock, index: number): string {
  const blocks = seg.blocks ?? []
  const samePage = blocks.slice(0, index + 1).filter((b) => b.page === block.page).length - 1
  return `${seg.id}:${block.page}:${samePage}`
}

/**
 * 用文本匹配把一条可疑点落到某个 block 上，返回它的 blockKey。
 *
 * ## 为什么靠文本而不是行号
 *
 * `MdSuspect.lineIndex` 是 **markdown 行号**，而面板渲染的是 `blocks`：`seg.md` 是后端
 * 把标题 + 各页块用空行拼起来的，一个表格块在 md 里会展开成几十行，两套编号没有对应
 * 关系。按行号取 block 必然**指错行**。
 *
 * ## 匹配口径
 *
 * 可疑点命中的片段（`match`，缺省退回整行）出现在哪个 block 的 `text` 里。表格块在
 * blocks 里是**一个块**（整张表就是它的 text），所以单元格片段能被它命中。
 *
 * 找不到返回 null —— 调用方据此不渲染「查看原页」，宁少一个入口也不给假跳转。
 */
export function locateKeyOf(seg: Segment, suspect: MdSuspect): string | null {
  const blocks = seg.blocks ?? []
  if (blocks.length === 0) return null
  const needle = (suspect.match || suspect.line).trim()
  if (!needle) return null
  const index = blocks.findIndex((b) => (b.text ?? '').includes(needle))
  if (index < 0) return null
  return blockKeyOf(seg, blocks[index]!, index)
}
