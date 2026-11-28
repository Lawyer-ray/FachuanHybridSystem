/**
 * Safari 16.4 兼容门禁：把「这个仓事实上要求 Safari ≥ 16.4」变成可执行的断言。
 *
 * ## 为什么是 16.4 这个版本
 *
 * 两条独立证据指向同一个下限，与本文档无关：
 * 1. `vite.config.ts` 的 `build.target: "es2022"`（ES2022 语法层）；
 * 2. 样式走 Tailwind CSS v4，其官方基线就是 **Safari 16.4+**（用到 `@property` /
 *    `color-mix()` / cascade layers）。
 *
 * 所以基线内的东西不必降级（`Object.hasOwn` 15.4、`structuredClone` 15.4、
 * `Array.prototype.toSorted` 16.0 都在内），要拦的是**基线内仍然没有**的那些。
 *
 * ## 为什么用测试而不是文档
 *
 * 兼容性文档没人读，也没人知道自己读的是不是最新版；而一条会红的测试是
 * **可执行、可追溯、有人维护**的记录：谁写出基线外写法，CI 当场告诉他
 * 哪个文件哪一行、为什么被禁、基线是多少。
 *
 * ## 判定口径
 *
 * 每条条目只回答一个问题：「Safari 16.4 有没有」。`note` 里的具体版本号只用于
 * 解释原因（本文档写作时按 MDN 记忆填写，未联网复核）；若某个版本号后来被修正，
 * **不影响门禁判定**——只要它晚于 16.4，条目就该留着。
 *
 * ## 本轮静态审计结论（跟着代码走，不另建文档）
 *
 * 被扫文件：`ui-tools/*.ts`、`store/ui-tools.ts`、`hooks/use-ui-tool-host.ts`、
 * `handlers/ui-action-handler.ts`、`components/UiActionBanner.tsx`、
 * `components/UiToolHost.tsx`、`streaming.ts`。结论：
 *
 * 1. 上面的 denylist：**0 处命中**（它已经落到断言里，不是一次性结论）。
 * 2. 唯一「看起来可疑但在基线内」的写法：`Object.hasOwn`（Safari 15.4）——
 *    `ui-tools/registry.ts:50/55/71/76` 的四处守卫，**不要**因为「怕旧 Safari」改写。
 * 3. 其余主机 API 都是 ES2019 之前就有的：`TextDecoder`、`URLSearchParams`、
 *    `CustomEvent`、`window.setTimeout/clearTimeout`、`window.location`、
 *    `Object.fromEntries`、`Set` / `Map`——不必为本轮浏览器手测另做准备。
 * 4. 一处基线外但**有降级**：`copilot.css:8` 的 `view-transition-name`（Safari 18+）。
 *    JS 侧 `transitions.ts` 的 `withViewTransition` 已特性检测 `document.startViewTransition`，
 *    不支持就直接执行回调；CSS 不认识该属性时只是不播动画，不影响功能。故不加进 denylist。
 * 5. `app/preload.ts:82` 的 `requestIdleCallback` 已经是「特性检测 + setTimeout 回退」，
 *    且不在 copilot 域内——它就是本文件 note 里推荐的那种写法本身。
 */

