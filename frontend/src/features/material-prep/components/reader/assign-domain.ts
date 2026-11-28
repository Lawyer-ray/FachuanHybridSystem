import { fetchAttachmentBytes } from '../../api'
import type { ArchiveToCaseFolderSegment } from '../../api'
import { rotationsForRange } from '../../draft/page-rotation'
import type { BundleMat, DraftState, PageRotMap, Segment } from '../../types'

/**
 * 归案 / 归档时对草稿的**纯域换算**：docx 字节怎么取、当事人字段怎么映射到后端
 * 的 `party_a..party_d`、哪些段要归档且怎么按拆分任务分组、段能不能直接归案。
 *
 * 从 `use-assign-launch.ts` 拆出的原因：那个文件是**动作编排**——弹窗确认后
 * 先建案/绑材料，再 toast 进度、逐组归档、落核对策略、最后跳页，整条链路都在
 * React 与路由里。而本文件的每个函数都不读 store、不碰 toast、不知道当前在哪个页面：
 * 它们只把 `DraftState` 换算成请求入参。混在一起时，「这一段的页引用合法吗」
 * 这种可以单测的口径表被埋在长长的编排流程里。拆开后 `use-assign-launch.ts`
 * 对这些名字保留 re-export，既有 import 路径不变。
 */

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
    // 后端只认 party_a..party_d。越界（第 5 条起）不能再回落成 party_a——
    // 那会把真实的第一当事人（我方委托人）覆盖成标的额/案由之类的无关字段，
    // 建出来的案件把我方当事人记错。所以越界直接丢弃。
    const key = 'abcd'[i]
    if (!key) return acc
    if (info.v?.trim()) acc[`party_${key}`] = info.v.trim()
    return acc
  }, {})
}

/** 一个拆分任务要归档的那些段（端点按 job 分组，一个 job 一次请求） */
export interface ArchiveGroup {
  jobId: string
  segments: ArchiveToCaseFolderSegment[]
}

/**
 * 把带 `splitRef` 的段按拆分任务分组，换成归档端点的入参。
 *
 * - **没有 `splitRef` 的段直接跳过**：人工切/并出来的段、旧草稿、规则引擎分流的段
 *   在后端没有对应的任务产物，指不到 job 就归档不对（同下载入口的取舍）。
 * - `doc_type` / `material_type` 都取段名（`seg.t || seg.fn`）去扩展名：卷宗里的
 *   类型名与文件名都不带扩展名。
 * - `page_start` / `page_end` 取该段的页区间（归案前已校验单源连续，见
 *   `isSingleSourceContiguous`，所以首尾就是最小/最大页）。
 */
export function archiveGroupsOf(
  segs: Segment[],
  pageRot?: PageRotMap,
  mats?: readonly BundleMat[],
): ArchiveGroup[] {
  const groups = new Map<string, ArchiveToCaseFolderSegment[]>()
  for (const sg of segs) {
    const jobId = sg.splitRef?.jobId
    if (!jobId) continue
    const first = sg.refs[0]
    const last = sg.refs[sg.refs.length - 1]
    if (!first || !last) continue
    const name = archiveDocTypeOf(sg)
    const list = groups.get(jobId) ?? []
    // 落进卷宗的那份也必须是律师看到的方向：后端在切页前把角度烧进页对象
    const partIndex = mats?.[first.mi]?.partIndex ?? first.mi
    // 只在该段真有旋转时才带字段：没有旋转的包里请求体保持与改动前逐字相同
    const rotations = pageRot ? rotationsForRange(pageRot, partIndex, first.p, last.p) : ''
    list.push({
      page_start: first.p,
      page_end: last.p,
      doc_type: name,
      material_type: name,
      ...(rotations ? { rotations } : {}),
    })
    groups.set(jobId, list)
  }
  return [...groups].map(([jobId, segments]) => ({ jobId, segments }))
}

/** 归档用的类型名：段类型优先、退回文件名，去掉扩展名；都空时给个兜底名 */
function archiveDocTypeOf(sg: Segment): string {
  const name = (sg.t || sg.fn || '').trim().replace(/\.[A-Za-z0-9]{1,5}$/, '')
  return name || '未命名材料'
}

/**
 * 段的页引用是否「单一素材内的连续页」——这是归案切分的先决条件。
 *
 * 为何必须校验：归案把每段换成一份小 PDF，而 `{partIndex, pageStart, pageEnd}`
 * 这个三字段模型**只能表达一个素材里的一段连续页**。
 *
 * 反例（实测出来的真 bug）：A 素材 1-10 页 + B 素材 1-6 页合并成一段，
 * 归案时取 `refs[0].mi = A`、`refs[last].p = 6` → 切成 **A 的第 1-6 页**，
 * B 那 6 页凭空消失，而且没有任何提示。证据丢了比切得不好严重得多，
 * 所以这里 fail-closed：不合法就拒绝归案，让律师先拆开。
 *
 * 空 refs 也算不合法（没有页可切）。
 */
export function isSingleSourceContiguous(refs: { mi: number; p: number }[]): boolean {
  if (refs.length === 0) return false
  const mi = refs[0]!.mi
  if (!refs.every((ref) => ref.mi === mi)) return false
  // 页号必须严格递增且相连（1,2,3…），不允许重复或跳页
  for (let i = 1; i < refs.length; i++) {
    if (refs[i]!.p !== refs[i - 1]!.p + 1) return false
  }
  return true
}
