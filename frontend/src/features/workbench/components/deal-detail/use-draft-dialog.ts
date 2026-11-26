import { useCallback, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

import { workbenchKeys } from '../../hooks/use-workbench-data'

/** 起草弹窗回报的成稿位置：`kind`/`owner_id` 由后端给出，前端不推断落位 */
export interface DraftedFile {
  kind: 'case'
  ownerId: number
  subpath: string
  name: string
}

/**
 * 「生成文书」弹窗的状态编排（从 DealDetailPage 拆出：页面已接近 350 行软红线）。
 *
 * 两件事：
 * - **哪一案在起草**：入口在案件节上，一个委托可挂多个阶段案，所以案件 id 由
 *   点按钮的那张卡决定（见 `CaseSection` 的 `onDraft`）；
 * - **成稿怎么打开**：用返回的 `subpath` 走现有文件夹通道，而不是喂 `file_url`——
 *   画布签配置时后端会把它换成 HMAC 代理地址，而「保存 / 另存为 / 版本」整套
 *   都挂在 kind+owner+subpath 上（见 use-folder-save），单给一个 URL 会绕过保存
 *   回写那条链路。同时失效该案的文件夹树缓存，否则新文件要刷整页才看得到。
 */
export function useDraftDialog(openDraftedFile: (file: DraftedFile) => void) {
  const qc = useQueryClient()
  const [caseId, setCaseId] = useState<number | null>(null)

  const openFor = useCallback((id: number) => setCaseId(id), [])
  const close = useCallback(() => setCaseId(null), [])

  const onCreated = useCallback(
    (_fileUrl: string, subpath: string) => {
      if (caseId == null) return
      openDraftedFile({ kind: 'case', ownerId: caseId, subpath, name: subpath.split('/').pop() ?? '文书.docx' })
      void qc.invalidateQueries({ queryKey: workbenchKeys.folderEntries('case', caseId) })
    },
    [caseId, openDraftedFile, qc],
  )

  return { caseId, openFor, close, onCreated }
}
