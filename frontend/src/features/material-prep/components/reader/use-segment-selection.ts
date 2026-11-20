import { useRef, useState } from 'react'
import { toast } from 'sonner'

import { downloadUrl } from '@/lib/download'
import { withDownloadTicket } from '@/lib/download-ticket'
import { errMessage } from '@/lib/errors'
import { jobDownloadUrl, segmentMdUrl, segmentPdfUrl } from '../../api'

/**
 * 「已分段产物」下载的**视图状态与动作**（多选 + 置忙），全部是组件本地
 * `useState`，**不进 zustand**。
 *
 * 为什么放本文件而不是 SegmentDownloadBar.tsx：.tsx 里再导出一个 hook 会踩
 * `react-refresh/only-export-components`（eslint 门禁 `--max-warnings 0`），
 * 而工具条与段行必须共用同一份状态，不能让其中一方独占。
 *
 * 为什么不进 store：律师勾几段只是为这一次下载，切走再回来本来就该清空。进了
 * store 就会跟草稿一起持久化，下次打开变成「上次勾的段还亮着、但内容早换了」的
 * 假选中——比少记一个勾更糟。
 *
 * 为什么 key 用 segment 主键（`Segment.splitRef.pk`）而不是列表下标：段会切开 /
 * 合并 / 删页，重新加载后下标整体漂移，用下标当 key 会把「勾过的第 3 行」错绑到
 * 别的材料上；发给后端的 `?ids=` 也正是这一列主键。
 */

/** 一段**已在后端落地**的产物：pk 是后端分段主键，jobId 是产出它的拆分任务 */
export interface DownloadableSegment {
  pk: number
  jobId: string
  name: string
}

export type SegmentFileKind = 'pdf' | 'md'

/** 工具条与段行共用的多选状态（见文件头：读时过滤失效 key，不用 effect 清理） */
export interface SegmentSelection {
  /** 当前有效的选中主键（升序）。列表里已不存在的 key 会被自动滤掉 */
  selected: number[]
  count: number
  has: (pk: number) => boolean
  toggle: (pk: number) => void
  selectAll: () => void
  clear: () => void
  /** 全选态：勾选框的 checked */
  allSelected: boolean
  /** 半选态：勾选框的 indeterminate（有选中但没选满） */
  indeterminate: boolean
}

/** `keys` 是当前列表里**可下载**的段主键（不可下载的段根本不该被勾上） */
export function useSegmentSelection(keys: number[]): SegmentSelection {
  const [raw, setRaw] = useState<number[]>([])
  // 读时过滤而不是 effect 清理：父层每次 render 都会传一个新数组进来（keys 引用
  // 每次都变），用 effect + setState 清理必然每次 render 再触发一轮 setState，
  // 直接打成死循环。读时过滤没有这个环路，代价只是一次小数组 filter。
  const available = new Set(keys)
  const selected = raw.filter((pk) => available.has(pk))
  const allSelected = keys.length > 0 && selected.length === keys.length

  return {
    selected,
    count: selected.length,
    has: (pk) => selected.includes(pk),
    toggle: (pk) =>
      setRaw((cur) => (cur.includes(pk) ? cur.filter((x) => x !== pk) : [...cur, pk].sort((a, b) => a - b))),
    selectAll: () => setRaw([...keys].sort((a, b) => a - b)),
    clear: () => setRaw([]),
    allSelected,
    indeterminate: selected.length > 0 && !allSelected,
  }
}

/** 单个段行的下载视图模型（RailSegRow 只认它，不碰 hook 与 api） */
export interface SegmentRowDownload {
  checked: boolean
  /** 本行正在下载的那一种文件；null = 本行没在下载（别的按钮只是被禁用） */
  busyKind: SegmentFileKind | null
  /** 任一文件在换票/下载中：所有下载按钮都禁用，见下面 `inFlight` 的理由 */
  disabled: boolean
  onToggle: () => void
  onDownload: (kind: SegmentFileKind) => void
}

export interface SegmentDownloads {
  /** 可下载段。空数组 = 这次识别没有后端产物 → 下载 UI 整块不渲染 */
  segments: DownloadableSegment[]
  sel: SegmentSelection
  /** 正在下载的按钮 key（`pdf:12` / `md:12` / `zip:job-1` / `sel:job-1`）；null = 空闲 */
  busy: string | null
  downloadSelected: () => void
  downloadAll: () => void
  rowFor: (pk: number | undefined) => SegmentRowDownload | undefined
}

