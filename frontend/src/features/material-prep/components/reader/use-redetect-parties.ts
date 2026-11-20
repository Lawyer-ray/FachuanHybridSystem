import { useCallback, useState } from 'react'
import { toast } from 'sonner'
import { applyDetectedParties } from '../../draft/detect-parties'
import { resolveParties } from '../../draft/party-lookup'
import { useReader } from '../../store'

/**
 * 「重新识别当事人」：对已经分好段（正文已在草稿里）的材料包重跑一次识别。
 *
 * ═══ 为什么必须有一个手动入口 ═══
 * 自动识别只在**分段成功那一刻**跑一次，而回填规则是「只填空字段」。
 * 于是第一次识别错了（比如把职工和单位拼成一个委托人）就再也改不掉：
 * 那个错值带着 `src: '自动识别'` 躺在草稿里，重跑分段会被当成「律师已填」跳过，
 * 律师只能先手动清空字段再重新分段 —— 为了改两个字重跑一整个 164 页的 OCR。
 *
 * 所以这里用 `replaceAuto`：**机填值可以被新结果覆盖/清空，律师手填的依旧不动**。
 */
export function useRedetectParties(): { busy: boolean; redetect: () => void } {
  const [busy, setBusy] = useState(false)

  const redetect = useCallback(() => {
    if (busy) return
    const st = useReader.getState()
    const draft = st.draft
    const openId = st.openId
    if (!draft || !openId) return
    setBusy(true)
    void (async () => {
      try {
        const detected = await resolveParties(draft)
        // 识别期间可能已经关掉阅读器 / 切到别的包：认到别处去比不认更糟
        if (useReader.getState().openId !== openId) return
        if (!detected.our && !detected.their) {
          toast.info('材料里没识别出当事人，直接手填即可')
          return
        }
        let changed = false
        useReader.getState().update((value) => {
          const r = applyDetectedParties(value.infos, detected, { replaceAuto: true })
          changed = r.changed
          return r.changed ? { ...value, infos: r.infos } : value
        })
        if (changed) toast.success('已重新识别当事人')
        else toast.info('识别结果与当前填写一致')
      } catch (error) {
        toast.error(error instanceof Error ? error.message : '当事人识别失败')
      } finally {
        setBusy(false)
      }
    })()
  }, [busy])

  return { busy, redetect }
}
