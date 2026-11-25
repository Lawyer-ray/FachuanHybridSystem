import type { RotDeg } from '../types'
import { rotatedSizeOf } from '../draft/page-rotation'

/**
 * 把一张位图按顺时针角度重编码（人工转正的照片素材用）。
 *
 * ## 为什么照片只能在浏览器转
 *
 * PDF 素材的旋转由**服务端**在切页时烧进 `/Rotate`（前端没有 pdf-lib，也不该为
 * 一次旋转传几十 MB 往返）。照片不同：它没有「页对象」，一页就是整张图，
 * 归案时上传的就是这张图的字节——不在这里转，客户收到的证据照片就还是躺着的。
 *
 * ## 为什么按原 MIME 决定编码格式
 *
 * PNG 常带透明通道（截图、电子签），一律转 JPEG 会把透明区域刷成黑底；而
 * JPEG 重编码成 PNG 只会让体积翻几倍。所以：PNG 保持 PNG，其余按 JPEG 0.92。
 *
 * 失败（解码不了、canvas 拿不到上下文）抛错，由调用方决定降级——归案不能因为
 * 「这张图转不动」而整包失败。
 */
export async function rotateImageBlob(blob: Blob, deg: RotDeg): Promise<Blob> {
  if (deg === 0) return blob

  const { source, release } = await decode(blob)
  try {
    const { width, height } = rotatedSizeOf(source.width, source.height, deg)
    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('无法创建 canvas 2d 上下文')

    // 绕画布中心旋转，再把图按原始尺寸画回去（90/270 时画布已宽高互换）
    ctx.translate(width / 2, height / 2)
    ctx.rotate((deg * Math.PI) / 180)
    ctx.drawImage(source, -source.width / 2, -source.height / 2)

    const keepPng = (blob.type || '').toLowerCase().includes('png')
    return await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob(
        (out) => (out ? resolve(out) : reject(new Error('图片编码失败'))),
        keepPng ? 'image/png' : 'image/jpeg',
        keepPng ? undefined : 0.92,
      )
    })
  } finally {
    // ImageBitmap 持有解码后的像素 / <img> 持有 object URL，不释放会在多张照片
    // 的包里累积（一个卷宗几十张证据照片是常态）
    release()
  }
}

/**
 * 解码成可画的东西：优先 `createImageBitmap`，退回 `<img>` + object URL。
 *
 * `release()` 必须由调用方在**画完之后**调：object URL 过早在 finally 里 revoke，
 * 部分浏览器会把还没绘制的内容丢掉（画出来一片空白，且不报错）。
 */
async function decode(
  blob: Blob,
): Promise<{ source: ImageBitmap | HTMLImageElement; release: () => void }> {
  if (typeof createImageBitmap === 'function') {
    const bitmap = await createImageBitmap(blob)
    return { source: bitmap, release: () => bitmap.close() }
  }
  const url = URL.createObjectURL(blob)
  const img = new Image()
  try {
    await new Promise<void>((resolve, reject) => {
      img.onload = () => resolve()
      img.onerror = () => reject(new Error('图片解码失败'))
      img.src = url
    })
  } catch (e) {
    URL.revokeObjectURL(url)
    throw e
  }
  return { source: img, release: () => URL.revokeObjectURL(url) }
}