import { readdirSync, readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

/** 扫描根：本测试与被打扫的产品代码同目录（`src/features/copilot`） */
const COPILOT_ROOT = path.dirname(fileURLToPath(import.meta.url))

/** 扫描的扩展名：CSS 也算——兼容面不止 JS API，样式特性同样会让页面在旧 Safari 上错版 */
const SCANNED_EXTENSIONS: readonly string[] = ['.ts', '.tsx', '.css']

interface SafariDeniedApi {
  /** 命中时打印的名字（报错信息第一关键词） */
  name: string
  /** 命中形态；CSS 用 `i` 标志容下大小写与空格的等价写法 */
  pattern: RegExp
  /** 一行版本说明：Safari 为什么不支持 / 基线是多少（写在声明处，读者不必再查） */
  note: string
}

const SAFARI_DENIED_APIS: readonly SafariDeniedApi[] = [
  {
    name: 'requestIdleCallback',
    pattern: /\brequestIdleCallback\b/,
    note: 'Safari 至今未实现（WebKit bug 202256，Chrome/Firefox 才有）；要用就照 src/app/preload.ts 的 whenIdle 写 setTimeout 回退',
  },
  {
    name: 'scheduler.postTask',
    pattern: /\bscheduler\s*\.\s*postTask\b/,
    note: 'Scheduler API 仅 Chromium 有（Safari 16.4~18 均未实现）；等价的延时用 setTimeout / queueMicrotask',
  },
  {
    name: 'Array.fromAsync',
    pattern: /\bArray\s*\.\s*fromAsync\b/,
    note: 'Safari 18.4 才加入（基线 16.4 没有）；用 `for await` 手动 push',
  },
  {
    name: 'Promise.withResolvers',
    pattern: /\bPromise\s*\.\s*withResolvers\b/,
    note: 'Safari 17.4 才加入（基线 16.4 没有）；用 `new Promise((resolve, reject) => …)` 把两个函数存进变量',
  },
  {
    name: 'Object.groupBy',
    pattern: /\bObject\s*\.\s*groupBy\b/,
    note: 'Safari 17.4 才加入（基线 16.4 没有）；用 reduce 自己分组',
  },
  {
    name: 'Map.groupBy',
    pattern: /\bMap\s*\.\s*groupBy\b/,
    note: 'Safari 17.4 才加入（基线 16.4 没有）；同上，reduce 分组',
  },
  {
    name: 'Promise.try',
    pattern: /\bPromise\s*\.\s*try\b/,
    note: 'Safari 18.2 才加入（基线 16.4 没有）；用 `new Promise((resolve) => resolve(fn()))` 或 try/catch',
  },
  {
    name: 'URL.parse()',
    pattern: /\bURL\s*\.\s*parse\s*\(/,
    note: 'Safari 18.4 才加入（基线 16.4 没有）；用 `new URL()` + try/catch 判断可解析',
  },
  {
    name: 'URL.canParse()',
    pattern: /\bURL\s*\.\s*canParse\s*\(/,
    note: 'Safari 17.0 才加入（基线 16.4 没有）；同上，`new URL()` + try/catch',
  },
  {
    name: 'text-wrap: balance',
    pattern: /\btext-wrap\s*:\s*balance\b|\btext-balance\b/i,
    note: 'Safari 17.5 才支持（基线 16.4 没有），Tailwind 的 `text-balance` 编译出的正是它；标题换行用普通换行或手动 `<br>`',
  },
  {
    name: 'scrollbar-gutter',
    pattern: /\bscrollbar-gutter\b/i,
    note: 'Safari 至今未实现（Chrome 94 / Firefox 97 才有）；避免滚动条出现/消失引起的横跳要另想办法（固定容器宽度、overflow-y: scroll）',
  },
  {
    name: 'field-sizing',
    pattern: /\bfield-sizing\b/i,
    note: 'Safari 18.4 才支持（基线 16.4 没有）；自适应高度的输入框用「隐藏 measure 元素 + 写 height」的既有做法',
  },
]

/** 未扫目录/文件名片段：测试会故意写出被禁写法（本文件自己就含全部关键字） */
function isExcluded(relPath: string): boolean {
  const segments = relPath.split('/')
  if (segments.includes('__tests__')) return true
  if (segments[0] === 'dev') return true
  return /\.test\.[cm]?[jt]sx?$/.test(relPath)
}

/** 产品代码的相对路径清单（`/` 分隔，稳定排序，便于断言与报错阅读） */
function productFiles(): string[] {
  return readdirSync(COPILOT_ROOT, { recursive: true, encoding: 'utf8' })
    .map((relPath) => relPath.split(path.sep).join('/'))
    .filter((relPath) => SCANNED_EXTENSIONS.some((ext) => relPath.endsWith(ext)))
    .filter((relPath) => !isExcluded(relPath))
    .sort()
}

interface SafariViolation {
  file: string
  /** 1 起；与编辑器行号一致，复制进搜索框就能跳到事发处 */
  line: number
  api: string
  note: string
}

/** 一段源码里的全部违规（纯函数：门禁本身也要能被「故意造红」验证） */
function scanSource(file: string, source: string): SafariViolation[] {
  const violations: SafariViolation[] = []
  source.split('\n').forEach((text, index) => {
    for (const denied of SAFARI_DENIED_APIS) {
      if (denied.pattern.test(text)) {
        violations.push({ file, line: index + 1, api: denied.name, note: denied.note })
      }
    }
  })
  return violations
}

/** 断言失败时原样打印的清单：文件:行 + API 名 + Safari 版本说明 */
function formatViolations(violations: readonly SafariViolation[]): string {
  return [
    `发现 ${violations.length} 处 Safari 16.4 基线外的写法：`,
    ...violations.map((v) => `  ${v.file}:${v.line}  ${v.api} —— ${v.note}`),
  ].join('\n')
}

describe('Safari 16.4 兼容门禁', () => {
  it('扫描范围是产品代码（空扫会让门禁永远绿，所以先钉住扫到了什么）', () => {
    const files = productFiles()
    expect(files.length).toBeGreaterThan(150)
    // 三类必须命中：纯逻辑层、组件层、CSS（漏掉任何一类都是门禁残缺）
    expect(files).toContain('streaming.ts')
    expect(files).toContain('ui-tools/routes.ts')
    expect(files).toContain('components/UiActionBanner.tsx')
    expect(files).toContain('copilot.css')
    // 测试与 dev 探针不在范围内（前者故意写被禁写法，后者不进 prod 包）
    expect(files.filter((f) => f.includes('.test.'))).toEqual([])
    expect(files.filter((f) => f.startsWith('dev/'))).toEqual([])
  })

  it('产品代码里没有基线外的 API / CSS 特性', () => {
    const violations = productFiles().flatMap((file) =>
      scanSource(file, readFileSync(path.join(COPILOT_ROOT, file), 'utf8')),
    )
    expect(violations, formatViolations(violations)).toEqual([])
  })

  it('门禁本身有效：故意写一行 requestIdleCallback 会被抓住并报出行号', () => {
    const hits = scanSource('fake.ts', "const id = window.requestIdleCallback(cb, { timeout: 3000 })\n")
    expect(hits).toHaveLength(1)
    expect(hits[0]).toMatchObject({ file: 'fake.ts', line: 1, api: 'requestIdleCallback' })
    expect(formatViolations(hits)).toContain('fake.ts:1  requestIdleCallback')
  })

  it('CSS 的等价写法也要抓住（空格与大小写不是漏网理由）', () => {
    expect(scanSource('fake.css', '.title { text-wrap:balance }')).toHaveLength(1)
    expect(scanSource('fake.css', '.title { TEXT-WRAP: BALANCE }')).toHaveLength(1)
    expect(scanSource('fake.css', '.pane { scrollbar-gutter: stable }')).toHaveLength(1)
    // 相邻但不相关的写法不该误报（`white-space` 是基线内的老写法，与 `text-wrap` 无关）
    expect(scanSource('fake.css', '.title { white-space: nowrap }')).toEqual([])
  })

  it('每一条都写清了原因（空 note 等于让后来人只看到「不许用」）', () => {
    for (const denied of SAFARI_DENIED_APIS) {
      expect(denied.note.length, `缺版本说明：${denied.name}`).toBeGreaterThan(20)
    }
  })
})
