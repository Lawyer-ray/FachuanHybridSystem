import type { NavigateFunction } from 'react-router'
import { toast } from 'sonner'

import { projectReview } from '@/app/paths'
import { fetchAttachmentBytes } from '../../api'
import type { AssignInfo, DraftState } from '../../types'

/**
 * 归案 → 发起审查的接线（材料预处理这一侧）。
 *
 * 两件事单独成文件：
 * 1. 归案确认后的流程：写 assign → 找 docx → 开抽屉 / 说清楚为什么不给审；
 * 2. 抽屉回调：上传已由抽屉自己做，这里只负责"审查启动后跳复审台"。
 *
 * `loadDocxBytes` 是模块级函数（不是 hook 内部）——它不读任何 React 状态，
 * 抽屉的 `loadFile` 回调直接调用它。必须跟本 hook 一起搬，否则 Reader 还得
 * import fetchAttachmentBytes。
 */
export function useAssignLaunch(params: {
  /** 草稿可能还没就绪（刚上传、后端尚未建出草稿）——调用方会早返回 loading，
   *  但本 hook 的字段推导仍会执行，所以这里允许 null 并在使用处守卫。 */
  draft: DraftState | null
  /** 材料归属里的案件/合同 id（项目锚点）；读材料包时还没有归属，所以可为 undefined */
  projectId?: number
  navigate: NavigateFunction
  setAssignOpen: (open: boolean) => void
  setAssign: (assign: AssignInfo) => void
  close: () => void
  setLaunchFile: (fileName: string | null) => void
}) {
  const { draft, projectId, navigate, setAssignOpen, setAssign, close, setLaunchFile } = params

  /** 归案弹窗确认：落 assign，然后直接进发起审查（否则归案是条死路） */
  const onAssignConfirm = (assign: AssignInfo) => {
    setAssignOpen(false)
    setAssign(assign)
    toast('已归案')
    // 归案后直接进发起审查：docx 才能审，其余格式在审查页里说清楚
    const target = draft?.mats.find((m) => /\.docx$/i.test(m.n))
    if (target) {
      setLaunchFile(target.n)
      return
    }
    toast.info('材料包里没有 .docx：审查流水线只处理 Word 文档', {
      description: 'PDF / 图片请先转成 docx，或到合同文件夹里对 docx 发起审查',
    })
    close()
  }

  /** 抽屉里流水线已触发：关抽屉 → 关阅读器 → 有项目锚点就跳复审台 */
  const onStarted = (taskId: string) => {
    setLaunchFile(null)
    close()
    if (projectId) {
      toast.success('审查已启动', { description: '正在打开复审工作台…' })
      void navigate(projectReview(projectId, taskId))
      return
    }
    toast.success('审查已启动', {
      description: '材料尚未归属到具体项目，请到项目下查看复审工作台',
    })
  }

  const onCloseDrawer = () => {
    setLaunchFile(null)
    close()
  }

  return { onAssignConfirm, onStarted, onCloseDrawer }
}

/** 从材料包里取 docx 字节（审查流水线只吃 docx，需带鉴权）。 */
export async function loadDocxBytes(
  messageId: number,
  draft: DraftState,
  fileName: string,
): Promise<ArrayBuffer> {
  const mat = draft.mats.find((m) => m.n === fileName)
  if (!mat) throw new Error('材料包里找不到该文件')
  return fetchAttachmentBytes(messageId, mat.partIndex)
}

/** 已归到的当事人（甲乙丙丁）→ 抽屉的 party_* 兜底选项 */
export function partiesOf(draft: DraftState): Record<string, string> {
  return draft.infos.reduce<Record<string, string>>((acc, info, i) => {
    if (info.v?.trim()) acc[`party_${'abcd'[i] ?? 'a'}`] = info.v.trim()
    return acc
  }, {})
}
