/**
 * 登录页左侧品牌栏（窄屏隐藏，由表单栏顶部的一行精简标识替代）。
 *
 * 编辑 / 时装杂志风：眉标 + 大字号主张 + 编号索引条 + 页脚。
 * 纯展示无交互，层级全靠字号对比与极细分割线，不用光斑 / 玻璃 / 渐变卡片。
 */

const CAPABILITIES = [
  { no: '01', name: '材料预处理' },
  { no: '02', name: '案件台账' },
  { no: '03', name: 'AI 辅助工具' },
]

export function LoginBrandPanel() {
  return (
    <aside className="fc-brand">
      <header className="fc-brand__head">
        <span className="fc-mark">法穿</span>
        <span className="fc-mark__meta">AI Copilot</span>
        <span className="fc-brand__est">Est. 2026</span>
      </header>

      <div>
        <p className="fc-eyebrow">法律事务协同系统</p>
        <h1 className="fc-display">
          让每一个案件
          <br />
          <span className="fc-display__accent">自动运转</span>
        </h1>
        <p className="fc-lede">
          从客户接洽到结案归档，全流程自动化。短信驱动、AI 赋能，把律师从事务性工作中解放出来。
          <em className="fc-lede__serif">From intake to archive, on autopilot.</em>
        </p>
      </div>

      {/* 索引条与页脚成组贴底，主张块才会落在视觉中线上 */}
      <div className="fc-brand__tail">
        <ol className="fc-index">
          {CAPABILITIES.map((item) => (
            <li key={item.no}>
              <span className="fc-index__no">{item.no}</span>
              <span className="fc-index__name">{item.name}</span>
            </li>
          ))}
        </ol>

        <footer className="fc-brand__foot">
          <span>© 2026 法穿 AI</span>
          <span>PolyForm Noncommercial</span>
        </footer>
      </div>
    </aside>
  )
}
