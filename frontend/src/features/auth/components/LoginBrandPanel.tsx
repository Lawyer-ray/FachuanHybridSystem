/**
 * 登录页左侧品牌栏（窄屏隐藏，由表单栏顶部的一行精简标识替代）。
 *
 * 编辑 / 时装杂志风：眉标 + 元信息带 + 大字号主张 + 编辑手记引言 + 编号目录 + 页脚。
 * 纯展示无交互，层级全靠字号对比、衬线斜体与极细分割线，不用光斑 / 玻璃 / 渐变卡片。
 */

/** 目录条目：编号 + 名称 + 一行短描述（描述让目录不再是孤立词） */
const CAPABILITIES = [
  { no: '01', name: '材料预处理', desc: 'OCR 识别 · 智能拆分 · 自动归档' },
  { no: '02', name: '案件台账', desc: '从客户接洽到结案归档的全流程协同' },
  { no: '03', name: 'AI 辅助', desc: '检索 / 审查 / 起草 一体化智能工具' },
]

/** 编辑手记：栏目里唯一的「重音」，给主张段做收束 */
const PULLQUOTE = {
  text: '我们不是要取代律师，而是把律师还给法律本身。',
  cite: '— 编辑手记 · EDITORIAL',
}

export function LoginBrandPanel() {
  return (
    <aside className="fc-brand">
      {/* 眉头 + 元信息带合成一个块：与「主张」「目录」三块由 aside 的
          justify-content: space-between 分布到顶 / 中 / 底，不再有大段空白 */}
      <div className="fc-brand__head-block">
        <header className="fc-brand__head">
          <span className="fc-mark">法穿</span>
          <span className="fc-mark__meta">AI Copilot</span>
          <span className="fc-brand__est">EST. 2026</span>
        </header>

        <div className="fc-brand__meta" aria-label="本期目录信息">
          <span className="fc-brand__meta-item">ISSUE No. 01</span>
          <span aria-hidden className="fc-brand__meta-sep">
            /
          </span>
          <span className="fc-brand__meta-item">INTAKE EDITION</span>
          <span aria-hidden className="fc-brand__meta-sep">
            /
          </span>
          <span className="fc-brand__meta-item">§ 01 · IDENTITY</span>
        </div>
      </div>

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

        <figure className="fc-pullquote">
          <blockquote>
            <span aria-hidden className="fc-pullquote__mark">
              ❝
            </span>
            {PULLQUOTE.text}
          </blockquote>
          <figcaption>{PULLQUOTE.cite}</figcaption>
        </figure>
      </div>

      {/* 索引条与页脚成组贴底，主张块才会落在视觉中线上 */}
      <div className="fc-brand__tail">
        <ol className="fc-index">
          {CAPABILITIES.map((item) => (
            <li key={item.no}>
              <span className="fc-index__no">{item.no}</span>
              <span className="fc-index__name">{item.name}</span>
              <span className="fc-index__desc">{item.desc}</span>
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