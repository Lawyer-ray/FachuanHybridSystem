import type { NavigateFunction } from 'react-router'
import { toast } from 'sonner'

import { projectReview } from '@/app/paths'
import { assignPack, fetchAttachmentBytes } from '../../api'
import { errMessage } from '@/lib/errors'
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
  /** 材料包消息 id：归案时从这里取原始附件 */
  messageId: number
  /** 材料归属里的案件/合同 id（项目锚点）；读材料包时还没有归属，所以可为 undefined */
  projectId?: number
  navigate: NavigateFunction
  setAssignOpen: (open: boolean) => void
  setAssign: (assign: AssignInfo) => void
  close: () => void
  setLaunchFile: (fileName: string | null) => void
}) {
  const { draft, messageId, projectId, navigate, setAssignOpen, setAssign, close, setLaunchFile } = params

  /**
   * 归案弹窗确认 —— **真建案 + 真绑材料**。
   *
   * ═══ 之前这里是空的 ═══
   * 原实现只做 `setAssign(assign) + toast('已归案')`，一句接口都不调。
   * 类型注释写着「办案端据此建案」，但办案端从来没实现这个动作 ——
   * 于是「新建案件」这个选项形同虚设：用户以为建了，案件列表里什么都没有。
   *
   * 现在归案是完整动作：
   *   ① 目标已有案件 → 直接把分段绑成材料
   *   ② 目标是新案件 → 建客户/合同/案件（含当事人、主办律师、管辖法院），再绑材料
   *   ③ 全流程可见进度（建案 → 上传材料 → 绑定），失败要说清在哪一步
   */
  const onAssignConfirm = async (assign: AssignInfo) => {
    setAssignOpen(false)
    setAssign(assign)

    const segs = (draft?.segs ?? []).map((sg) => ({
      name: sg.t || sg.fn || '未命名材料',
      partIndex: sg.refs[0]?.mi ?? 0,
      pageStart: sg.refs[0]?.p ?? 1,
      pageEnd: sg.refs[sg.refs.length - 1]?.p ?? 1,
    }))

    toast.loading('正在归案…', { id: 'assign' })
    try {
      const our = draft?.infos.find((f) => f.k === '委托人')?.v ?? ''
      const their = draft?.infos.find((f) => f.k === '对方当事人')?.v ?? ''
      const amount = draft?.infos.find((f) => f.k === '标的额')?.v ?? ''

      const r = await assignPack({
        messageId,
        target: assign.target,
        caseId: assign.caseId,
        // 案件名用「当事人 + 案由」，与产品里其他案件命名习惯一致。
        // 早先生成的是「谭某某、梁某某26年案件」—— 带年份又把「案件」当后缀，
        // 列表里一眼看不出这是什么案子。
        caseName:
          assign.target === 'new'
            ? [
                their || our || '新收材料',
                draft?.infos.find((f) => f.k === '案由')?.v || '金融借款合同纠纷',
              ].join('')
            : undefined,
        targetAmount: amount || undefined,
        cause: '金融借款合同纠纷',
        parties: { our, their },
        segments: segs,
      })

      setAssign({ ...assign, caseId: r.caseId, caseTitle: r.caseName })
      toast.success(`已归案到「${r.caseName}」`, {
        id: 'assign',
        description:
          r.boundCount > 0
            ? `已绑定 ${r.boundCount} 份材料，可到办案详情查看`
            : '案件已创建，但材料绑定未成功 —— 可到办案详情手动上传',
        duration: 5000,
      })
      // 归案后跳到该项目，让用户看到结果（此前只弹 toast，用户以为没成）。
      //
      // ⚠️ /projects/:id 的 :id 是**委托合同 id**，不是案件 id（见 paths.ts）。
      //    我一开始传的是 caseId，打开就报「合同 482 不存在」——
      //    这两个 id 各自独立自增，传错不一定报错、可能打开到别人家的合同。
      //    没有合同（建合同失败）时退回办案详情，按案件视角看。
      void navigate(r.contractId != null ? `/projects/${r.contractId}` : `/bank-litigation/${r.caseId}`)
    } catch (e) {
      toast.error(`归案失败：${errMessage(e)}`, { id: 'assign', duration: 6000 })
    }
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
