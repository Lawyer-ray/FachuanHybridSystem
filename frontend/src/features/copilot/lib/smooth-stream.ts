/**
 * 流式放字的纯函数与节拍常量（无 React，可单测）。
 *
 * 背景：后端 SSE 的 token 到达节奏忽快忽慢（网络抖动），把每个增量直接丢给
 * markdown 渲染会双重受损 —— 一来一顿一顿，二来每来一个字就要重解析整篇
 * markdown，帧预算被吃光。这里把「可见文本」做成一条追赶全量文本的平滑线：
 *
 * - 每帧只算一次、每 `SMOOTH_STREAM_TICK_FRAMES` 帧才真正放字（约 30Hz），
 *   其余帧跳过，把重解析 markdown 的次数压到一半以下；
 * - 每拍放出的量随积压增长（积压的 1/8），慢速流平滑、快速流不落后；
 * - 积压过大或全文过长时直接到位（平滑的收益抵不过重解析整段的成本）；
 * - 切点必须落在**码点**边界，且不能停在半行表格上。
 *
 * 硬不变量：`nextStreamCut` 返回的切点永远是 `advanceCodePoints` 的结果或
 * 某个行边界，因此由它切出的文本始终是源文本的前缀。
 */

/** 每 N 帧放一次字：约 30Hz。每帧都重解析 markdown 太贵 */
export const SMOOTH_STREAM_TICK_FRAMES = 2

/** 每拍至少放出的码点数（否则慢速流会慢到看不出来） */
export const SMOOTH_STREAM_MIN_STEP = 2

/** 每拍放出积压的 1/8：积压越多放越快，不至于越落越远 */
export const SMOOTH_STREAM_BACKLOG_DIVISOR = 8

/** 积压超过这么多码点直接到位（一次跳几百字以下才值得平滑） */
export const SMOOTH_STREAM_JUMP_BACKLOG = 2000

/** 全文超过这么长不再平滑：长回复每拍重解析整段会掉帧 */
export const SMOOTH_STREAM_MAX_LENGTH = 8000

/** 表格行：行首（允许缩进）后紧跟竖线 */
const TABLE_ROW = /^[ \t]*\|/

/**
 * 从 `from` 往后数 `count` 个码点，返回新下标（UTF-16 单元数）。
 *
 * 用码点而不是 UTF-16 单元切：emoji（`😀` 是 4 个单元）与生僻字（`𠮷` 是
 * 2 个单元）都由代理对组成，按单元切会把它们砍成半个——半个高代理渲染成
 * 替换字符（），且降级不回来，只能等下一拍补全，肉眼就是闪一下。
 *
 * `count <= 0` 原样返回 `from`；超出末尾返回 `text.length`。
 */
export function advanceCodePoints(text: string, from: number, count: number): number {
  if (count <= 0) return Math.min(from, text.length)
  let pos = Math.max(0, from)
  let left = count
  while (left > 0 && pos < text.length) {
    const code = text.charCodeAt(pos)
    // 高代理 0xD800–0xDBFF：若紧跟低代理（0xDC00–0xDFFF）则两者是一个码点
    const isHighSurrogate = code >= 0xd800 && code <= 0xdbff
    const next = pos + 1
    const nextCode = next < text.length ? text.charCodeAt(next) : 0
    const paired = isHighSurrogate && nextCode >= 0xdc00 && nextCode <= 0xdfff
    pos = paired ? pos + 2 : pos + 1
    left -= 1
  }
  return pos
}

/**
 * 下一拍该切到哪（返回 UTF-16 下标，供 `full.slice(0, cut)` 用）。
 *
 * 基础步长 = `max(MIN_STEP, ceil(backlog / BACKLOG_DIVISOR))`，即积压越多
 * 每拍放得越多。切出来之后再看落点所在行：
 *
 * - 落在表格行（行首为 `|`）上时特殊处理。半行 `| a | b` 会被 markdown 当成
 *   段落排版，等分隔行到了才变成表格——逐字放的话每一格都要闪一次段落。
 *   所以：这一行**还没写完**（找不到换行）就退回行首等；**写完了**就一次放
 *   出整行（到换行符之后）。
 * - 其余情况原样返回切点。
 *
 * 返回值恒在 `[from, full.length]`：退到行首时可能等于 `from`（本拍不放字），
 * 但绝不会小于 `from`（否则可见文本会倒退、不再是前缀）。
 */
export function nextStreamCut(full: string, from: number): number {
  const start = Math.max(0, Math.min(from, full.length))
  const backlog = full.length - start
  if (backlog <= 0) return full.length

  const step = Math.max(SMOOTH_STREAM_MIN_STEP, Math.ceil(backlog / SMOOTH_STREAM_BACKLOG_DIVISOR))
  const cut = advanceCodePoints(full, start, step)
  if (cut >= full.length) return full.length

  // cut 落在某个字符中间时 lastIndexOf 仍会命中上一行的换行，行首取其后一位
  const lineStart = full.lastIndexOf('\n', cut - 1) + 1
  const line = full.slice(lineStart)
  if (!TABLE_ROW.test(line)) return cut

  const newlineAt = full.indexOf('\n', lineStart)
  if (newlineAt < 0) return Math.max(start, lineStart) // 行还没写完：停在行首等
  const lineEnd = newlineAt + 1 // 含换行符，整行一次放出
  return cut <= lineEnd ? lineEnd : cut
}
