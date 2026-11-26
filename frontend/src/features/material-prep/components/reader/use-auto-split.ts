import { useState } from 'react'
import { toast } from 'sonner'
import { detectAutoSplitConflicts, type AutoSplitConflict } from '../../draft'
import type { DraftState, PdfSplitSegmentSuggestion } from '../../types'
import { useReader } from '../../store'
import { usePollSession } from '@/hooks/use-poll-session'
import { applyAutoSplitResults, summarizeAutoSplitResults, type RerunChoice } from './auto-split-apply'
import { runOfficeTrack, runPdfTrack, runPhotoTrack } from './auto-split-tracks'
import { autoSplitTargetsOf } from './auto-split-targets'
import { beginOwnedAutoSplit, clearAutoSplitTask, reportAutoSplitProgress } from './use-auto-split-task'
import { resolveBackendRequest } from './platform-selection'

/**
 * 自动分段编排：提交云端拆分任务 → 轮询到终态 → 回写草稿。
 *
 * 只做编排。「现在有没有任务在跑、跑到哪、要不要接管别人发起的任务」在
 * use-auto-split-task.ts：那是另一份生命周期（不随 openId 复位、工具条与底部
 * 浮条都要读），混进来会把本文件顶过规模红线，也让两条入口的边界看不清。
 *
 * 重入与卸载走 usePollSession 的会话号守卫：run() 一开始就签发新会话，
 * 旧循环在下一个自检点退出。以前的 cancelled ref 只在卸载置位——连点两次
 * 会跑起两个循环，两个云端任务、两条 setProgress 流互相覆盖，回写顺序不定。
 * 工具条按钮的 disabled 只挡得住「已渲染成 running」之后的点击，
 * 挡不住同一帧/双击的这种重入。
 */
