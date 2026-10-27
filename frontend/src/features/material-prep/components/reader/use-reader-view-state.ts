import { useCallback, useEffect, useRef, useState } from 'react'

import { useReader } from '../../store'

/**
 * 阅读器的本地视图态：侧栏抽屉、元信息栏、源文件重命名目标、追加材料 input、
 * 「归案 → 发起审查」选中的文件。
 *
 * 抽出来的理由：这 6 个 state 有两个共同的时机（换包复位、框选取字让开抽屉）和
 * 一条共同规则（两侧栏互斥），原来散在 Reader 的 396 行里，看布局看不出哪条
 * 是互斥、哪条是复位。
 *
 * 不放进 store：这些是"这个视图此刻怎么摆"的瞬时态，不该跟着材料草稿持久化。
 */
export function useReaderViewState() {
  // 待重命名的源文件（左栏重命名入口打开），null = 关闭
  const [renameMat, setRenameMat] = useState<{ mi: number; initial: string } | null>(null)
  const [renaming, setRenaming] = useState(false)
  const [railOpen, setRailOpen] = useState(false)
  const [metaOpen, setMetaOpen] = useState(false)
  const addInputRef = useRef<HTMLInputElement>(null)
  // 通过回调 setter 交给调用方做 ref={...}：React Compiler 的 ref 规则不允许在
  // 渲染期把 ref 对象本身传出去/读 .current，回调形式是官方认可的写法
  const [addInput, setAddInput] = useState<HTMLInputElement | null>(null)
  const setAddInputRef = useCallback((el: HTMLInputElement | null) => {
    addInputRef.current = el
    setAddInput(el)
  }, [])
  // 归案之后的下一个动作是「发起审查」——不接这一步，归案就是条死路：
  // draft_state 里只多了个 assign 字段，律师回到卡片墙不知道下一步做什么。
  const [launchFile, setLaunchFile] = useState<string | null>(null)

  const openId = useReader((s) => s.openId)
  const setAssignOpen = useReader((s) => s.setAssignOpen)
  const pickInfo = useReader((s) => s.pickInfo)

  // 换包复位：侧栏、重命名目标、归案弹窗、待发起审查的文件都作废。
  useEffect(() => {
    setRailOpen(false)
    setMetaOpen(false)
    setRenameMat(null)
    setAssignOpen(false)
    setLaunchFile(null)
  }, [openId, setAssignOpen])

  // 框选取字必须看得见页面 —— 抽屉让开
  useEffect(() => {
    if (pickInfo >= 0) {
      setRailOpen(false)
      setMetaOpen(false)
    }
  }, [pickInfo])

  /** 开左栏必收右栏（两侧栏在窄屏下都是覆盖抽屉，同开必然互相压住） */
  const toggleRail = useCallback(() => {
    setRailOpen((v) => !v)
    setMetaOpen(false)
  }, [])
  const toggleMeta = useCallback(() => {
    setMetaOpen((v) => !v)
    setRailOpen(false)
  }, [])
  /**
   * 左栏「重命名源文件」入口：打开重命名弹窗并带初始名。
   *
   * 初始名是用户改过的名字优先，否则原始文件名——`customName` 是草稿里持久化的
   * 自定义名，`n` 是上传时的原始名。
   */
  const startRenameMat = useCallback(
    (mi: number) => {
      const m = useReader.getState().draft?.mats[mi]
      if (!m) return
      setRenameMat({ mi, initial: m.customName || m.n })
    },
    [],
  )

  /** 多列时收起侧栏，让页面更宽敞 */
  const collapsePanels = useCallback(() => {
    setRailOpen(false)
    setMetaOpen(false)
  }, [])

  return {
    renameMat,
    setRenameMat,
    renaming,
    setRenaming,
    railOpen,
    metaOpen,
    toggleRail,
    toggleMeta,
    collapsePanels,
    startRenameMat,
    setAddInputRef,
    addInput,
    launchFile,
    setLaunchFile,
  }
}