/**
 * 下载动作本体：换一次性票据 → 触发浏览器下载。
 *
 * ⚠️ 三步一步都不能省（踩过的坑，不是风格偏好）：
 * 1. `segmentPdfUrl / segmentMdUrl / jobDownloadUrl` 只拼**纯路径**；
 * 2. `withDownloadTicket` 换 60 秒一次性票据，`appendTicket` 负责拼 `?ticket=`
 *    或 `&ticket=`——所以 `?ids=12,15` 这种带 query 的 URL 也必须走它，
 *    自己拼 `${url}?ticket=` 会得到两个 `?`；
 * 3. `downloadUrl` 建 `<a>` 点一下（带 `rel=noopener`）。
 *
 * 为什么不能用裸 `<a href>`：JWT 在 localStorage，只有经 ky 发的请求才带
 * `Authorization`；浏览器导航带不上，后端又刻意不收 `?token=<JWT>`（安全审计 M-2）。
 * 裸链接在任何账号下都是 401——「用自己的账号下载自己的材料也失败」那次事故
 * （回归注释见 `inbox/components/InboxView.dom.test.tsx`）。
 */
export function useSegmentDownloads(segments: DownloadableSegment[]): SegmentDownloads {
  const sel = useSegmentSelection(segments.map((seg) => seg.pk))
  const [busy, setBusy] = useState<string | null>(null)
  // ref 是**同步**闸门：setBusy 落到 DOM 之前用户还能再点一次，两次点击会各换一张
  // 票据。票据一次性 + 只活 60 秒，白换的那张会让后一次下载 401——这正是 M-2 事故
  // 里最像「下载功能坏了」的表现。所以闸门必须是 ref，不能只靠 state + disabled。
  const inFlight = useRef<string | null>(null)

  const run = async (key: string, urls: string[]) => {
    if (inFlight.current) return
    inFlight.current = key
    setBusy(key)
    try {
      for (const url of urls) {
        // 每个文件都现换票：票据单次使用，不能拿上一个文件的复用
        const signed = await withDownloadTicket(url)
        // `withDownloadTicket` 换票失败时**自己吞掉异常**、原样返回 url（设计如此）。
        // 所以「没拿到票据」只能靠对比 URL 判断，而这一步必须拦：放过去就是打开裸
        // 链接，律师看到的是一个只写着 `401/403` 的新标签页——正是 M-2 事故里
        // 「用自己的账号下载自己的材料也失败」的观感。票据没到手就报人话。
        if (signed === url) throw new Error('未取到下载票据，登录状态可能已失效，请刷新后重试')
        downloadUrl(signed)
      }
    } catch (e) {
      // 下载走的是浏览器导航，**下载端点自己的 HTTP 状态码进不了 JS**（例如
      // `ids` 非法时后端的 400 只会渲染成一个错误页）。前端能判定的失败就是这里
      // 两条：换票失败 / 换票接口抛错。统一 toast，且**不清选择**——重试一次
      // 就行，不能让律师把几十段重新勾一遍（选择只在用户自己动手时变）。
      toast.error(errMessage(e, '下载失败，请稍后重试'))
    } finally {
      inFlight.current = null
      setBusy(null)
    }
  }

  const downloadOne = (seg: DownloadableSegment, kind: SegmentFileKind) => {
    const url = kind === 'pdf' ? segmentPdfUrl(seg.jobId, seg.pk) : segmentMdUrl(seg.jobId, seg.pk)
    void run(`${kind}:${seg.pk}`, [url])
  }

  const downloadSelected = () => {
    const groups = groupByJob(segments.filter((seg) => sel.has(seg.pk)))
    if (groups.length === 0) return
    void run(
      `sel:${groups.map((g) => g.jobId).join(',')}`,
      groups.map((g) => jobDownloadUrl(g.jobId, g.pks)),
    )
  }

  const downloadAll = () => {
    const groups = groupByJob(segments)
    if (groups.length === 0) return
    void run(
      `zip:${groups.map((g) => g.jobId).join(',')}`,
      groups.map((g) => jobDownloadUrl(g.jobId)),
    )
  }

  const rowFor = (pk: number | undefined): SegmentRowDownload | undefined => {
    if (pk == null) return undefined
    const seg = segments.find((s) => s.pk === pk)
    // 人工切/合并出来的段没有后端产物：不给按钮（点了必然 404）
    if (!seg) return undefined
    return {
      checked: sel.has(pk),
      busyKind: busy === `pdf:${pk}` ? 'pdf' : busy === `md:${pk}` ? 'md' : null,
      disabled: busy !== null,
      onToggle: () => sel.toggle(pk),
      onDownload: (kind) => downloadOne(seg, kind),
    }
  }

  return { segments, sel, busy, downloadSelected, downloadAll, rowFor }
}

/**
 * 按后端任务分组：`ids=` 与整包 zip 都是**按 job** 的，一个包可以有多份 PDF，
 * 每份各有自己的识别任务（`use-auto-split` 就是一个源一个 job）。跨任务的一组
 * 选择没法拼成一个请求，只能一任务一个请求、依次下载。
 */
function groupByJob(list: DownloadableSegment[]): { jobId: string; pks: number[] }[] {
  const groups: { jobId: string; pks: number[] }[] = []
  for (const seg of list) {
    const hit = groups.find((g) => g.jobId === seg.jobId)
    if (hit) hit.pks.push(seg.pk)
    else groups.push({ jobId: seg.jobId, pks: [seg.pk] })
  }
  return groups
}
