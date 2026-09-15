import { create } from 'zustand'
import { toast } from 'sonner'
import { getPackDetail, saveDraft } from './api'
import { buildInitialDraft, resolveMats } from './draft'
import type { BundleMat, DraftState, InboxMessageDetail } from './types'

interface ReaderState {
  openId: number | null
  detail: InboxMessageDetail | null
  draft: DraftState | null
  status: 'idle' | 'loading' | 'ready' | 'error'
  error: string
  /** 正在「标来源」的信息便签序号（-1 = 未在取字） */
  pickInfo: number
  /** 画布缩放倍数（1 = 适应宽度） */
  zoom: number

  open: (id: number) => Promise<void>
  close: () => void
  /** 不可变更新 draft，并防抖保存到后端 */
  update: (fn: (d: DraftState) => DraftState) => void
  setPickInfo: (i: number) => void
  setZoom: (z: number) => void
  renameMatInDraft: (mi: number, n: string) => void
}

let saveTimer: ReturnType<typeof setTimeout> | null = null
let latestDraft: DraftState | null = null
let latestId = 0
let forceSave = false

function scheduleSave(draft: DraftState, id: number, immediate = false): void {
  latestDraft = draft
  latestId = id
  if (immediate && saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
  }
  if (saveTimer) return
  forceSave = immediate
  saveTimer = setTimeout(() => {
    saveTimer = null
    const d = latestDraft
    const mid = latestId
    if (!d) return
    saveDraft(mid, d)
      .catch(() => toast.error('拆分草稿保存失败，请检查后端连接'))
  }, forceSave ? 0 : 450)
}

export const useReader = create<ReaderState>((set, get) => ({
  openId: null,
  detail: null,
  draft: null,
  status: 'idle',
  error: '',
  pickInfo: -1,
  zoom: 1,

  open: async (id) => {
    set({ status: 'loading', error: '', openId: id, pickInfo: -1, zoom: 1 })
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
    if (openId && draft) scheduleSave(draft, openId, true)
    set({ openId: null, detail: null, draft: null, status: 'idle', pickInfo: -1, zoom: 1 })
  },

  update: (fn) => {
    const cur = get().draft
    if (!cur) return
    const next = fn(cur)
    if (next === cur) return
    set({ draft: next })
    if (get().openId) scheduleSave(next, get().openId as number)
  },

  setPickInfo: (i) => set({ pickInfo: i }),
  setZoom: (z) => set({ zoom: z }),

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
}))
