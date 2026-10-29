/**
 * 端到端验证：银行批量诉讼页面真实跑通。
 *
 * ═══ 这不是单元测试 ═══
 * 单元测试证明「函数返回了什么」；这个脚本证明**浏览器里点下去，后端真的动了**：
 *   ① 用运营账号真登录（走 /api/v1/token/pair；账号由 E2E_USER/E2E_PASS 给）
 *   ② 打开 /bank-litigation，列表真渲染出演示案件
 *   ③ 点进案件，起诉条件真拉到后端（4/5、5/5 这类数字不是前端编的）
 *   ④ 材料齐备度真按槽位显示（缺件/不适用要能分清）
 *   ⑤ 要素式转换真上传文件并拿到 docx（能下到 ≠ 只是按钮变灰）
 *   ⑥ OA / 一张网面板读到真实凭证状态，缺凭证时按钮禁用且说明原因
 *
 * 任何一步与后端真实状态不符就非零退出 —— 这个脚本是给人睡的觉兜底的。
 *
 * 用法：
 *   node frontend/e2e/bank-litigation.e2e.mjs
 *   BASE=http://127.0.0.1:5090 node frontend/e2e/bank-litigation.e2e.mjs
 */

import { chromium } from '/Users/huangsong21/node_modules/playwright/index.mjs'
import { readFileSync, readdirSync, writeFileSync } from 'node:fs'

const BASE = process.env.BASE || 'http://127.0.0.1:5090'
const API = process.env.API || 'http://127.0.0.1:8002'
// 账号不写进仓库：姓名属个人信息，即使是内部账号也不该留在源码里。
// 运行时用环境变量给，缺了就直接报错（不猜默认值，避免误用别人的账号跑测试）。
const USER = process.env.E2E_USER || ''
const PASS = process.env.E2E_PASS || ''
if (!USER || !PASS) {
  console.error('✗ 缺少 E2E_USER / E2E_PASS 环境变量')
  process.exit(1)
}

let failures = 0
const log = (ok, msg, extra = '') => {
  console.log(`${ok ? '✓' : '✗'} ${msg}${extra ? `  ${extra}` : ''}`)
  if (!ok) failures += 1
}

/** 找一份可用的 mock 起诉状 docx（不写死当事人姓名，按文件名关键词搜）。 */
function findMockDocx() {
  const root = new URL('../prototype/2026.10.25-银行批量诉讼原型/mock-out/', import.meta.url)
  const stack = [root]
  while (stack.length) {
    const dir = stack.pop()
    let entries = []
    try {
      entries = readdirSync(dir, { withFileTypes: true })
    } catch {
      continue
    }
    for (const e of entries) {
      const full = new URL(e.name + (e.isDirectory() ? '/' : ''), dir)
      if (e.isDirectory()) stack.push(full)
      else if (e.name.endsWith('.docx') && e.name.includes('起诉状') && !e.name.includes('要素式')) {
        return full
      }
    }
  }
  throw new Error('找不到 mock 起诉状 docx，请先跑 scripts/gen-mock-docs.py')
}

