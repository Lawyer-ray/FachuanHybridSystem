import type {
  AssignInfo,
  CloudEngine,
  CloudSelection,
  DraftState,
  Inconsistency,
  InboxMessageDetail,
  OcrPending,
  PackStatus,
  PageKey,
} from './types'

/**
 * 阅读器会话 store 的形状（状态 + 动作契约）。
 *
 * 从 store.ts 拆出：实现与契约是两个关注点，合在一起已顶过规模软红线。
 * 这里只声明「有什么、什么语义」，怎么改在 store.ts。
 */
export interface ReaderState {
  openId: number | null
  detail: InboxMessageDetail | null
  draft: DraftState | null
  status: 'idle' | 'loading' | 'ready' | 'error'
  error: string
  /** 退出过渡中（阅读器先淡出再卸载） */
  closing: boolean
  /** 正在「标来源」的信息便签序号（-1 = 未在取字） */
  pickInfo: number
  /** 画布缩放倍数（1 = 适应宽度） */
  zoom: number
  /** 并排列数 */
  cols: number
  /** 自动分段时的版面策略（**按包持久化**，权威值在 `draft.recognition`）：
   *  · fast_text（全局默认）—— 电子版 PDF 只抽文本层，快且不计费，但没有坐标与结构
   *  · layout —— 电子版也上云端拿版面块与坐标：更准但更慢更贵（按页计费）
   *  这里是它的会话态当前值：open 时从草稿读回，改动即写回草稿——律师对
   *  「这一包要不要多花钱」的判断是按包做的，换包复位、重开又得重选等于丢掉它。 */
  layoutMode: 'fast_text' | 'layout'
  /**
   * 勾选参与本次识别的云端引擎：空集合 = 自动容灾；1 个 = 锁定；
   * ≥2 个 = 交叉比对（见 components/reader/platform-selection.ts）。
   *
   * 为什么是集合而不是旧的 `'auto' | 'mineru' | 'textin'`：律师要能自己勾选
   * 「同时用哪几个引擎」，而不是靠运维开环境变量。`auto` 是空集合的**后果**，
   * 不是一个可勾的选项——两者并存会让「勾了 auto 又勾 mineru」无解。
   *
   * 同样按包持久化（`draft.recognition.engines`）。新建包默认双引擎（计费默认值，
   * 见 constants.defaultRecognition）；存量草稿没有该键时回到自动容灾，不追溯计费。
   */
  cloudSelection: CloudSelection
  /** 选页模式：平时点页面不做任何事，靠 ⌘/⇧ 或此模式 */
  selMode: boolean
  /** 当前选中的页 */
  selPages: PageKey[]
  /** 区间锚点（扁平序 index） */
  lastAnchor: number
  /** OCR 框选取字：当前待确认的框（律师未确认前由面板接管） */
  ocrPending: OcrPending | null
  /** 归案归属弹窗的开关。仍在 store 里（不退回 ReaderDialogs 局部 state）：换包
   *  /重开时要随 openId 一并复位，且阅读器内其他模块也用得到这个「是否开着」的信号。
   *  Esc 不再靠它：AssignModal 已改成 Radix Dialog，Esc 由 Radix 自己处理。 */
  assignOpen: boolean
  /**
   * 本次识别带回来的全本级统计：跨页不一致清单（`summary.inconsistencies`）。
   *
   * 为什么在 store 而不在草稿：草稿记的是「律师怎么分」，这是「机器读到什么」，
   * 而且同样不落盘。`useAutoSplit` 把 summary 消费掉之后，ReaderBody 还要用它
   * 渲染全局清单，所以留一个会话级的落点。页级质量（page_quality）则落在
   * `draft.pageQuality` 上——它要给左栏/右栏按段算页覆盖关系，跟草稿同生命周期更自然。
   */
  inconsistencies: Inconsistency[]

  open: (id: number) => Promise<void>
  close: () => void
  /** 全局重置（登出时调用）：清空阅读器全部状态并释放缓存，丢弃未落盘的防抖保存 */
  resetAll: () => void
  /**
   * 不可变更新 draft，并保存到后端。
   *
   * `immediate` 跳过 450ms 防抖（打标 / 归案这类「一次点击定终身」的改动，
   * 不能被防抖窗口拖后）。保存只在这里排一次：调用方再用返回的草稿补一次
   * `scheduleSave` 会把计时器换掉，而第一次返回的 Promise 再也不会 settle。
   */
  update: (fn: (d: DraftState) => DraftState, immediate?: boolean) => void
  setPickInfo: (i: number) => void
  /** 删除信息字段（含取字态 pickInfo 下标同步校正） */
  removeInfo: (di: number) => void
  setZoom: (z: number) => void
  /** 页旋转：叠加（delta 可为 90/-90/180）。refs 是页引用（mi + p），见 draft/page-rotation.ts */
  rotatePages: (refs: PageKey[], delta: number) => void
  /** 页旋转：设为绝对角度（右键「旋转 180°」用，不叠加） */
  setPagesRotation: (refs: PageKey[], deg: number) => void
  /** 页旋转：这些页回正 */
  resetPagesRotation: (refs: PageKey[]) => void
  /** 页旋转：全部回正 */
  resetAllRotation: () => void
  /** 切换版面策略（影响下一次「自动分段」是否让电子页上云端）；按包落草稿 */
  setLayoutMode: (m: 'fast_text' | 'layout') => void
  /** 勾选 / 取消一个云端引擎（空集合即自动容灾）；按包落草稿 */
  toggleCloudEngine: (e: CloudEngine) => void
  /** 整组替换引擎选择（设置菜单「一键关闭交叉比对」用）；按包落草稿 */
  setCloudSelection: (sel: CloudSelection) => void
  setCols: (n: number) => void
  toggleSelMode: () => void
  /** ⌘/Ctrl 单击切换 / ⇧ 单击选区间（shift=true 用锚点） */
  toggleSel: (mi: number, p: number, shift: boolean) => void
  clearSel: () => void
  applySel: () => void
  /** 删除页（缺省删当前选中，传 target 删指定页），返回被删页数 */
  deleteSelected: (target?: PageKey[]) => number
  setOcrPending: (p: OcrPending | null) => void
  setAssignOpen: (v: boolean) => void
  /** 本次识别带回的跨页不一致清单（空数组 = 没发现 / 旧任务没有） */
  setInconsistencies: (list: Inconsistency[]) => void
  /** 打标材料包状态（不接归档 / 拆分归类完成等） */
  setStatus: (s: PackStatus) => void
  setAssign: (a: AssignInfo) => void
  renameMatInDraft: (mi: number, n: string) => void
  /** 重命名材料包标题（同步已打开的阅读器标题） */
  renameSubject: (id: number, title: string) => void
  /** 阅读器内追加材料：上传后并回 draft_state（不改已拆内容） */
  appendFiles: (files: File[]) => Promise<void>
}
