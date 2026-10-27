import { useReader } from '../../store'

/**
 * Reader 用到的 store 字段/动作，一次取齐。
 *
 * **一律走按字段 selector**（`useReader((s) => s.x)`），不取整份快照：整份快照
 * （`useReader.getState()` 或 `useReader()`）会让 store 任一字段变化都触发 Reader
 * 整树重渲染，而且拿到的是"这一帧"的副本——以前这里就有一次 `getState()` 的
 * 孤立写法，靠 zustand action 引用恒定才侥幸成立，读代码的人看不出分别。
 *
 * action 引用在 zustand 里恒不变，所以这些 selector 订阅不会引起额外重渲染，
 * 直接内联箭头也不必 memo（返回的仍是同一个函数引用）。
 */
export function useReaderStoreFields() {
  return {
    // 数据
    openId: useReader((s) => s.openId),
    detail: useReader((s) => s.detail),
    draft: useReader((s) => s.draft),
    status: useReader((s) => s.status),
    closing: useReader((s) => s.closing),
    pickInfo: useReader((s) => s.pickInfo),
    zoom: useReader((s) => s.zoom),
    cols: useReader((s) => s.cols),
    selMode: useReader((s) => s.selMode),
    selPages: useReader((s) => s.selPages),
    ocrPending: useReader((s) => s.ocrPending),
    assignOpen: useReader((s) => s.assignOpen),
    error: useReader((s) => s.error),

    // 动作（稳定引用）
    update: useReader((s) => s.update),
    removeInfo: useReader((s) => s.removeInfo),
    close: useReader((s) => s.close),
    setAssignOpen: useReader((s) => s.setAssignOpen),
    setAssign: useReader((s) => s.setAssign),
    setPickInfo: useReader((s) => s.setPickInfo),
    setCols: useReader((s) => s.setCols),
    setZoom: useReader((s) => s.setZoom),
    setOcrPending: useReader((s) => s.setOcrPending),
    clearSel: useReader((s) => s.clearSel),
    toggleSelMode: useReader((s) => s.toggleSelMode),
    applySel: useReader((s) => s.applySel),
    appendFiles: useReader((s) => s.appendFiles),
    // 内联箭头会让 Flow 的 cellPropsOf 依赖每次 render 变化，PageCell memo 全失效
    onToggleSel: useReader((s) => s.toggleSel),
  }
}