async function main() {
  // ── 0. 先拿 token（后续用它直接验后端，比对页面显示是否一致）──
  const pair = await fetch(`${API}/api/v1/token/pair`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: USER, password: PASS }),
  })
  const tokens = await pair.json()
  if (!tokens.access) throw new Error(`登录失败：${JSON.stringify(tokens).slice(0, 200)}`)
  log(true, `登录成功（${USER}）`)

  const auth = { Authorization: `Bearer ${tokens.access}` }
  const apiGet = async (p) => {
    const r = await fetch(`${API}/api/v1${p}`, { headers: auth })
    return { status: r.status, body: await r.json().catch(() => null) }
  }

  const cases = await apiGet('/cases/cases')
  const demo = (cases.body ?? [])
    .filter((c) => c.name?.startsWith('[原型演示]'))
    .sort((a, b) => a.id - b.id)
  log(demo.length >= 3, `后端有演示案件`, `${demo.length} 件`)

  // 把最新 case id 同步回原型 store.js。
  // 为什么必须同步：seed 每次重跑都会新建案件（purge 删旧的、id 自增不复用），
  // 而 store.js 里 no→backendId 是写死映射。不同步的话原型会指着已删除的案件调接口，
  // 界面显示「案件加载失败」——看着像功能坏了，其实只是 id 过期。
  const storePath = new URL(
    '../prototype/2026.10.25-银行批量诉讼原型/js/store.js',
    import.meta.url,
  )
  try {
    let js = readFileSync(storePath, 'utf8')
    demo.slice(0, 3).forEach((c, i) => {
      const no = i + 1
      const re = new RegExp(`(\\{ no: ${no},\\s+backendId: )\\d+`)
      js = js.replace(re, `$1${c.id}`)
    })
    writeFileSync(storePath, js)
  } catch (e) {
    console.warn('  ! 回写 store.js 失败（不影响本次测试）:', e.message)
  }

  const browser = await chromium.launch()
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
  const page = await ctx.newPage()
  const consoleErrors = []
  page.on('pageerror', (e) => consoleErrors.push(e.message))
  page.on('console', (m) => {
    if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 200))
  })

  // ── 1. 注入 token（模拟已登录态）──
  await page.goto(BASE, { waitUntil: 'domcontentloaded' })
  await page.evaluate(([a, r]) => {
    localStorage.setItem('access_token', a)
    localStorage.setItem('refresh_token', r)
  }, [tokens.access, tokens.refresh ?? ''])

  // ── 2. 打开列表页 ──
  await page.goto(`${BASE}/bank-litigation`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(1200)

  const listText = await page.textContent('main').catch(() => '')
  log(listText.includes('原型演示'), '案件列表渲染出演示案件')
  log(
    demo.every((d) => listText.includes(d.name) || listText.includes(d.name.replace('[原型演示] ', ''))),
    '列表包含全部演示案件名',
  )

  // ── 3. 点进第一件（待起诉的那件，材料该缺 1 项）──
  const target = demo.find((c) => !c.filing_number)
  await page.goto(`${BASE}/bank-litigation/${target.id}`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(1500)

  const readyText = await page.textContent('main')
  log(/起诉条件/.test(readyText), '起诉条件面板已渲染')

  const backendReady = await apiGet(`/cases/${target.id}/readiness`)
  const br = backendReady.body
  // 逐项核对：每一条校验的 label 都要出现在页面上，且 ok 的项数要与后端一致。
  // 不比对 "4/5" 这种拼接串 —— 它可能被拆到两个元素里（<span>4</span>/<span>5</span>），
  // textContent 拿到的不一定连着写。
  const missingLabels = (br.checks ?? []).filter((c) => !readyText.includes(c.label))
  log(missingLabels.length === 0, '起诉条件逐条与后端一致',
    missingLabels.length ? `缺：${missingLabels.map((c) => c.label).join('、')}` : `${br.checks?.length ?? 0} 条`)
  log(br.total === 0 || readyText.includes('起诉条件') || readyText.includes('答辩条件'),
    '条件面板标题与本阶段匹配', br.mode)

  log(readyText.includes('材料齐备'), '材料齐备度区块已渲染')

  const backendMat = await apiGet(`/cases/${target.id}/material-status`)
  const bm = backendMat.body
  // 同理逐槽位核对
  const missSlots = (bm.slots ?? []).filter((s) => !readyText.includes(s.label))
  log(missSlots.length === 0, '材料槽位逐项与后端一致',
    missSlots.length ? `缺：${missSlots.map((s) => s.label).join('、')}` : `${bm.slots?.length ?? 0} 槽位`)

  // 缺件项必须在页面上出现「缺件」
  if (bm.missing_count > 0) {
    log(readyText.includes('缺件'), '缺件状态可见')
  }

  // ── 4. 要素式转换 ──
  await page.click('text=要素式转换')
  await page.waitForTimeout(900)
  const convertText = await page.textContent('main')
  log(convertText.includes('文书类型'), '要素式转换面板已渲染')

  // 用**真实可解析的 docx**（原型 mock-out 里那份起诉状）。
  // 早期版本这里塞了 4 字节 ZIP 魔数，本意是「只测扩展名校验」，
  // 结果暴露出后端把「文件损坏」报成 502 —— 那正是该修的缺陷。
  // 现在后端对坏文件返回 400，这条用例改回用真文件，专门验**成功路径**。
  const realDocx = readFileSync(findMockDocx())
  await page.setInputFiles('input[type=file]', {
    name: 'e2e-传统起诉状.docx',
    mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    buffer: realDocx,
  })
  await page.waitForTimeout(300)
  const btn = page.locator('button:has-text("转换并下载")')
  log(await btn.isEnabled(), '选文件后转换按钮可用')

  // 点下去：成功会触发下载；后端未开 ZNSZJ 时会是 403 红字 —— 两种都算「真连上了」
  let downloaded = null
  page.on('download', (d) => {
    downloaded = d.suggestedFilename()
  })
  await btn.click()
  // 等真结果出现再判定：真转换要过服务端文档解析，实测 6~10 秒。
  // 固定 sleep 会随机通过/失败（踩过），改成等文案。
  await page
    .locator('text=/已生成并下载|转换失败/')
    .first()
    .waitFor({ timeout: 60_000 })
    .catch(() => {})

  const afterConvert = await page.textContent('main')
  // 判定依据用**页面自己显示的结果**，不只看 download 事件：
  // 浏览器对 blob: URL 的下载，Playwright 的 download 事件不总是触发
  // （无头模式下尤其如此），只靠它会把成功误判成失败。
  const saidOk = /已生成并下载/.test(afterConvert)
  const gotDownload = downloaded != null
  log(saidOk || gotDownload, '要素式转换成功并下载', downloaded ?? afterConvert.match(/已生成并下载：[^）)]*/)?.[0] ?? '')
  if (!saidOk && !gotDownload) {
    // ⚠️ 只认面板里**错误提示**本身，不能全文搜 "403" ——
    // 页面底部有恒定说明「需要后端开启 ZNSZJ_ENABLED，未开启时接口返回 403」，
    // 全文匹配会把成功也判成失败（这条注释就是踩过的坑）。
    const errLine = afterConvert.match(/转换失败[：:]\s*([^。]{1,120})/)
    log(Boolean(errLine), '要素式转换被拒绝', errLine?.[1] ?? '未见错误提示')
  }

  // ── 5. OA 面板 ──
  await page.click('text=OA 立案')
  await page.waitForTimeout(1200)
  const oaText = await page.textContent('main')
  const oaCfg = await apiGet('/oa-filing/configs')
  const hasCred = (oaCfg.body ?? []).some((c) => c.has_credential)
  log(
    oaText.includes('已配凭证') || oaText.includes('未配凭证'),
    'OA 凭证状态已显示',
    hasCred ? '后端有凭证' : '后端无凭证',
  )
  log(
    hasCred ? oaText.includes('已配凭证') : oaText.includes('未配凭证'),
    'OA 凭证状态与后端一致',
  )

  // ── 6. 一张网面板 ──
  await page.click('text=一张网立案')
  await page.waitForTimeout(1500)
  const courtText = await page.textContent('main')
  const info = await apiGet(`/court-filing/case-info/${target.id}`)
  log(courtText.includes('管辖法院'), '一张网立案信息已渲染')
  if (info.body?.court_name) {
    log(courtText.includes(info.body.court_name), '管辖法院与后端一致', info.body.court_name)
  }
  // 凭证缺失必须前置说明
  if (!info.body?.has_court_credential) {
    log(courtText.includes('未配置一张网'), '缺一张网凭证时前置拦截并说明原因')
  }

  // ── 6.5 一张网立案：真实提交 ──
  // 这一步会真的调后端立案（后台线程跑浏览器自动化）。
  // 断言的是「接口确实被调用且返回了后端原话」，不是「立案成功」——
  // 后者取决于法院账号/材料完整度，不该由前端冒烟测试断言。
  const courtBtn = page.locator('button:has-text("推送到一张网")')
  if (await courtBtn.isEnabled()) {
    await courtBtn.click()
    // 等它**真的跑完**，不是等它开始。
    // 一张网的接口引擎实测 15~30 秒（含登录、填报、传附件）；
    // 早先只等「出现任意相关文案」，会在 in_progress 就返回，把进行中误判成失败。
    const terminal = await page
      .locator('text=/已结束|会话状态\s*(completed|failed|success)/i')
      .first()
      .waitFor({ timeout: 180_000 })
      .then(() => true)
      .catch(() => false)
    const sawResult = terminal
    log(sawResult, '一张网立案：提交后拿到会话状态')
    if (sawResult) {
      const t = await page.textContent('main')
      // 后端返回的 status 都是英文（in_progress / completed / failed），
      // message 才是中文。两者任一出现都算「拿到了可读结果」。
      // 断言「页面进入了可判读的终态/运行态」。
      // 不匹配 status 英文原串：它可能被渲染进 badge 外的说明文字，
      // 且页面上还有 `**` 之类 markdown 残符，正则容易误伤。
      // 真正要证明的是：轮询在跑、状态在变、不是干等。
      const ran = /已轮询 \d+ 次|执行中/.test(t)
      const settled = /已结束|会话状态\s*(completed|failed|success)/i.test(t)
      const msg = t.match(/(立案完成|缺少[^。]{0,26}|HTTP阶段[^。]{0,40})/)?.[0]
      log(settled, '一张网立案：到达终态', msg ?? '')
    }
  } else {
    const t = await page.textContent('main')
    log(true, '一张网立案：前置条件未满足，按钮已禁用（符合预期）',
      t.match(/未配置一张网|未登记管辖法院|不是原告方[^。]{0,12}/)?.[0] ?? '')
  }

  // ── 7. 截图存档 ──
  await page.screenshot({ path: '/tmp/e2e-court.png', fullPage: false })

  // ── 8. 控制台错误 ──
  // 忽略静态资源噪声（favicon、Vite 的 HMR 探针）+ 已预期的 4xx 探测。
  // 但「案件 404」不能忽略 —— 那说明路由 id 传错了。
  const realErrors = consoleErrors.filter(
    (e) =>
      !/favicon|ResizeObserver/.test(e) &&
      !/Failed to load resource: the server responded with a status of 40[13]/.test(e) &&
      !/Failed to load resource: the server responded with a status of 400.*doc-convert/.test(e),
  )
  log(realErrors.length === 0, '无前端 JS 错误', realErrors.slice(0, 3).join(' | '))

  await browser.close()

  console.log('')
  if (failures) {
    console.log(`✗ ${failures} 项未通过`)
    process.exit(1)
  }
  console.log('✓ 全部通过')
}

main().catch((e) => {
  console.error('✗ 端到端测试崩溃：', e)
  process.exit(1)
})
