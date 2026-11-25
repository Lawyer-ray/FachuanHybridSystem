import { create } from 'zustand'
import { toast } from 'sonner'
import { appendPackFiles, getPackDetail, clearBytesCache } from './api'
import { discardPendingSave, scheduleSave } from './draft-persistence'
import { clearPdfDocuments } from '@/lib/pdf'
import { errMessage } from '@/lib/errors'
import { READER_CLOSE_MS } from './constants'
import { toggleCloudEngine, normalizeCloudSelection } from './types'
import {
  applyPageSelection,
  appendMatsToDraft,
  buildInitialDraft,
  ensureSegIds,
  flatRefs,
  isEmptyDraft,
  isSelectionContiguous,
  pageIndexOf,
  resetRefsRotation,
  rotateRefs,
  removeInfoField,
  removePages,
  renameMat,
  resolveMats,
  setPackAssign,
  setPackStatus,
  withDefaultNames,
} from './draft'
import type { PageRefKey } from './draft/page-rotation'
import type { BundleMat, DraftState, PageKey } from './types'
import type { ReaderState } from './reader-state'


/**
 * 页引用（`mi` + 页号）→ 旋转表的键（`partIndex` + 页号）。
 *
 * 两套坐标必须在这里换算一次：`refs.mi` 是**素材下标**（数组位置，追加附件会漂），
 * 而旋转表按**附件 partIndex** 存（稳定，且服务端认这个标识）。放模块级纯函数而不是
 * 各组件各写一份——换算错的表现是「转了这一页、歪的是另一页」，很难肉眼发现。
 */
function pageRotRefsOf(draft: DraftState | null, refs: readonly PageKey[]): PageRefKey[] {
  if (!draft) return []
  return refs.flatMap((ref) => {
    const mat = draft.mats[ref.mi]
    // 素材不在了（删附件/旧草稿）就跳过：宁可这次不转，也不要往错的 partIndex 上写
    return mat ? [{ partIndex: mat.partIndex, page: ref.p }] : []
  })
}

/** 阅读器会话交互态的清零并叠加差异字段（open 换包 / close 卸载 / resetAll
 *  三处共用同一组重置字段；差异项——openId/detail/draft/status/error——由调用方给）。 */
function resetState(over: Partial<ReaderState>): Partial<ReaderState> {
  return {
    closing: false,
    pickInfo: -1,
    zoom: 1,
    cols: 1,
    // 换包/关闭先复位成不计费的默认值；open 拿到草稿后再按包覆盖（recognitionOf）。
    // 成本选择不跨材料包继承——双引擎意味着同一份 PDF 付两次云端费用。
    layoutMode: 'fast_text',
    cloudSelection: [],
    selMode: false,
    selPages: [],
    lastAnchor: -1,
    ocrPending: null,
    assignOpen: false,
    // 换包 / 关闭一律清空：上一包的不一致清单套到新包上就是彻头彻尾的假清单
    inconsistencies: [],
    ...over,
  }
}

/**
 * 草稿里的按包识别选择 → 会话态。
 *
 * 存量草稿没有 recognition 键时回到「仅文本层 + 自动容灾」，**不**套用新建包的
 * 双引擎默认：老包突然开始双倍计费是用户没同意过的变更。
 */
function recognitionOf(d: DraftState): Pick<ReaderState, 'layoutMode' | 'cloudSelection'> {
  return {
    layoutMode: d.recognition?.layoutMode ?? 'fast_text',
    cloudSelection: normalizeCloudSelection(d.recognition?.engines ?? []),
  }
}

