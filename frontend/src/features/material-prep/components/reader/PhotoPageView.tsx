import { useEffect, useState } from 'react'
import { Image as ImageIcon } from 'lucide-react'

import { fetchAttachmentBytes } from '../../api'
import { rotateImageBlob } from '../../api/rotate-image'
import type { RotDeg } from '../../types'

/**
 * 位图素材的一页（一张图 = 一页）。
 *
 * ## 为什么照片转正走「重编码」而不是 CSS transform
 *
 * 照片没有 PDF 的页对象可烧 `/Rotate`，只能动像素。用 CSS `rotate()` 看似更省，
 * 但容器高度是按**未旋转**的图算的：转 90° 后要么沿竖向留一大块空白、要么把
 * 图裁掉一截，两种都不能接受（律师要看清整张证据照）。所以直接按旋转角度重新
 * 编码成一张新图——与归案上传时用的是同一个函数（`rotateImageBlob`），
 * 「屏幕上看到的」与「传给客户的」用的是同一条代码路径。
 *
 * 代价是每次改角度要重编码一次（图片素材通常几百 KB～几 MB），换来的是尺寸精确。
 */
export function PhotoPageView({
  messageId,
  partIndex,
  rotation = 0,
}: {
  messageId: number
  partIndex: number
  /** 人工转正角度（顺时针） */
  rotation?: RotDeg
}) {
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    let alive = true
    let objectUrl: string | null = null
    setError(false)

    fetchAttachmentBytes(messageId, partIndex)
      .then(async (bytes) => {
        const raw = new Blob([bytes])
        // 0° 不重编码：原字节直接显示，省一次解码/编码
        const shown = rotation === 0 ? raw : await rotateImageBlob(raw, rotation)
        if (!alive) return
        objectUrl = URL.createObjectURL(shown)
        setUrl(objectUrl)
      })
      .catch(() => {
        // 加载失败要有可见反馈（与 PdfPageView 的 error 分支同款），不能静默吞掉
        if (alive) setError(true)
      })

    return () => {
      alive = false
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [messageId, partIndex, rotation])

  if (error) {
    return (
      <div className="grid h-48 place-items-center text-xs text-muted-foreground">该页加载失败</div>
    )
  }
  if (!url) {
    return (
      <div className="grid h-56 place-items-center bg-zinc-50 text-xs text-muted-foreground">
        <ImageIcon className="h-6 w-6" />
      </div>
    )
  }
  return <img src={url} alt="材料页" className="block h-auto w-full bg-white" />
}
