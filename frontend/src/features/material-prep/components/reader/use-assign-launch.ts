import type { NavigateFunction } from 'react-router'
import { toast } from 'sonner'

import { bankLitigation, projectDetail, projectReview } from '@/app/paths'
import { archiveSplitToCaseFolder, assignPack } from '../../api'
import { errMessage } from '@/lib/errors'
import { putPolicy } from '../../doc-verify/api'
import type { AssignInfo, DraftState } from '../../types'
import { rotationsForRange } from '../../draft/page-rotation'
import { archiveGroupsOf, isSingleSourceContiguous } from './assign-domain'

/**
 * 纯域换算（docx 字节 / 当事人字段 / 归档分组 / 单源连续校验）已搬到
 * `assign-domain.ts`。这里 re-export 是为了让既有调用方（`Reader.tsx`、抽屉、
 * 既有测试文件）继续从本文件 import——它们都是「归案这件事」的一部分，
 * 只是从「动作编排」变成了「草稿 → 请求入参」的纯函数。
 */
export { archiveGroupsOf, isSingleSourceContiguous, loadDocxBytes, partiesOf } from './assign-domain'
export type { ArchiveGroup } from './assign-domain'

/**
 * 「同时归档到案件文件夹」的勾选状态（默认勾选）。
 *
 * 为什么由本模块持有而不是跟着 `AssignInfo` 一起传：那个类型在 `types.ts`，
 * 它的归属不归这次改动；而弹窗到 hook 的唯一通道 `onConfirm` 在 `Reader.tsx`
 * 里被包成了单参箭头（`(a) => void launch.onAssignConfirm(a)`），第二参数会被
 * 静默丢掉。所以状态放在这里，`AssignModal` 用下面两个函数读写。
 *
 * 模块级而不是 hook state：这是律师的**偏好**，关掉弹窗再打开不该自己弹回来。
 */
let archiveToCaseFolderOn = true

export function isArchiveToCaseFolderEnabled(): boolean {
  return archiveToCaseFolderOn
}

export function setArchiveToCaseFolderEnabled(enabled: boolean): void {
  archiveToCaseFolderOn = enabled
}

/**
 * 「回传后核对内容」的勾选状态（默认勾选）。
 *
 * 与上面「同时归档到案件文件夹」同构、同理由：这是律师的**偏好**，关掉弹窗再打开
 * 不该自己弹回来；而 `AssignInfo`（`types.ts`）不归这次改动，弹窗到 hook 的唯一通道
 * `onConfirm` 在 `Reader.tsx` 里也被包成了单参箭头。所以状态留在本模块，
 * `AssignModal` 通过下面两个函数读写，归案成功后按它把策略落库。
 */
let verifyAfterReturnOn = true

export function isVerifyAfterReturnEnabled(): boolean {
  return verifyAfterReturnOn
}

export function setVerifyAfterReturnEnabled(enabled: boolean): void {
  verifyAfterReturnOn = enabled
}

/**
 * 新建案件归案成功后，把「回传后核对内容」的策略写到案件上（fire-and-forget）。
 *
 * 只服务新建案件：那时的勾选框没有案件可写，归案返回的 case id 是唯一落库机会。
 * 选中既有案件时勾选框自己已经写过该案策略（见 `doc-verify/PolicyToggle.tsx`）。
 *
 * 为什么是附加动作、失败只记日志不 toast：此刻归案已经写库成功，策略没存上只是
 * 「客户回传时不会自动核对」，不能让律师以为归案失败（重试会建出第二个案子）。
 * 也刻意不弹 warning —— 归档有可见产物（卷宗目录）所以值得提示，而策略是个静默的
 * 开关，失败时再弹一条只会让人去追一个看不到结果的动作。
 *
 * 拿不到可用的 case id 就跳过：宁可这次没存上，也不能猜一个 id 把策略写到别人案子上。
 */
function saveVerifyPolicy(caseId: number): void {
  if (!Number.isInteger(caseId) || caseId <= 0) {
    console.warn('[doc-verify] 归案结果没有可用的 case id，跳过核对策略落库', caseId)
    return
  }
  // `doc_types: []` = 按后端口径「改全部高风险类」（四类文书一起开/关），
  // 与勾选框文案点名的四类一致。
  void putPolicy({ case_id: caseId, enabled: isVerifyAfterReturnEnabled(), doc_types: [] }).catch(
    (e: unknown) => {
      // 只在**没存上**的时候说一句：此刻归案已写库成功，说清「不影响归案」，别让律师重试建出第二个案子。
      // 用 warning 而不是 error：客户回传时不会自动核，但代码默认（高风险四类）仍会核，
      // 后果是「多核了」或「回落默认」，不是「少核了没发现」。
      toast.warning(`归案成功，但「回传后核对内容」的设置没存上（不影响本案）：${errMessage(e, '未知错误')}`)
    },
  )
}