export const useReader = create<ReaderState>((set, get) => ({
  openId: null,
  detail: null,
  draft: null,
  status: 'idle',
  error: '',
  closing: false,
  pickInfo: -1,
  zoom: 1,
  cols: 1,
  layoutMode: 'fast_text',
  cloudSelection: [],
  selMode: false,
  selPages: [],
  lastAnchor: -1,
  ocrPending: null,
  assignOpen: false,
  inconsistencies: [],

  open: async (id) => {
    // 切到新包先释放上一个包的 PDF 文档/worker，避免跨包累积占内存；
    // 此时上一个包的页卡已随 openId 变化卸载，销毁其文档是安全的
    clearPdfDocuments()
    clearBytesCache()
    set(resetState({ status: 'loading', error: '', openId: id }))
    try {
      const detail = await getPackDetail(id)
      // 快速连点两个包时，慢的那个响应后到会张冠李戴——响应回来时若已切到别的包就丢弃
      if (get().openId !== id) return
      let mats: BundleMat[] = []
      try {
        mats = await resolveMats(detail)
        if (get().openId !== id) return
      } catch {
        mats = []
        toast.error('附件解析失败，已按空材料打开 —— 可尝试重新打开该包')
      }
      const ds = detail.draft_state
      // 未拆过的包 draft_state 是空占位（见 draft/state.ts 的 isEmptyDraft）；
      // 已存草稿但段被删空的仍按「未拆」重建初始草稿，避免打开一个空阅读器
      const hasStored = !isEmptyDraft(ds) && ds.segs.length > 0
      // 存量草稿的段可能没有 id（id 是后加的字段），读取时兜底补齐；
      // 仍用默认名的段按现行规则刷新（源名-P起始页）——老草稿里切开留下的余段
      // 都叫源文件名，打开就是几份同名；用户改过的名不动
      const draft = hasStored ? withDefaultNames(ensureSegIds(ds)) : buildInitialDraft(detail, mats)
      set({ detail, draft, status: 'ready', ...recognitionOf(draft) })
    } catch (e) {
      if (get().openId !== id) return
      set({ status: 'error', error: errMessage(e, '打开失败') })
    }
  },

  close: () => {
    const { openId, draft } = get()
    if (openId && draft) scheduleSave(draft, openId, true)?.catch(() => {})
    // 先淡出，动画完成后再彻底卸载；期间若重新 open，则取消本次退场
    set({ closing: true })
    setTimeout(() => {
      const s = useReader.getState()
      if (!s.closing || !s.openId) return
      // 阅读器已彻底关闭，释放该包的 PDF 文档/worker（关掉后不重开时也得回收，别等下次 open）
      clearPdfDocuments()
      clearBytesCache()
      set(resetState({ openId: null, detail: null, draft: null, status: 'idle' }))
    }, READER_CLOSE_MS)
  },

  resetAll: () => {
    // 取消未落盘的防抖保存：登出后 token 已清，保存只会报错；草稿按丢弃处理
    discardPendingSave()
    clearPdfDocuments()
    clearBytesCache()
    set(resetState({ openId: null, detail: null, draft: null, status: 'idle', error: '' }))
  },

  update: (fn, immediate = false) => {
    const cur = get().draft
    if (!cur) return
    const next = fn(cur)
    if (next === cur) return
    set({ draft: next })
    const { openId } = get()
    if (openId) scheduleSave(next, openId, immediate)?.catch(() => {})
  },

  setPickInfo: (i) => {
    set({ pickInfo: i, selPages: [], ocrPending: null })
    if (i >= 0) set({ selMode: false })
  },
  /** 删除信息字段：取字态（pickInfo≥0）下同步校正下标——删在取字字段之前 →
   *  infos 前移一位（pickInfo-1）；删的正是取字字段 → 退出取字态。
   *  与 MetaPanel armDel 记字段名防漂移是同型的下标漂移问题。 */
  removeInfo: (di) => {
    const { pickInfo } = get()
    get().update((d) => removeInfoField(d, di))
    if (pickInfo < 0) return
    if (di < pickInfo) set({ pickInfo: pickInfo - 1 })
    else if (di === pickInfo) set({ pickInfo: -1, selPages: [], ocrPending: null })
  },
  // ── 页旋转（人工转正） ────────────────────────────────────────
  //
  // 只改草稿里的 `pageRot`，**不碰源 PDF**：真正的方向在归案切页 / 卷宗归档 /
  // 下载时由服务端烧进 /Rotate（见 draft/page-rotation.ts 的模块文档）。这样
  // 「转一下」是零成本的本地编辑，可以随意反复调，也不会让 OCR/拆分缓存失效。
  rotatePages: (refs, delta) => {
    const keys = pageRotRefsOf(get().draft, refs)
    if (!keys.length) return
    get().update((d) => ({ ...d, pageRot: rotateRefs(d.pageRot, keys, delta) }))
  },
  resetPagesRotation: (refs) => {
    const keys = pageRotRefsOf(get().draft, refs)
    if (!keys.length) return
    get().update((d) => ({ ...d, pageRot: resetRefsRotation(d.pageRot, keys) }))
  },
  setZoom: (z) => set({ zoom: z }),
  setLayoutMode: (m) => {
    set({ layoutMode: m })
    get().update((d) => ({ ...d, recognition: { ...d.recognition, layoutMode: m } }))
  },
  toggleCloudEngine: (e) => {
    const next = toggleCloudEngine(get().cloudSelection, e)
    set({ cloudSelection: next })
    get().update((d) => ({ ...d, recognition: { ...d.recognition, engines: next } }))
  },
  setCloudSelection: (sel) => {
    const next = normalizeCloudSelection(sel)
    set({ cloudSelection: next })
    get().update((d) => ({ ...d, recognition: { ...d.recognition, engines: next } }))
  },
  setCols: (n) => set({ cols: n }),
  toggleSelMode: () => {
    const next = !get().selMode
    set({ selMode: next, selPages: next ? get().selPages : [], pickInfo: next ? -1 : get().pickInfo })
  },

  toggleSel: (mi, p, shift) => {
    const { draft } = get()
    if (!draft) return
    const idx = pageIndexOf(draft, mi, p)
    if (shift && get().lastAnchor >= 0) {
      const flat = flatRefs(draft)
      const lo = Math.max(0, Math.min(get().lastAnchor, idx))
      const hi = Math.min(flat.length - 1, Math.max(get().lastAnchor, idx))
      set({ selPages: flat.slice(lo, hi + 1).map((f) => ({ mi: f.ref.mi, p: f.ref.p })) })
      return
    }
    set({ lastAnchor: idx })
    const cur = get().selPages
    const hit = cur.find((x) => x.mi === mi && x.p === p)
    set({
      selPages: hit
        ? cur.filter((x) => !(x.mi === mi && x.p === p))
        : [...cur, { mi, p }],
    })
  },

  clearSel: () => set({ selPages: [], lastAnchor: -1 }),

  applySel: () => {
    const { draft, selPages } = get()
    if (!draft || !selPages.length) return
    if (!isSelectionContiguous(draft, selPages)) {
      toast('请选顺序上连续的页')
      return
    }
    get().update((d) => applyPageSelection(d, selPages))
    get().clearSel()
    toast('新的一份已就位，记得给它起个名')
  },

  /** 删除页：缺省删当前选中；传 target 则删指定页（右键未选中页时用）。 */
  deleteSelected: (target?: PageKey[]) => {
    const { draft, selPages } = get()
    const picked = target ?? selPages
    if (!draft || !picked.length) return 0
    const n = picked.length
    get().update((d) => removePages(d, picked))
    get().clearSel()
    return n
  },

  setOcrPending: (p) => set({ ocrPending: p }),

  setAssignOpen: (v) => set({ assignOpen: v }),

  setInconsistencies: (list) => set({ inconsistencies: list }),

  // 打标与归案立即落盘（走 update 的 immediate 参数）：曾被写成「update 排一次
  // 防抖保存 + 这里再 scheduleSave(…, true) 一次」，第二次只是把计时器换掉，
  // 第一次返回的 Promise 再也不 settle。
  setStatus: (s) => {
    get().update((d) => setPackStatus(d, s), true)
  },

  setAssign: (a) => {
    get().update((d) => setPackAssign(d, a), true)
  },

  renameMatInDraft: (mi, n) => {
    get().update((d) => renameMat(d, mi, n))
  },

  renameSubject: (id, title) => {
    const st = get()
    if (st.detail && st.detail.id === id && st.detail.subject !== title) {
      set({ detail: { ...st.detail, subject: title } })
    }
  },

  appendFiles: async (files) => {
    const { openId, draft } = get()
    if (!openId || !draft) return
    if (!files.length) return
    try {
      const updated = await appendPackFiles(openId, files)
      // 上传期间可能关 A 开 B（或 close 置空 openId）：续体回来时若已不是
      // 当时的包就静默丢弃（与 open() 的失配检查一致），否则会把 A 的
      // detail 覆盖到 B、把 A 的材料追加进 B 的草稿并经防抖保存落盘
      if (get().openId !== openId) return
      const added = await resolveMats(updated)
      if (get().openId !== openId) return
      const known = new Set(draft.mats.map((m) => m.partIndex))
      const fresh = added.filter((m) => !known.has(m.partIndex))
      if (!fresh.length) {
        toast('没有新增材料')
        set({ detail: updated })
        return
      }
      set({ detail: updated })
      get().update((d) => appendMatsToDraft(d, fresh))
      toast.success(`已追加 ${fresh.length} 份材料`)
    } catch (e) {
      // 同 DeskPage.handleFiles：后端的「附件过大 / 格式不支持」文案必须透出，
      // 吞成「检查后端连接」会让可自行处理的上传失败看起来像服务故障。
      toast.error(errMessage(e, '追加材料失败，请重试'))
    }
  },
}))
