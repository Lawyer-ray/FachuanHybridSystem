import { useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import { errMessage } from '@/lib/errors'
import { folderFileUrl, registerFolderSaveAsIntent, type FolderOwnerKind } from '../../api'
import { workbenchKeys } from '../../hooks/use-workbench-data'
import { defaultSaveAsName } from './save-as-name'

/**
 * 「另存为」的编排：登记意图 → 触发 DS 保存 → 延迟刷新。
 *
 * **为什么是两步（且顺序不能换）**：社区版 OnlyOffice 不暴露 `downloadAs`，
 * 编辑后的字节只在 DS 那边，浏览器拿不到——前端没法像上传那样把内容传给
 * 「另存为」接口。只能先把「下次保存写哪个名字」登记到编辑器会话上，
 * 再让 DS forcesave；真正落盘发生在后端回调里（原文件不动，写新名字）。
 *
 * **登记失败绝不触发保存**：意图没登记成功时，forcesave 走的仍是「原地覆写」，
 * 等于律师点另存却把原稿改了——不可逆。所以失败分支只提示、直接返回。
 *
 * 两个预览形态（整页 `FilePreview` / 右栏 `FilePreviewCard`）共用这一份，
 * 避免「一边修好一边还是旧行为」。
 */
export function useSaveAs({
  kind,
  ownerId,
  file,
  requestSave,
  onSaved,
  enabled,
  locked,
}: {
  kind: FolderOwnerKind
  ownerId: number
  file: { subpath: string; name: string }
  /** 触发 DS forcesave；编辑器未就绪返回 false（不要假装已提交） */
  requestSave: () => boolean
  /** 落盘后通知父级刷新业务数据 */
  onSaved?: () => void
  /** 按钮可用条件：docx 且合同文件夹（cases 没这个端点） */
  enabled: boolean
  /** 有其它操作在进行中时禁止重入 */
  locked: boolean
}): () => Promise<void> {
  const qc = useQueryClient()

  return useCallback(async () => {
    if (!enabled || locked) return
    // 名字在点击时就定下来（today 只算一次），否则跨零点会前后不一致
    const name = defaultSaveAsName(file.name)
    try {
      const res = await registerFolderSaveAsIntent(kind, ownerId, file.subpath, name)
      // 触发保存前先确认编辑器还活着：意图已登记但没有保存，等于没生效，
      // 而用户看到「已提交」会直接关页面。这里只提示，意图留着不影响下次保存
      if (!requestSave()) {
        toast.error('编辑器尚未就绪，请稍后重试')
        return
      }
      toast.success('已提交另存为', { description: `${res.name || name} · 原文件保持不变` })
      // 落盘在 DS 回调里（1–3 秒）后才会有新文件：文件夹树缓存 60s，
      // 不主动失效就会一直看不到新名字，与原地保存同一套延迟刷新口径
      window.setTimeout(() => {
        void qc.invalidateQueries({ queryKey: workbenchKeys.folderEntries(kind, ownerId) })
        onSaved?.()
      }, 2500)
    } catch (e) {
      // 文案取后端 message（未打开文档 / 文件不存在 / 无权限 / 文件名非法各有
      // 明确说法），不裸 e.message——那是英文技术描述
      toast.error('另存为失败', {
        description: errMessage(e, `请先在 OnlyOffice 中打开 ${file.name}，再点击另存为`),
      })
    }
  }, [enabled, locked, file.name, file.subpath, kind, ownerId, requestSave, onSaved, qc])
}

/**
 * 「另存为」是否可点：只对**合同文件夹的 docx**开放。
 *
 * 两个限制都来自后端契约，不是 UI 偏好：
 * - 非 docx 打开的是只读 `view` 模式，改完也存不回去，给按钮就是假按钮；
 * - `folder-save-as-intent` 只挂在 contracts 路由下，cases 侧没有该端点。
 */
export function canSaveAs(kind: FolderOwnerKind, fileName: string): boolean {
  return kind === 'contract' && /\.docx$/i.test(fileName)
}

/**
 * 登记意图时用的 subpath：取 `folderFileUrl` 里同一份编码后原文再解码回来。
 *
 * 绕这一圈是**故意的**：后端按 source_path 逐字匹配编辑器会话，而 source_path
 * 由 `folderFileUrl` 的编码口径拼出（`?subpath=<encodeURIComponent(subpath)>`，
 * 后端再用 `quote(..., safe='')` 回拼）。从 URL 反解保证「前端传的路径」与
 * 「签配置时用的路径」永远是同一个串——万一将来编码口径调整（比如换用
 * URLSearchParams），这里自动跟随，不会悄悄错开一次编码导致「明明开着却报未打开」。
 */
export function intentSubpath(kind: FolderOwnerKind, ownerId: number, subpath: string): string {
  const query = folderFileUrl(kind, ownerId, subpath).split('?')[1] ?? ''
  const raw = new URLSearchParams(query).get('subpath')
  return raw ?? subpath
}
