import { useEffect, useState } from 'react'
import { useLocation } from 'react-router'

import { useMediaQuery } from '@/hooks/use-media'
import { COPILOT_LAUNCH_EVENT } from '@/features/copilot/launch'

/**
 * 壳层的两层全局浮层状态：AI 助手面板（⌘J，常驻侧栏）与 ⌘K 全局检索（模态弹窗）。
 *
 * **为什么单独成文件**：AppShell 之前 190 行里有 100 行是这两层的开关、挂载
 * 动画、并排偏好与互斥联动——它们跟路由一点关系都没有（壳层只是 `Outlet`
 * 的容器），却把「壳层为什么长这样」的注释挤到看不见。
 *
 * 状态归口：所有打开路径（快捷键 / 导航栏按钮 / 业务页「AI 助手」按钮 /
 * localStorage 恢复）都汇到这里，互斥用状态联动实现，不在各个回调里互相关停
 * ——否则必漏一条路径。
 */

const COPILOT_OPEN_KEY = 'copilot:open'
const COPILOT_DOCK_KEY = 'copilot:dock'

export function useCopilotShell() {
  const { pathname } = useLocation()

  // AI 助手面板开关：展开状态跨会话记忆（localStorage），首次展开才加载 chunk。
  const [copilotOpen, setCopilotOpen] = useState(() => {
    try {
      return localStorage.getItem(COPILOT_OPEN_KEY) === '1'
    } catch {
      return false
    }
  })
  // 滑出动画期间保持挂载：收起时先播 animate-out，240ms 后再卸载（与面板
  // duration-200 对齐留余量）。重新展开会取消定时器，无缝回到 animate-in。
  // 背景压暗遮罩（PanelBackdrop）同理跟 copilotMounted 走，这样收起时它的
  // fade-out 能和面板滑出同步播完。
  const [copilotMounted, setCopilotMounted] = useState(copilotOpen)
  useEffect(() => {
    if (copilotOpen) {
      setCopilotMounted(true)
      return
    }
    const timer = setTimeout(() => setCopilotMounted(false), 240)
    return () => clearTimeout(timer)
  }, [copilotOpen])
  const toggleCopilot = () => {
    setCopilotOpen((v) => {
      try {
        localStorage.setItem(COPILOT_OPEN_KEY, v ? '0' : '1')
      } catch {
        /* 忽略持久化失败 */
      }
      return !v
    })
  }

  // 并排模式：宽屏（≥1280）下面板不再悬浮覆盖，主内容区让出右侧等宽
  // padding（--copilot-w-app 由面板的 resize hook 同步），页面与 AI 可同屏
  // 对照——合同详情页的文件夹树可直接拖文件进 AI 输入区。**默认并排**：
  // 悬浮会盖住右侧内容且页面无从感知、无法自适应，并排让位后页面按容器
  // 净宽重排（各页布局用容器查询，见 HomePage / ReviewWorkbenchPage）。
  // 窄屏回落悬浮（面板 w-full / sm 定宽覆盖），偏好跨会话记忆。
  const [copilotDock, setCopilotDock] = useState(() => {
    try {
      return localStorage.getItem(COPILOT_DOCK_KEY) !== '0'
    } catch {
      return true
    }
  })
  const isXlUp = useMediaQuery('(min-width: 1280px)')
  const toggleCopilotDock = () => {
    setCopilotDock((v) => {
      try {
        localStorage.setItem(COPILOT_DOCK_KEY, v ? '0' : '1')
      } catch {
        /* 忽略持久化失败 */
      }
      return !v
    })
  }
  /**
   * 详情页（合同／案件作业页）在宽屏下**总是并排**。
   *
   * 详情页的工作形态是「左看案件、右改合同、侧边调 AI」，三者必须同时可见。
   * 悬浮模式下即使不弹遮罩，面板也会盖住右栏的合同——而合同正是要对照着改的
   * 对象，盖住就等于废了右栏。
   *
   * **不看用户偏好**：之前试过「用户显式切过 dock 就尊重偏好」，结果是一旦点过
   * 那个切换按钮，详情页就永远退回悬浮、又盖住合同，用户还得再点一次。
   * 详情页的布局是确定的（三栏并置），不该用全局偏好去覆盖它。
   */
  const onDetailRoute = /^\/projects\/[^/]+/.test(pathname)
  const effectiveDocked = copilotOpen && isXlUp && (onDetailRoute || copilotDock)

  /**
   * AI 助手**永不渲染压暗遮罩**。
   *
   * 它是常驻侧边栏，不是模态对话框——遮罩的存在只会造成两个问题：
   * 1. 点页面任何地方（包括右栏的合同文件）都会先命中遮罩，触发 onClose
   *    把刚打开的助手收回去，表现为「点合同助手就缩回去了」；
   * 2. 律师看不到被遮的合同内容，而这恰好是他要对照着改的对象。
   *
   * 历史：曾经用 `copilotDocked || /^\/projects\//` 做豁免，但豁免条件本身
   * 就是拿"哪些页面不该被遮"去猜"哪些页面不需要遮"——而答案是**全都不需要**。
   * 收起走面板自己的关闭按钮与 ⌘J，不靠点遮罩。
   */
  const copilotBackdropEnabled = false

  // ⌘K 全局检索面板开关：状态收在壳层（与 copilotOpen 同层），⌘K 快捷键、
  // 导航栏检索按钮、弹窗自身关闭（Esc / 点遮罩 / 选中跳转）三条路径都汇到这里。
  const [searchOpen, setSearchOpen] = useState(false)

  // ⌘K 检索（模态弹窗）与 ⌘J AI 助手（常驻侧栏）两层全局浮层互斥：任意一层
  // 展开即收起另一层。此前两层各自独立开关，先 ⌘K 再 ⌘J 会弹窗、侧栏与双重
  // 压暗遮罩同屏叠加。用状态联动而非在各个开关回调里互相关停，所有打开
  // 路径（快捷键 / 导航栏按钮 / localStorage 恢复）都被覆盖，不会漏。
  // 联动收起面板时同步写持久化，与用户手动收起（⌘J / 点遮罩）同一语义。
  useEffect(() => {
    if (!searchOpen) return
    setCopilotOpen(false)
    try {
      localStorage.setItem(COPILOT_OPEN_KEY, '0')
    } catch {
      /* 忽略持久化失败 */
    }
  }, [searchOpen])
  useEffect(() => {
    if (!copilotOpen) return
    setSearchOpen(false)
  }, [copilotOpen])

  // ⌘J / Ctrl+J 呼出收起 AI 助手：非浏览器保留键（Chrome 的下载面板可被
  // 接管），VS Code/ChatGPT 的侧栏肌肉记忆。e.repeat 挡住按住不放——
  // toggle 语义下连续 repeat 会快速开关闪烁。
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || e.key.toLowerCase() !== 'j') return
      e.preventDefault()
      if (e.repeat) return
      toggleCopilot()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // 业务页的「AI 助手」按钮（案件/合同详情页）：只负责开面板（含 chunk
  // 加载），业务上下文由 copilot 域自己的监听（CopilotPanel 挂载时）消费。
  // 打开时同步写持久化，与 ⌘J 手动打开同一语义。
  useEffect(() => {
    const onLaunch = () => {
      setCopilotOpen(true)
      try {
        localStorage.setItem(COPILOT_OPEN_KEY, '1')
      } catch {
        /* 忽略持久化失败 */
      }
    }
    window.addEventListener(COPILOT_LAUNCH_EVENT, onLaunch)
    return () => window.removeEventListener(COPILOT_LAUNCH_EVENT, onLaunch)
  }, [])

  // ⌘K / Ctrl+K 唤起 / 收起全局检索（再按一次即收起）。与 ⌘J 同层注册；
  // e.repeat 同理挡住按住不放的连续切换。
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || e.key.toLowerCase() !== 'k') return
      e.preventDefault()
      if (e.repeat) return
      setSearchOpen((v) => !v)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return {
    copilotOpen,
    copilotMounted,
    copilotBackdropEnabled,
    effectiveDocked,
    isXlUp,
    toggleCopilot,
    toggleCopilotDock,
    searchOpen,
    setSearchOpen,
  }
}
