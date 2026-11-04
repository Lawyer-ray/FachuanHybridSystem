import { useMemo, useState } from 'react'

/**
 * 邮件 HTML 正文渲染。
 *
 * ## 为什么用 sandboxed iframe 而不是 dangerouslySetInnerHTML
 *
 * 邮件 HTML 是**完全不可信的外部输入**：任何一个发件人都能给我们的页面塞
 * `<script>`、`<img onerror>`、外链追踪像素。项目里没有 DOMPurify，而手写
 * 净化器永远会漏——所以这里用 iframe 的 `sandbox` 属性做**机制隔离**：
 * 不给 `allow-scripts`，内部脚本一律不执行；不给 `allow-same-origin`，
 * 它拿不到父页面的 cookie / localStorage。
 *
 * 两个属性都不给时，浏览器视其为唯一来源（opaque origin），这是最严格的组合。
 *
 * ## 为什么必须剥掉邮件自带的 <html>/<head>
 *
 * 真实邮件（尤其 Outlook 导出的）会带 `<!--[if gte mso 9]><xml>...` 条件注释
 * 和 vml 命名空间声明。整段塞进 iframe 后字体/行高会被邮件自带样式覆盖，
 * 在我们 12px 的紧凑布局里会巨丑。这里只取 body 内部内容，样式由外层注入。
 */

/** 从完整 HTML 文档里抽出 body 内部内容；没有 body 时原样返回 */
function extractBodyInner(html: string): string {
  const match = /<body[^>]*>([\s\S]*?)<\/body>/i.exec(html)
  return match?.[1] ?? html
}

/** 注入到 iframe 里的最小样式：只保证可读，不试图复刻邮件原貌 */
const IFRAME_STYLE = `
  <style>
    html, body { margin: 0; padding: 0; }
    body {
      font: 12px/1.65 -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif;
      color: #27272a;
      word-break: break-word;
      overflow-wrap: anywhere;
    }
    /* 邮件里到处都是固定宽度的 table 布局，超过容器就横向滚动而不是撑破页面 */
    img { max-width: 100%; height: auto; }
    table { max-width: 100%; border-collapse: collapse; }
    a { color: #2563eb; }
    /* 追踪像素（1x1 图）不显示，避免视觉上一个诡异的小点 */
    img[width="1"][height="1"] { display: none; }
  </style>
`

export function MailHtmlBody({ html }: { html: string }) {
  const [height, setHeight] = useState(160)

  // 剥壳 + 拼样式。html 变化才重算，避免每次渲染都跑一遍正则
  const srcDoc = useMemo(() => {
    const inner = extractBodyInner(html)
    return `<!doctype html><html><head><meta charset="utf-8">${IFRAME_STYLE}</head><body>${inner}</body></html>`
  }, [html])

  return (
    <iframe
      // sandbox 只给 allow-popups：邮件里的链接点了能开新页，但脚本与同源访问全禁。
      // 不加 allow-scripts / allow-same-origin —— 这是本组件的安全边界，改动前请三思。
      sandbox="allow-popups allow-popups-to-escape-sandbox"
      referrerPolicy="no-referrer"
      title="邮件正文"
      srcDoc={srcDoc}
      onLoad={(e) => {
        // 按内容真实高度撑开，避免 iframe 内部再出一层滚动条（套在抽屉里很难用）
        const doc = e.currentTarget.contentDocument
        if (doc?.body) {
          const h = Math.min(Math.max(doc.body.scrollHeight, 80), 420)
          setHeight(h)
        }
      }}
      className="w-full rounded-[8px] border border-border bg-white"
      style={{ height }}
    />
  )
}
