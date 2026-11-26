import {
  applyAutoSplit,
  applyAutoSplitPreservingEdits,
  applyDetectedParties,
  fillSegmentText,
  judgeOutcomeNote,
  mergeJudgeStates,
  resolveParties,
  withEngineDisagreements,
  withJudgeState,
  withPageAnomaly,
  withPageQuality,
} from '../../draft'
import { useReader } from '../../store'
import { ruleSegmentCountOf, segmentBackendNote } from './auto-split-helpers'
import type { AutoSplitResult, ExtractedText } from './auto-split-tracks'

/** 重跑前冲突询问的三种结果。
 *
 * - `keep`：保留律师改过的东西（人工正文搬回新分段）→ `applyAutoSplitPreservingEdits`
 * - `overwrite`：以 AI 结果为准，改动会被覆盖 → `applyAutoSplit`
 * - `cancel`：整次重跑不执行
 */
export type RerunChoice = 'keep' | 'overwrite' | 'cancel'

/** 自动回填到的当事人（空串 = 没识别出来） */
export interface DetectedParties {
  our: string
  their: string
}

/**
 * 把这次识别的结果全部回写草稿，返回顺带识别出的当事人。
 *
 * ⚠️ 调用前必须已确认「打开的还是同一个材料包」（`openId` 未变），否则会把结果写到
 * 另一个包的草稿上。检查留在调用方（run）里：那是编排的一部分，不是回写的一部分。
 */
export async function applyAutoSplitResults(params: {
  results: AutoSplitResult[]
  photoTexts: ExtractedText[]
  officeTexts: ExtractedText[]
  choice: RerunChoice
}): Promise<DetectedParties> {
  const { results, photoTexts, officeTexts, choice } = params
  const current = useReader.getState()
  // 用户在前面的弹窗里选了「保留我的修改」就走保留版：人工正文搬回新分段；
  // 选「用识别结果覆盖」（或本来就没冲突）就走原版，行为与重跑前完全一致。
  const applyFor = choice === 'keep' ? applyAutoSplitPreservingEdits : applyAutoSplit
  // 裁定门禁是**卷级**事实（部署总闸 + 每任务开关），整批只算一次：同一批任务由同一个门禁
  // 决定，真不一致时 mergeJudgeStates 优先保留「要求了没生效」那一条。
  // 折进**已有的**逐份回写里，而不是单独再 update 一次：多一次 update 会改变既有
  // 回写顺序（图片 / Office 两条轨道的用例都取 `update.mock.calls[0]` 断言正文回填）。
  const judgeState = mergeJudgeStates(results.map((item) => item.judgeState))
  for (const result of results) {
    // 页级质量跟着同一次识别结果一起落到草稿上。
    // 引擎分歧同路：它也是「这次识别产出了什么」，且要随草稿持久化（抽屉与双框都要读它）。
    // 裁定总账落在这里是为了**刷新后仍能解释「为什么全是人工」**——律师问这个问题
    // 的时机往往是第二天重开这个包，那时本次 summary 早就不在内存里了。
    // 退化页 / 列数突变页同路（最外层：它们是「这次识别读成什么样」的另一面）。
    // 按 `result.mi` 分槽：一个包多份 PDF 各有自己的页号，整份覆盖会丢页并串源。
    current.update((value) =>
      withPageAnomaly(
        withJudgeState(
          withEngineDisagreements(
            withPageQuality(applyFor(value, result.mi, result.segments, result.jobId), result.pageQuality),
            result.engineDisagreements,
          ),
          judgeState,
        ),
        result.mi,
        result.pageAnomaly,
      ),
    )
  }
  // 跨页不一致是全本的：多个源的结果合并进同一份清单
  current.setInconsistencies(results.flatMap((item) => item.inconsistencies))
  for (const item of photoTexts) {
    current.update((value) => fillSegmentText(value, item.mi, item.md))
  }
  for (const item of officeTexts) {
    current.update((value) => fillSegmentText(value, item.mi, item.md))
  }

  // ── 自动回填当事人 ──
  // 分段完成后正文已在草稿里，当事人信息（借款人/银行）也就在里面。
  // 不回填的话律师得自己翻材料手打一遍右栏那两个框 —— 那正是机器该干的活。
  // 只填空字段（律师已填/改过的不覆盖），识别不出就留空，不猜。
  // 身份判定走 resolveParties：先按标签取候选，再去**客户库**对账
  // （同一叠纸里「申请人」可能同时指委托单位和职工，光看标签必错一半，
  //   见 draft/party-lookup.ts）。客户库查不到才退回纯标签判定。
  // ⚠️ 必须判空：单测里 store 的 draft 可能是 null，直接识别会抛
  //    「Cannot read properties of null」，把整条成功路径带崩（实测挂了 6 个用例）。
  //    现场不会有 null（阅读器打开着才有这个 hook），但测试环境有。
  let detected: DetectedParties = { our: '', their: '' }
  try {
    const draftNow = useReader.getState().draft
    if (draftNow) {
      detected = await resolveParties(draftNow)
      if (detected.our || detected.their) {
        current.update((value) => {
          const { infos, changed } = applyDetectedParties(value.infos, detected)
          return changed ? { ...value, infos } : value
        })
      }
    }
  } catch {
    // 当事人识别是**附加价值**，失败不能拖垮分段主流程 ——
    // 分段成功才是主线，识别不到就留空让律师自己填。
    // 不加这层 try，测试环境里 draft 字段不全就会把整条成功路径带崩
    // （实测挂了 6 个用例，toast 一个都没弹）。
  }
  return detected
}

