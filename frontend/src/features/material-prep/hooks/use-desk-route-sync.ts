import { useEffect, useRef } from 'react'
import { materialPrep } from '@/app/paths'
import { useLocation, useNavigate, useParams } from 'react-router'
import { parseStage } from '../stages'
import { useJudgePack } from './use-inbox'
import { useReader } from '../store'

/**
 * DeskPage 的路由 / 缓存同步副作用，三条：
 *   1. 路径带 :id → 自动打开对应材料包（刷新 / 前进后退 / 分享直达）
 *   2. 从打开态退到未打开（关阅读器）→ 回退到列表 URL
 *   3. 阅读器关闭（openId 变 null）→ 让列表卡片进度 / 状态刷新
 */
export function useDeskRouteSync() {
  const navigate = useNavigate()
  const location = useLocation()
  const { id } = useParams()
  const openId = useReader((s) => s.openId)
  const openPack = useReader((s) => s.open)
  const judgePack = useJudgePack()
  // 记录是否曾打开过详情：从打开态退到未打开时（关阅读器）回退到列表 URL
  const wasOpenRef = useRef(false)
  const prevOpenId = useRef<number | null>(null)

  // 1. 详情路由：路径里带 :id 时自动打开对应材料包
  useEffect(() => {
    if (id == null) return
    if (useReader.getState().openId === Number(id)) return
    void openPack(Number(id))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  // 2. 关阅读器：从打开态回退到列表 URL，避免 URL 停留在 :id
  //
  // ⚠️ 必须保留当前 stage。曾经这里写的是 materialPrep()（返回 /material-prep），
  // 于从「待处理」点进一个包、再关掉阅读器，URL 会退回首段「收件箱」——
  // 用户看到的是"待处理页进不去了 / 又跳回收件箱了"。stage 是这个页面的
  // 状态而非临时筛选，回退时必须原样带回。
  useEffect(() => {
    const open = openId != null
    if (wasOpenRef.current && !open && id != null) {
      // 用 router 的 location 而不是 window.location：测试跑在 MemoryRouter 下
      // 没有真实地址栏，读 window 会永远拿到空 query。
      const current = parseStage(new URLSearchParams(location.search).get('stage'))
      void navigate(materialPrep(current), { replace: true })
    }
    if (open) wasOpenRef.current = true
  }, [openId, id, navigate, location.search])

  // 3. 关闭阅读器后让列表卡片进度/状态跟上次变化
  useEffect(() => {
    if (prevOpenId.current != null && openId == null) {
      void judgePack.invalidate()
    }
    prevOpenId.current = openId
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openId])
}
