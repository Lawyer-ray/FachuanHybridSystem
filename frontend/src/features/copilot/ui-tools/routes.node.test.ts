import { describe, expect, it } from 'vitest'

import { ROUTES, materialPrepDetail, publicUpload } from '@/app/paths'
import { MATERIAL_PREP_STAGES, pathForMaterialPrepStage, pathForNavigate } from './routes'

describe('pathForNavigate：放行站内白名单路径', () => {
  it.each([
    ['/material-prep', '/material-prep'],
    ['/material-prep?stage=todo', '/material-prep?stage=todo'],
    ['/material-prep?stage=filed', '/material-prep?stage=filed'],
    ['/projects', '/projects'],
    [materialPrepDetail(393), '/material-prep/393'],
    ['/projects/393/review/task-20261127-abc', '/projects/393/review/task-20261127-abc'],
    ['/assistant', '/assistant'],
    ['/assistant/3f2b8c1e-0000-4000-8000-000000000000', '/assistant/3f2b8c1e-0000-4000-8000-000000000000'],
    ['/bank-litigation/17', '/bank-litigation/17'],
    ['/settings', '/settings'],
    ['/', '/'],
    // 只做前转的旧路径仍在 ROUTES 里，模型跳过去只是被重定向一次，不算越界
    [ROUTES.inbox, ROUTES.inbox],
  ])('%s → %s', (input, expected) => {
    expect(pathForNavigate(input)).toBe(expected)
  })

  it('两端的空白先 trim 再匹配（`" /material-prep "` 在浏览器里仍是有效地址）', () => {
    expect(pathForNavigate('  /material-prep?stage=todo  ')).toBe('/material-prep?stage=todo')
  })
})

describe('pathForNavigate：拒绝外站与协议', () => {
  it.each([
    ['绝对 http 地址', 'http://evil.example/material-prep'],
    ['绝对 https 地址', 'https://evil.example/x'],
    ['协议相对地址', '//evil.example/x'],
    ['javascript: 伪协议', 'javascript:alert(1)'],
    ['大小写变体伪协议', 'JaVaScRiPt:alert(document.cookie)'],
    ['data: 伪协议', 'data:text/html,<script>alert(1)</script>'],
  ])('%s 一律拒', (_label, input) => {
    expect(pathForNavigate(input)).toBeNull()
  })
})

describe('pathForNavigate：拒绝路径穿越与危险字符', () => {
  it.each([
    ['相对穿越', '../admin'],
    ['夹在中间的双点', '/material-prep/../admin'],
    ['编码穿越', '/projects/..%2fadmin'],
    ['编码双点', '/projects/%2e%2e'],
    ['反斜杠（浏览器等价于 /）', '/\\evil.example/x'],
    ['夹在中间的反斜杠', '/material-prep\\..\\admin'],
    ['锚点', '/material-prep#top'],
    ['内部空白', '/material prep'],
    ['tab 字符', '/material-prep\t?stage=todo'],
  ])('%s 一律拒', (_label, input) => {
    expect(pathForNavigate(input)).toBeNull()
  })
})

describe('pathForNavigate：拒绝未登录态页面与链接即凭证的公开页', () => {
  it('登录页', () => {
    expect(pathForNavigate(ROUTES.login)).toBeNull()
  })

  it('社交登录回调页', () => {
    expect(pathForNavigate(ROUTES.socialCallback)).toBeNull()
  })

  it('客户上传页（/u/:token，链接即凭证）', () => {
    expect(pathForNavigate(publicUpload('tok_secret_123'))).toBeNull()
  })
})

describe('pathForNavigate：拒绝非字符串、空串与不在路由表里的地址', () => {
  it.each([42, true, null, undefined, {}, ['/material-prep']])('非字符串 %s', (raw) => {
    expect(pathForNavigate(raw)).toBeNull()
  })

  it.each(['', '   '])('空串/纯空白 %s', (raw) => {
    expect(pathForNavigate(raw)).toBeNull()
  })

  it.each(['/admin', '/material-prep/', '/material-prep/393/extra', '/u'])('不在白名单里的 %s', (raw) => {
    expect(pathForNavigate(raw)).toBeNull()
  })
})

describe('pathForNavigate：query 只认材料预处理页的 stage', () => {
  it.each([
    ['未知阶段', '/material-prep?stage=archived'],
    ['重复 stage', '/material-prep?stage=todo&stage=done'],
    ['夹带 message 深链接参数', '/material-prep?stage=todo&message=12'],
    ['别的页面带 query', '/projects?stage=todo'],
    ['空 stage', '/material-prep?stage='],
  ])('%s 一律拒', (_label, input) => {
    expect(pathForNavigate(input)).toBeNull()
  })
})

describe('pathForMaterialPrepStage：切阶段保深链接、inbox 不写冗余参数', () => {
  it('保住当前页的 ?message=（深链接直达某条消息）', () => {
    expect(pathForMaterialPrepStage('todo', '/material-prep?message=12')).toBe(
      '/material-prep?message=12&stage=todo',
    )
  })

  it('已有 stage 时原地改写，不叠加', () => {
    expect(pathForMaterialPrepStage('done', '/material-prep?stage=todo')).toBe('/material-prep?stage=done')
  })

  it('inbox 是默认阶段，不写 stage 参数', () => {
    expect(pathForMaterialPrepStage('inbox', '/material-prep?stage=todo&message=12')).toBe(
      '/material-prep?message=12',
    )
  })

  it('不在材料预处理页时也能生成目标地址（动作本身就是跳过去）', () => {
    expect(pathForMaterialPrepStage('filed', '/projects/393')).toBe('/material-prep?stage=filed')
  })

  it.each(['archived', '', null, 3, {}])('非法 stage %s 返回 null', (raw) => {
    expect(pathForMaterialPrepStage(raw, '/material-prep')).toBeNull()
  })

  it('四阶段顺序即漏斗顺序（清单里的 enum 必须与本文件逐个相同，见 registry.node.test.ts）', () => {
    expect([...MATERIAL_PREP_STAGES]).toEqual(['inbox', 'todo', 'done', 'filed'])
  })
})
