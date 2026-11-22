import { useState } from 'react'

/**
 * 「已分段产物」的**多选状态**（工具条与段行共用一份），组件本地 `useState`，
 * **不进 zustand**。
 *
 * 为什么是 .ts 而不是 .tsx：.tsx 里再导出一个 hook 会踩
 * `react-refresh/only-export-components`（eslint 门禁 `--max-warnings 0`）。
 *
 * 为什么不进 store：律师勾几段只是为这一次下载，切走再回来本来就该清空。进了
 * store 就会跟草稿一起持久化，下次打开变成「上次勾的段还亮着、但内容早换了」的
 * 假选中——比少记一个勾更糟。
 *
 * 为什么 key 用 segment 主键（`Segment.splitRef.pk`）而不是列表下标：段会切开 /
 * 合并 / 删页，重新加载后下标整体漂移，用下标当 key 会把「勾过的第 3 行」错绑到
 * 别的材料上；发给后端的 `?ids=` 也正是这一列主键。
 *
 * 下载动作（换票 / 拼 URL / 分组）在 `use-segment-downloads.ts`，它消费本文件的
 * `useSegmentSelection`。
 */

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
