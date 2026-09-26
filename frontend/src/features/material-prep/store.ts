import { create } from 'zustand'
import { toast } from 'sonner'
import { appendPackFiles, getPackDetail, saveDraft } from './api'
import { clearPdfDocuments } from '@/lib/pdf'
import {
  applyPageSelection,
  appendMatsToDraft,
  buildInitialDraft,
  flatRefs,
  isSelectionContiguous,
  pageIndexOf,
  removePages,
  resolveMats,
  setPackAssign,
  setPackStatus,
} from './draft'
import type {
  AssignInfo,
  BundleMat,
  DraftState,
  InboxMessageDetail,
  OcrPending,
  PackStatus,
  PageKey,
} from './types'

interface ReaderState {
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
  /** 选页模式：平时点页面不做任何事，靠 ⌘/⇧ 或此模式 */
  selMode: boolean
  /** 当前选中的页 */
  selPages: PageKey[]
  /** 区间锚点（扁平序 index） */
  lastAnchor: number
  /** OCR 框选取字：当前待确认的框（民警未确认前由面板接管） */
  ocrPending: OcrPending | null

  open: (id: number) => Promise<void>
  close: () => void
  /** 不可变更新 draft，并防抖保存到后端 */
  update: (fn: (d: DraftState) => DraftState) => void
  setPickInfo: (i: number) => void
  setZoom: (z: number) => void
  setCols: (n: number) => void
  toggleSelMode: () => void
  /** ⌘/Ctrl 单击切换 / ⇧ 单击选区间（shift=true 用锚点） */
  toggleSel: (mi: number, p: number, shift: boolean) => void
  clearSel: () => void
  applySel: () => void
  /** 删除页（缺省删当前选中，传 target 删指定页），返回被删页数 */
  deleteSelected: (target?: PageKey[]) => number
  setOcrPending: (p: OcrPending | null) => void
  /** 打标材料包状态（不接归档 / 拆分归类完成等） */
  setStatus: (s: PackStatus) => void
  setAssign: (a: AssignInfo) => void
  renameMatInDraft: (mi: number, n: string) => void
  /** 重命名材料包标题（同步已打开的阅读器标题） */
  renameSubject: (id: number, title: string) => void
  /** 阅读器内追加材料：上传后并回 draft_state（不改已拆内容） */
  appendFiles: (files: File[]) => Promise<void>
}

let saveTimer: ReturnType<typeof setTimeout> | null = null
let latestDraft: DraftState | null = null
let latestId = 0
let forceSave = false

function scheduleSave(draft: DraftState, id: number, immediate = false): Promise<void> | null {
  latestDraft = draft
  latestId = id
  if (immediate && saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
  if (saveTimer) return null
  forceSave = immediate
  return new Promise((resolve, reject) => {
    latestDraft = draft
    latestId = id
    saveTimer = setTimeout(() => {
      saveTimer = null
      const d = latestDraft
      const mid = latestId
      if (!d) return resolve()
      saveDraft(mid, d)
        .then(() => resolve())
        .catch((e) => {
          toast.error('拆分草稿保存失败，请检查后端连接')
          reject(e)
        })
    }, forceSave ? 0 : 450)
  })
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
  selMode: false,
  selPages: [],
  lastAnchor: -1,
  ocrPending: null,

  open: async (id) => {
    // 切到新包先释放上一个包的 PDF 文档/worker，避免跨包累积占内存；
    // 此时上一个包的页卡已随 openId 变化卸载，销毁其文档是安全的
    clearPdfDocuments()
    set({
      status: 'loading',
      error: '',
      closing: false,
      openId: id,
      pickInfo: -1,
      zoom: 1,
      cols: 1,
      selMode: false,
      selPages: [],
      lastAnchor: -1,
      ocrPending: null,
    })
    try {
      const detail = await getPackDetail(id)
      let mats: BundleMat[] = []
      try {
        mats = await resolveMats(detail)
      } catch {
        mats = []
      }
      const hasStored = detail.draft_state && detail.draft_state.segs?.length
      const draft = hasStored
        ? detail.draft_state
        : {
            ...buildInitialDraft(detail, mats),
            segs: buildInitialDraft(detail, mats).segs,
          }
      set({ detail, draft, status: 'ready' })
    } catch (e) {
      set({ status: 'error', error: e instanceof Error ? e.message : '打开失败' })
    }
  },

  close: () => {
    const { openId, draft } = get()
    if (openId && draft) forceSave = true
    if (openId && draft) scheduleSave(draft, openId, true)
    // 先淡出，动画完成后再彻底卸载；期间若重新 open，则取消本次退场
    set({ closing: true })
    setTimeout(() => {
      const s = useReader.getState()
      if (!s.closing || !s.openId) return
      // 阅读器已彻底关闭，释放该包的 PDF 文档/worker（关掉后不重开时也得回收，别等下次 open）
      clearPdfDocuments()
      set({
        openId: null,
        detail: null,
        draft: null,
        status: 'idle',
        closing: false,
        pickInfo: -1,
        zoom: 1,
        cols: 1,
        selMode: false,
        selPages: [],
        lastAnchor: -1,
        ocrPending: null,
      })
    }, 240)
  },

  update: (fn) => {
    const cur = get().draft
    if (!cur) return
    const next = fn(cur)
    if (next === cur) return
    set({ draft: next })
    if (get().openId) scheduleSave(next, get().openId as number)
  },

  setPickInfo: (i) => {
    set({ pickInfo: i, selPages: [], ocrPending: null })
    if (i >= 0) set({ selMode: false })
  },
  setZoom: (z) => set({ zoom: z }),
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
    toast('已处理选中页 —— 新段记得归类')
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

  setStatus: (s) => {
    const { openId } = get()
    get().update((d) => setPackStatus(d, s))
    if (openId) {
      const d = get().draft
      if (d) scheduleSave(d, openId, true)
    }
  },

  setAssign: (a) => {
    const { openId } = get()
    get().update((d) => setPackAssign(d, a))
    if (openId) {
      const d = get().draft
      if (d) scheduleSave(d, openId, true)
    }
  },

  renameMatInDraft: (mi, n) => {
    get().update((d) => {
      const name = n.trim()
      if (!name) return d
      const mats = d.mats.map((m, i) =>
        i === mi ? { ...m, customName: name !== m.n ? name : undefined } : m
      )
      const segs = d.segs.map((sg) =>
        sg.fn === (d.mats[mi]?.n || '') && sg.refs.every((r) => r.mi === mi) ? { ...sg, fn: name } : sg
      )
      return { ...d, mats, segs }
    })
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
      const added = await resolveMats(updated)
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
    } catch {
      toast.error('追加材料失败，请检查后端连接')
    }
  },
}))
