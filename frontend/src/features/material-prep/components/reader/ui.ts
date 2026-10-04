/** 原型 .pbtn：阅读器描边按钮，浅色主题下 hover 填充 */
export const PBTN =
  'flex h-[30px] flex-none items-center gap-1 rounded-[7px] border border-border bg-transparent px-[13px] text-[12.5px] font-medium text-secondary-foreground transition-colors hover:bg-secondary hover:text-foreground hover:border-zinc-300'
/** .pbtn 激活态（on） */
export const PBTN_ON = 'bg-secondary text-foreground border-zinc-300'

/** 阅读器放大/缩小边界与步长 */
export const ZOOM_MIN = 0.6
export const ZOOM_MAX = 2.2
export const ZOOM_STEP = 0.1

/** 取字拖框矩形（归一化坐标，相对页宽/页高的 0-1 比例） */
export interface PageRect {
  x: number
  y: number
  w: number
  h: number
}

/** 拖框成立的最小位移阈值：宽或高任一超过该比例才算有效拖框 */
export const MIN_DRAG = 0.018

/** 由按下锚点与当前指针位置（均归一化）求拖框矩形；未超阈值返回 null。
 *  这是「是否构成拖框」的唯一判定，pointerup 据此分派：有矩形走 onOcrBox，
 *  null 走 onPickPage 记页码——阈值内的手抖位移必须归 null，否则两组回调都不触发。 */
export function resolveDragRect(a: { x: number; y: number }, cur: { x: number; y: number }): PageRect | null {
  const rect: PageRect = {
    x: Math.min(a.x, cur.x),
    y: Math.min(a.y, cur.y),
    w: Math.abs(cur.x - a.x),
    h: Math.abs(cur.y - a.y),
  }
  return rect.w > MIN_DRAG || rect.h > MIN_DRAG ? rect : null
}
