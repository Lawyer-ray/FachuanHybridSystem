/**
 * 拖拽期间的「页面级外壳」：禁选中 + 设拖拽光标 + 让 iframe 不吞指针事件，
 * 返回卸载即复位的清理函数。纯 DOM、不依赖 React。
 *
 * 抽出的原因：workbench 分栏、copilot 面板、copilot 侧栏三处都要这套外壳，
 * 手写三份时最容易漏掉两件事——
 *
 * 1. **pointercancel**：touch/笔在系统手势、通知遮罩等情况下只发 pointercancel，
 *    不发 pointerup。漏掉它则拖拽态卡死、`userSelect: 'none'` 永久残留，页面
 *    此后整页选不中文字（这是真实踩过的坑）。
 * 2. **复位成原值而不是空串**：直接写 `''` 会抹掉别人本来就设在这个元素上的
 *    内联样式（例如拖拽先从某个自带 cursor: pointer 的容器开始）。所以先记
 *    原值、结束再还回去。
 *
 * 各 hook 自己的差异（像素 vs 百分比换算、anchor 方向、要不要走 React state）
 * **不在这里**——这里只管指针事件的挂载与页面外壳。
 */

export interface DragChromeOptions {
  /** 拖拽期间给 body 设的光标，默认列宽拖拽的 col-resize */
  cursor?: string
  /**
   * 是否在拖拽期间把 document 里全部 iframe 设成 pointer-events: none。
   * OnlyOffice 预览、PDF 等是 iframe：指针划进去后 move 事件被子文档接走，
   * 父文档收不到，拖动会「断」在半路。不拖跨 iframe 的场景可不开。
   */
  blockIframes?: boolean
}

/**
 * 开始一次拖拽：挂 window 的移动/松开监听，并接管页面外壳样式。
 * 返回的函数做全部复位（幂等，可重复调用）。
 *
 * 同时挂 mouse* 与 pointer*：老调用方（document-recognition 的分屏/弹窗拖拽）
 * 历来用 mouse 事件，新调用方用 pointer 事件（要接 pointercancel）。浏览器里
 * 一次鼠标拖动两种都发，只算谁先到（finish 有幂等闸），不会双车道各跑一遍。
 *
 * @param onMove 指针/鼠标移动（每次调一次，调用方自己直改 DOM）
 * @param onEnd  拖拽结束（up / cancel / 调用方主动取消都走它）；
 *               先复位外壳再调用，调用方此后不必操心 userSelect/光标/iframe
 */
export function beginDrag(
  onMove: (e: MouseEvent & { clientX: number }) => void,
  onEnd: () => void,
  options: DragChromeOptions = {},
): () => void {
  const { cursor = 'col-resize', blockIframes = false } = options

  const prevUserSelect = document.body.style.userSelect
  const prevCursor = document.body.style.cursor
  document.body.style.userSelect = 'none'
  document.body.style.cursor = cursor

  // 只记本次改过的 iframe 及其原值，结束时按各自原值还回去
  const frames = blockIframes ? Array.from(document.querySelectorAll('iframe')) : []
  const prevFrameEvents = frames.map((f) => f.style.pointerEvents)
  frames.forEach((f) => (f.style.pointerEvents = 'none'))

  // 收尾只跑一次：up / cancel / 调用方取消三者里谁先来算谁
  let ended = false
  const finish = () => {
    if (ended) return
    ended = true
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', finish)
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', finish)
    window.removeEventListener('pointercancel', finish)
    document.body.style.userSelect = prevUserSelect
    document.body.style.cursor = prevCursor
    frames.forEach((f, i) => (f.style.pointerEvents = prevFrameEvents[i] ?? ''))
    // 外壳先复位再通知：调用方在 onEnd 里提交宽度/落库，不该再看到 userSelect: none
    onEnd()
  }

  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', finish)
  window.addEventListener('pointermove', onMove)
  // pointercancel：系统手势 / 触摸中断时浏览器只发它，不补 up
  window.addEventListener('pointerup', finish)
  window.addEventListener('pointercancel', finish)

  return finish
}