export function useAutoSplit() {
  const [running, setRunning] = useState(false)
  const [progress, setProgress] = useState('')
  // 重跑前的冲突询问：非 null 时 ReaderDialogs 弹 RerunConfirmDialog，等用户选。
  // resolve 一直挂在 state 里直到用户点按钮；取消时 resolve('cancel')，整次 run 直接退出。
  const [pendingConflicts, setPendingConflicts] = useState<{
    conflicts: AutoSplitConflict[]
    draft: DraftState
    resolve: (choice: RerunChoice) => void
  } | null>(null)
  const pollSession = usePollSession()

  /**
   * 拿这次重跑的用户选择。
   *
   * 冲突**在提交云端任务之前**算：算得到的 `edited` 只依赖当前草稿，跟这次任务会返回
   * 什么建议无关（`detectAutoSplitConflicts` 只用 suggestions 判空）。放在提交前问，
   * 律师取消时一个钱不花、一个任务不建。
   *
   * 这里用一条临时占位建议骗过那层判空：我们不需要真建议，只需要「有冲突吗」这个答案。
   * 真建议此刻还没拿到——它正是提交后才会有的东西。
   */
  const askRerunChoice = (draftNow: DraftState, targets: { mi: number }[]): Promise<RerunChoice> => {
    const conflicts = targets
      .map(({ mi }) => detectAutoSplitConflicts(draftNow, mi, [{ page_start: 1, page_end: 1 } as PdfSplitSegmentSuggestion]))
      .filter((c): c is AutoSplitConflict => c !== null)
    // 没人改过：不必打扰，直接按「覆盖」走（与重跑前的旧行为完全一致）
    if (conflicts.length === 0) return Promise.resolve('overwrite')
    return new Promise((resolve) => setPendingConflicts({ conflicts, draft: draftNow, resolve }))
  }

  const run = async () => {
    const { openId, draft } = useReader.getState()
    if (!openId || !draft || running) return

    // 取路分派（按附件粒度，见 auto-split-targets.ts）：pdf / photo / office 各走各的
    const targets = autoSplitTargetsOf(draft)
    if (targets.pdf.length === 0 && targets.photo.length === 0 && targets.office.length === 0) {
      if (targets.allPdf.length > 0) {
        toast.info('这些 PDF 都已人工拆分或跨源合并，为免覆盖你的操作已跳过；需要重来可点「恢复初始分段」')
      } else {
        toast.info('材料包里没有可自动识别的材料')
      }
      return
    }

    // ── 重跑前问一次：会不会抹掉律师改过的东西 ──
    // 必须在 setRunning(true) **之前**：取消时整次 run 不执行，也不能留下 running 残态。
    const choice = await askRerunChoice(draft, targets.pdf)
    if (choice === 'cancel') return
    // 等弹窗期间草稿可能被改过（用户不会，但防御重入/切包）：以最新草稿为准
    if (useReader.getState().openId !== openId) return

    // 先开新会话再置 running：同帧重入的第二个 run 从这里开始，第一个循环立刻过期
    const lease = pollSession.begin()
    setRunning(true)
    // 进度面板同步亮起：提交 164 页 PDF 本身就要几十秒，这段时间面板上不能是空白
    beginOwnedAutoSplit()
    if (targets.pdf.length > 0) setProgress(`正在提交 ${targets.pdf.length} 个 PDF`)
    try {
      // 版面策略与引擎勾选**按包持久化**（draft.recognition），ReaderState 上是当前值。
      // 整批只读一次，避免每个 PDF 各读一遍。
      const layoutMode = useReader.getState().layoutMode
      // 勾选的引擎集合整批只算一次：正主（cloud_backend 单值）+ 交叉比对名单
      // （dual_engines）。两者分开发是因为 cloud_backend 只认单值，塞逗号串会被
      // 后端当成未知值按 auto 处理（详见 platform-selection.resolveBackendRequest）。
      const { cloudBackend, dualEngines } = resolveBackendRequest(useReader.getState().cloudSelection)
      // 分段策略与分歧裁定也是**按包选择**（draft.recognition），与引擎/版面同一批读：
      // 前者决定分段 LLM 调用次数，后者只在双引擎分歧上有事可做。
      const { segmentStrategy, judgeOn } = useReader.getState()

      // 轨道 ①：PDF —— 提交云端任务 + 串行轮询（复用已有结果 / 版面策略 / 双引擎都在里面）
      const pdf = await runPdfTrack({
        openId,
        targets: targets.pdf,
        lease,
        setProgress,
        reportProgress: reportAutoSplitProgress,
        layoutMode,
        cloudBackend,
        dualEngines: dualEngines ? dualEngines.join(',') : null,
        segmentStrategy,
        ocrJudgeEnabled: judgeOn,
      })
      // 轮询期间可能已卸载（关掉阅读器）或重入：不再回写 store、不再弹提示
      if (pdf.stale) return

      // 轨道 ②③：图片单页取字 / Office 文档解析（与 PDF 分段并行，互不影响）
      const photo = await runPhotoTrack({ openId, targets: targets.photo, isStale: () => lease.isStale() })
      if (photo.stale) return
      const office = await runOfficeTrack({ openId, targets: targets.office, isStale: () => lease.isStale() })
      if (office.stale) return

      if (pdf.results.length === 0 && photo.texts.length === 0 && office.texts.length === 0) {
        const failure = pdf.failures[0]
        throw failure?.status === 'rejected' && failure.reason instanceof Error
          ? failure.reason
          : new Error('所有材料的识别任务均未完成')
      }

      if (useReader.getState().openId !== openId) return
      // 回写：分段结果 / 页级质量 / 引擎分歧 / 跨页不一致 / 图片与 Office 正文 / 当事人
      const detected = await applyAutoSplitResults({
        results: pdf.results,
        photoTexts: photo.texts,
        officeTexts: office.texts,
        choice,
      })

      const { message, warned } = summarizeAutoSplitResults({
        results: pdf.results,
        pdfFailed: pdf.failures.length,
        photoTexts: photo.texts,
        officeTexts: office.texts,
        photoFailed: photo.failed,
        officeFailed: office.failed,
        detected,
      })
      if (warned) toast.warning(message)
      else toast.success(message)
    } catch (error) {
      // 组件已卸载（关掉阅读器）或这次 run 已被新 run 取代：静默返回，不弹错误
      if (lease.isStale()) return
      toast.error(error instanceof Error ? error.message : '云端材料识别失败')
    } finally {
      // 过期会话不得复位：新会话正在跑，复位会让按钮可点、进度条消失
      if (!lease.isStale()) {
        setRunning(false)
        setProgress('')
        // 面板同样只在「本会话仍是当前会话」时收起。接管的那个任务用的 lease 已经过期，
        // 这里绝不会误收别人的面板。
        clearAutoSplitTask()
      }
    }
  }

  // 弹窗的三个出口：选完就关框（resolve 会在 run 里被 await 接走）
  const answerConflicts = (choice: RerunChoice) => {
    const pending = pendingConflicts
    setPendingConflicts(null)
    pending?.resolve(choice)
  }

  return {
    run,
    running,
    progress,
    /** 非 null 时 ReaderDialogs 应弹重跑确认框 */
    pendingConflicts,
    onKeepEdits: () => answerConflicts('keep'),
    onOverwrite: () => answerConflicts('overwrite'),
    onCancelRerun: () => answerConflicts('cancel'),
  }
}
