import { useEffect, useMemo, useRef } from 'react'
import { useIsMutating, useQueryClient, type QueryClient, type MutationKey } from '@tanstack/react-query'

import { errMessage } from '@/lib/errors'
import { uploadContract, type UploadedTask } from '../api'
import { recommendParty, type PartyKey } from '../domain'

/** 上传 + 识别的阶段：idle → uploading → ready | error */
export type LaunchPhase = 'idle' | 'uploading' | 'ready' | 'error'

/** 一次识别的结果：立场选项的来源 + 后续 confirmParty 复用的 taskId */
export interface LaunchRecognized {
  taskId: string
  parties: Record<string, string>
  /** 用委托客户名自动推荐的我方立场；匹配不上为 null（让律师自己选） */
  party: PartyKey | null
}

/** 单次上传识别的缓存条目归属（按抽屉输入分区，不同文件不会互相串数据） */
const UPLOAD_SCOPE = { id: 'contract-review:launch-upload' }

/**
 * 抽屉第一阶段：上传合同 + 让后端识别甲乙丙丁，并自动推荐我方。
 *
 * **为什么必须先识别再选立场**：立场决定全部建议方向。合同可能是甲乙丙丁
 * 四方、我方也可能是乙方甚至丙方（代表客户股东去审时更是如此）。先让律师
 * 看着「甲方/乙方」两个空标签选，等于让他猜；识别完再选，他看到的是真实
 * 当事人名称。
 *
 * **为什么是 mutation 而不是旧的那段 useEffect**：旧实现用 `runningRef` 挡住
 * "effect 因 phase 变化重跑"，而这个 ref 只在错误分支复位——成功路径永不复位，
 * 于是同一个抽屉换了文件（fileName 变化）就再不会重传，界面停在上一份合同的
 * 识别结果上且毫无提示。
 *
 * 现在上传是**显式动作**：抽屉打开 / 输入变化 / 点重试时才 mutate 一次；结果按
 * `scope + mutationKey` 落在 mutation cache 里（`retry: 0`，一条输入只有一条记录，
 * 失败重试就地覆盖），阶段由记录本身派生（见 uploadPhaseOf）。不再有守卫 ref，
 * 也就没有"某条路径忘了复位"这种状态。
 */
export function useLaunchUpload(params: {
  open: boolean
  loadFile: () => Promise<ArrayBuffer>
  fileName: string
  /** 我方委托客户名：用于从识别结果里自动推荐「我方是哪一方」 */
  clientName?: string
}) {
  const { open, loadFile, fileName, clientName } = params
  const queryClient = useQueryClient()

  // 识别输入：关闭抽屉即作废（下次打开换了一份合同，不能沿用上一份的识别结果）
  const input = useMemo(() => (open ? `${fileName}\u0000${clientName ?? ''}` : null), [open, fileName, clientName])
  // loadFile 是调用方每次渲染新建的箭头函数，不能进缓存 key（否则每次都算新输入），
  // 但 mutate 时必须用最新那一个，所以走 ref（只在 effect 里写，不在渲染期写）。
  const loadFileRef = useRef(loadFile)
  useEffect(() => {
    loadFileRef.current = loadFile
  }, [loadFile])

  const mutationKey = useMemo<MutationKey>(() => (input ? [input] : []), [input])
  const uploading = useIsMutating({ mutationKey, exact: true }) > 0

  /**
   * 触发上传（调用方在 effect 里调，见 ReviewLaunchDrawer）。
   *
   * 幂等：同一条输入已经有识别结果就不再传。这个判断**不经过 state**，所以
   * 不会被 StrictMode 的 effect 双跑放大成两次上传。
   */
  const recognize = () => {
    if (!input) return
    const existing = queryClient.getMutationCache().find({
      mutationKey,
      exact: true,
      predicate: (m) => m.options.scope === UPLOAD_SCOPE && m.state.status === 'success',
    })
    if (existing) return
    // 起这条 mutation 的 Promise 必须自己接住：结果由上面的 cache 查询渲染，
    // 没人 await 它，漏 catch 会在 Node 里变成 unhandledRejection（测试会报错）
    queryClient
      .getMutationCache()
      .build(queryClient, {
        mutationKey,
        scope: UPLOAD_SCOPE,
        // 不重试：一条输入对应一条记录，"重试"是用户点重试按钮的显式动作
        retry: 0,
        // 本 hook 自带错误渲染（抽屉内 ErrorBlock），别让 main.tsx 的全局
        // mutation onError 再弹一次 toast
        onError: () => {},
        mutationFn: (): Promise<LaunchRecognized> => uploadAcross(loadFileRef.current, fileName, clientName),
      })
      .execute(undefined)
      .catch(() => {
        /* 错误已落在 cache 里，由 uploadStateOf → err 渲染 */
      })
  }

  /** 丢弃当前输入的识别结果并重传（失败后重试用） */
  const retry = () => {
    if (!input) return
    // 先丢掉这次的失败记录，再照常触发（recognize 只认 status === 'success'）
    const cache = queryClient.getMutationCache()
    const scoped = cache.findAll({ mutationKey, exact: true })
    for (const m of scoped) if (m.options.scope === UPLOAD_SCOPE) cache.remove(m)
    recognize()
  }

  const result = input
    ? uploadStateOf(queryClient, mutationKey, uploading)
    : { phase: 'idle' as LaunchPhase, data: null, error: null }

  return {
    phase: result.phase,
    parties: result.data?.parties ?? null,
    taskId: result.data?.taskId ?? null,
    party: result.data?.party ?? null,
    err: result.error,
    recognize,
    retry,
  }
}

/** 取包好的 File 上传并归一化识别结果（含"只保留识别到的方"与立场推荐） */
async function uploadAcross(
  loadFile: () => Promise<ArrayBuffer>,
  fileName: string,
  clientName?: string,
): Promise<LaunchRecognized> {
  const bytes = await loadFile()
  const file = new File([bytes], fileName, {
    type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  })
  const task: UploadedTask = await uploadContract(file)
  return toRecognized(task, clientName)
}

function toRecognized(task: UploadedTask, clientName?: string): LaunchRecognized {
  // 只保留识别到的方：空值不渲染，丙丁没出现就不占位
  const found: Record<string, string> = {}
  for (const [k, v] of Object.entries(task.parties ?? {})) {
    if (v?.trim()) found[k] = v.trim()
  }
  // 自动推荐我方：用委托客户名去匹配某一方；匹配不上就留空让律师选
  return { taskId: task.task_id, parties: found, party: recommendParty(found, clientName) }
}

/** 从 cache 里那条上传记录派生阶段（pending / error / success → 三态） */
function uploadStateOf(
  queryClient: QueryClient,
  mutationKey: MutationKey,
  uploading: boolean,
): { phase: LaunchPhase; data: LaunchRecognized | null; error: string | null } {
  if (uploading) return { phase: 'uploading', data: null, error: null }
  const mutation = queryClient
    .getMutationCache()
    .find({ mutationKey, exact: true, predicate: (m) => m.options.scope === UPLOAD_SCOPE })
  if (!mutation) return { phase: 'uploading', data: null, error: null }
  if (mutation.state.status === 'error') {
    return { phase: 'error', data: null, error: errMessage(mutation.state.error, '读取合同失败') }
  }
  if (mutation.state.status === 'success') {
    return { phase: 'ready', data: mutation.state.data as LaunchRecognized, error: null }
  }
  // idle（尚未执行）视同进行中：调用方紧接着就会 recognize()
  return { phase: 'uploading', data: null, error: null }
}
