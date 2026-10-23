/**
 * AI 助手面板的压暗遮罩 —— 面板展开时把内容区压暗一档，拉开主次层次。
 *
 * 为什么从「inset-0 全屏压暗」改成「只压导航栏以下」：
 * 导航栏是 sticky z-50 且常驻可点（AI 助手 / ⌘K 检索 / 新建案件都在上面），
 * 一整块 inset-0 的遮罩会把它一起压暗成「置灰不可用」的样子——视觉上禁用、
 * 实际却能点，是典型的交互与视觉打架。现在遮罩从 --app-navbar-h 起，
 * 只压真正被面板遮挡的内容区。
 *
 * 为什么是「压暗」而不加毛玻璃：
 * 强度直接对齐站内弹窗基线——shadcn Dialog / AlertDialog 的遮罩都是
 * `bg-black/50`（「新建日程」等弹窗走的就是这套），这里用同一档，避免
 * 用户在不同层之间感到两种「暗」。但它们有 `backdrop-blur` 的只有 Sheet /
 * DaySheet，本面板是 non-modal dock，不毛玻璃（跟面板自身一起看会脏）。
 *
 * 层级：遮罩必须**低于**面板（z-[100]），否则会把面板本身也压暗。父级
 * z-[100] 建了层叠上下文、子节点不参与全局 z 比较，所以遮罩用 z-[90] 即可
 * 压住页面内容（含 z-[80] 全屏阅读器），又不会越到面板之上。
 * 点击即收起面板（与右键菜单遮罩同义），所以需要吃掉指针事件。
 * 显隐动画与面板的 animate-in / animate-out 同频（200ms）；挂载时机由
 * AppShell 的 copilotMounted 统一控制，这里只负责收尾淡出。
 */

export function PanelBackdrop({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <div
      aria-hidden
      onClick={onClose}
      className={`fixed inset-x-0 top-(--app-navbar-h) bottom-0 z-[90] bg-black/50 duration-200 fill-mode-both transition-none ${
        open ? 'animate-in fade-in' : 'animate-out fade-out'
      }`}
    />
  )
}