/**
 * 收尾文案：分了几段、拿到的是哪种质量、图片/Office 各几份、失败几份。
 *
 * 为什么要分类数：混在一起报「完成 N 份」会让律师以为图片也分了段——
 * 图片只回填正文、不产生分段，必须说清楚。
 */
export function summarizeAutoSplitResults(params: {
  results: AutoSplitResult[]
  /** 云端任务失败的 PDF 份数 */
  pdfFailed: number
  photoTexts: ExtractedText[]
  officeTexts: ExtractedText[]
  photoFailed: number
  officeFailed: number
  detected: DetectedParties
}): { message: string; warned: boolean } {
  const { results, pdfFailed, photoTexts, officeTexts, photoFailed, officeFailed, detected } = params
  const count = results.reduce((sum, item) => sum + item.segments.length, 0)
  // 分段后端可观测：律所 AI 失败会降级规则引擎（summary 三态 llm/mixed/rule），
  // 得让用户知道拿到的是哪种质量、有几段是规则兜的要重点复核
  const ruleSegments = results.reduce(
    (sum, item) => sum + ruleSegmentCountOf(item.segmentBackend, item.segments),
    0,
  )
  const backendNote = segmentBackendNote(results.map((item) => item.segmentBackend), ruleSegments)
  const parts: string[] = []
  if (results.length > 0) parts.push(`${results.length} 个 PDF 已分段（${backendNote}，共 ${count} 段）`)
  if (photoTexts.length > 0) parts.push(`${photoTexts.length} 张图片已识别正文`)
  if (officeTexts.length > 0) parts.push(`${officeTexts.length} 份 Office 已转正文`)
  const failedTotal = pdfFailed + photoFailed + officeFailed
  const filled = detected.our || detected.their ? '；已自动填入当事人' : ''
  const tail = failedTotal > 0 ? `；${failedTotal} 份识别失败，可稍后重试` : '；未识别材料仍需人工归类'
  // 页级取字失败必须让收尾提示升级成 warning。
  //
  // 为什么不能只看 `failedTotal`：那数的是「整份任务失败」。而某一页没取到字时，
  // 任务状态是成功的、分段也是成功的——**正文里只是少了几页**，律师看到的是一条
  // 绿色「已完成」。2026-11-25 一份真实卷宗里，某一页整案的核心事实（标的金额 +
  // 生效刑事判决编号）就是这样静默消失的。
  const lostPages = results.reduce((sum, item) => sum + (item.pageQuality?.ocr_failed_pages?.length ?? 0), 0)
  const lost = lostPages > 0 ? `；${lostPages} 页未取到任何文字，正文里没有这几页，请核对原图补录` : ''
  // 分歧裁定：生效时报「裁了几条」，没生效时说清为什么（缺 Key / 总闸没开）。
  // **不升级 warned**：这不是失败，把它染成黄色会让上面那条真警告（页级取字失败）贬值。
  const judgeNote = judgeOutcomeNote(mergeJudgeStates(results.map((item) => item.judgeState)))
  const judged = judgeNote ? `；${judgeNote}` : ''
  // 退化页与列数突变页：正文有了、任务也成功了，但机器读出来的东西本身可疑（见
  // draft/page-anomaly.ts）。**不升级 warned**：这不是失败，染黄会稀释上面那条真警告
  // （页级取字失败）。顺序固定「先退化后列数」，两者都空时一个字都不加（旧任务兼容）。
  const degeneratePages = results.reduce((sum, item) => sum + (item.pageAnomaly?.degenerate_pages?.length ?? 0), 0)
  const degenerateNote =
    degeneratePages > 0 ? `；${degeneratePages} 页云端取字判为退化，已换识别路径重取，请核对原页` : ''
  const columnAnomalyPages = results.reduce(
    (sum, item) => sum + (item.pageAnomaly?.column_anomalies?.length ?? 0),
    0,
  )
  const columnNote = columnAnomalyPages > 0 ? `；${columnAnomalyPages} 页表格列数与邻页不同，数字表头请核对` : ''
  return {
    message: `${parts.join('，')}${filled}${tail}${lost}${judged}${degenerateNote}${columnNote}`,
    warned: failedTotal > 0 || lostPages > 0,
  }
}