/**
 * 归案 → 发起审查的接线（材料预处理这一侧）。
 *
 * 两件事单独成文件：
 * 1. 归案确认后的流程：写 assign → 找 docx → 开抽屉 / 说清楚为什么不给审；
 * 2. 抽屉回调：上传已由抽屉自己做，这里只负责"审查启动后跳复审台"。
 *
 * `loadDocxBytes` 等不读 React 状态的换算住在 `assign-domain.ts`——它们与
 * 本 hook 的编排流程无关，抽屉的 `loadFile` 回调直接调用；本文件 re-export
 * 它们，所以 `Reader` 的 import 路径与拆分前一致。
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

    // 归案时把每段“换成一份小 PDF”，而界面的段→页范围模型只能表达
    // 「单个素材内的一段连续页」（partIndex + pageStart..pageEnd）。
    //
    // 跨素材合并的段（A1-10 并 B1-6）在这种模型下会**静默丢页**：
    // 只取 refs[0] 的 mi 与 refs[last] 的 p，实际切出来是 A1-6，
    // B 那 6 页消失且无任何提示——实测确认。
    //
    // 所以 rel-to-fail：宁可拦住归案让律师先拆开，也不能默默丢证据。
    const badSegs = (draft?.segs ?? []).filter((sg) => !isSingleSourceContiguous(sg.refs))
    if (badSegs.length > 0) {
      toast.error('有材料跨了多个源文件，无法直接归案', {
        id: 'assign',
        description: `「${badSegs.map((sg) => sg.fn).join('」「')}」跨源合并，请先拆回单源再归案`,
        duration: 8000,
      })
      return
    }

    const mats = draft?.mats ?? []
    const pageRot = draft?.pageRot
    const segs = (draft?.segs ?? []).map((sg) => {
      const first = sg.refs[0]
      const last = sg.refs[sg.refs.length - 1]
      // refs 里的 mi 是**素材下标**；附件 partIndex 才是后端认的标识，也是页旋转
      // 的键。常规包里两者数值相同，追加过附件后就会漂，所以显式换算。
      const partIndex = mats[first?.mi ?? 0]?.partIndex ?? first?.mi ?? 0
      const pageStart = first?.p ?? 1
      const pageEnd = last?.p ?? 1
      // 人工转正：切页在服务端做，角度必须跟着切页请求走，否则案件里那份还是歪的。
      // 空串不进字段——没有旋转的包里请求体保持与改动前逐字相同。
      const rotations = rotationsForRange(pageRot, partIndex, pageStart, pageEnd)
      return {
        name: sg.t || sg.fn || '未命名材料',
        partIndex,
        pageStart,
        pageEnd,
        ...(rotations ? { rotations } : {}),
        // 段标识随材料一起进案件侧：起草 RAG 靠它找回律师核对过的那一段预处理 Markdown
        segmentRef: sg.id,
      }
    })

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
        // 来源素材的页数：归案时用它判断「这一段的页范围是否已覆盖整份」，
        // 覆盖就不必先切页再上传（内容完全一样，省一次往返）。
        sources: draft?.mats ?? [],
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

      // 归档到案件文件夹（默认勾选）：归案已经成功，这一步是**附加**动作。
      // 任何失败只提示、绝不改判「归案失败」——归档挂了律师也得进得去案件看材料。
      // 一个 job 挂了不影响其余 job：循环里逐组 catch。
      if (isArchiveToCaseFolderEnabled()) {
        for (const group of archiveGroupsOf(draft?.segs ?? [], draft?.pageRot, draft?.mats)) {
          try {
            await archiveSplitToCaseFolder(group.jobId, r.caseId, group.segments)
          } catch (e) {
            toast.warning(`归档到案件文件夹失败：${errMessage(e, '未知错误')}`, {
              id: 'archive',
              duration: 6000,
            })
          }
        }
      }

      // 回传后核对内容的策略：勾了=客户回传时自动比正文，没勾=不核。
      // 用归案**返回**的 case id（不是用户选的/猜的），新建案件时只有这里才拿得到。
      //
      // 只在**新建案件**时写：选中既有案件的话，勾选框已经在弹窗里按该案的服务端值
      // 逐次 putPolicy 过了（见 doc-verify/PolicyToggle.tsx），这里再按模块偏好写一遍，
      // 会把律师刚才在弹窗里针对这个案子的选择覆盖成全局偏好。
      if (assign.target !== 'existing') saveVerifyPolicy(r.caseId)

      // 归案后跳到该项目，让用户看到结果（此前只弹 toast，用户以为没成）。
      //
      // ⚠️ /projects/:id 的 :id 是**委托合同 id**，不是案件 id（见 paths.ts）。
      //    我一开始传的是 caseId，打开就报「合同 482 不存在」——
      //    这两个 id 各自独立自增，传错不一定报错、可能打开到别人家的合同。
      //    没有合同（建合同失败）时退回办案详情，按案件视角看。
      // 统一走 paths.ts 的构造函数：`/projects/:id` 的 :id 是**委托合同 id**，
      // 而 `/bank-litigation/:id` 是**案件 id** —— 两套 id 指向不同实体，
      // 手拼字符串时极易传错（就踩过：把 caseId 当 contractId 传，
      // 报「合同 482 不存在」）。用有名字的函数，传错时至少读代码能看出来。
      void navigate(
        r.contractId != null ? projectDetail(r.contractId) : bankLitigation(r.caseId),
      )
    } catch (e) {
      toast.error(`归案失败：${errMessage(e, '未知错误')}`, { id: 'assign', duration: 6000 })
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
