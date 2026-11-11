import { useCallback, useRef, useState } from 'react'
import { toast } from 'sonner'
import { errMessage } from '@/lib/errors'
import { useCreatePack } from '../hooks/use-inbox'
import { formatMB, uploadSizeCapBytes } from '../constants'
import type { PrepStage } from '../stages'

/**
 * DeskPage 的上传编排状态簇：选文件的 input ref、拖放层计数、`dragging` /
 * `uploading` 两个 UI 态，以及建材料包的动作本身。
 *
 * 为什么成簇住在这里：`dragging` 与 `uploading` 是**这一个流程**的两个阶段
 * （拖入 → 上传中），拖放层 / 页签按钮 / 文件选择都读同一对值；分开放就变成
 * 三个组件各自猜「现在到底在干什么」。建包成功后的「切到待处理」也属于这里，
 * 由 `onCreated` 交回页面处理（阶段状态归 useDeskFilters 所有）。
 */
export function useDeskUpload({
  onCreated,
}: {
  /** 建包成功后要落到的阶段（新包在「待处理」），以及清空选中项 */
  onCreated: (stage: PrepStage) => void
}) {
  const createPack = useCreatePack()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const dragDepth = useRef(0)
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)

  const handleFiles = useCallback(
    async (files: FileList | null) => {
      if (!files || files.length === 0) return
      const list = Array.from(files)
      // 体积预检：后端对单文件有硬上限（普通 50MB / 压缩包 200MB），超限必被
      // 400 拒绝。传到一半才被拒既浪费上行带宽又让用户白等，这里提前报。
      // 逐个提示第一个超限文件即可——一次拖 10 个超限文件时堆 10 条 toast
      // 只会把提示区刷满，反而看不到具体哪个文件有问题。
      const oversized = list.find((f) => f.size > uploadSizeCapBytes(f.name))
      if (oversized) {
        toast.error(
          `${oversized.name} 过大（${formatMB(oversized.size)}），单个不能超过 ${formatMB(uploadSizeCapBytes(oversized.name))}`,
        )
        setDragging(false)
        return
      }
      setUploading(true)
      try {
        const detail = await createPack.mutateAsync(list)
        onCreated('todo')
        // 压缩包会被服务端展开：以响应里的实际附件数为准，别拿输入文件数冒充
        const total = detail?.attachment_count ?? list.length
        const hadArchive = list.some((f) => /\.(zip|rar|7z)$/i.test(f.name))
        toast.success(
          hadArchive
            ? `压缩包已展开，共收进 ${total} 份材料`
            : `已收进 ${total} 份材料`,
        )
      } catch (e) {
        // 必须透出后端文案：上传失败的一大类是「附件过大 / 格式不支持」这类
        // 可自行处理的 400，后端 message 已经写得很具体。以前这里吞掉错误
        // 一律弹「请检查后端连接」，会让 65MB 的 PDF 被拒时用户以为后端挂了
        // （实测：一份 65.7MB / 164 页的扫描件超 50MB 上限被拒，看到的却是连接问题）。
        toast.error(errMessage(e, '上传失败，请重试'))
      } finally {
        setUploading(false)
        setDragging(false)
      }
    },
    [createPack, onCreated],
  )

  const onPickFiles = useCallback(() => fileInputRef.current?.click(), [])

  /** 拖放层的 enter / leave 成对调用：计数器归零才认为真的离开了窗口 */
  const onDragEnter = useCallback(() => {
    dragDepth.current += 1
    setDragging(true)
  }, [])

  const onDragLeave = useCallback(() => {
    dragDepth.current -= 1
    if (dragDepth.current <= 0) {
      dragDepth.current = 0
      setDragging(false)
    }
  }, [])

  const onDrop = useCallback(
    (files: FileList | null) => {
      dragDepth.current = 0
      void handleFiles(files)
    },
    [handleFiles],
  )

  return {
    fileInputRef,
    dragging,
    uploading,
    handleFiles,
    onPickFiles,
    onDragEnter,
    onDragLeave,
    onDrop,
  }
}
