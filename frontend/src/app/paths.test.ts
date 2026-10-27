/**
 * app/paths 单测（node）。
 *
 * 这些函数的存在理由就是「路由字面量只能有一份」：`/projects/:id/review/:taskId`
 * 曾在 Reader 与 ContractFileOverlays 里各手拼一遍，路由一改就静默断链。所以这里
 * 断言的是**实际拼出来的字符串**，而不是「函数被调用过」。
 */
import { describe, expect, it } from 'vitest'

import {
  loginPath,
  materialPrep,
  materialPrepDetail,
  projectDetail,
  projectList,
  projectReview,
  publicUpload,
  ROUTES,
  settings,
} from './paths'

describe('paths：项目类路径', () => {
  it('projectReview 拼出复审台路径（两处调用方共用同一条）', () => {
    expect(projectReview(393, 'task-1')).toBe('/projects/393/review/task-1')
  })

  it('projectDetail 拼出详情页路径', () => {
    expect(projectDetail(393)).toBe('/projects/393')
  })

  it('projectDetail 缺 id 时回落到项目列表，而不是拼出 /projects/undefined', () => {
    expect(projectDetail(undefined)).toBe('/projects')
    expect(projectDetail(null)).toBe('/projects')
  })

  it('projectList 就是项目列表路由', () => {
    expect(projectList()).toBe(ROUTES.projects)
  })
})

describe('paths：材料预处理与公开入口', () => {
  it('材料预处理列表与详情', () => {
    expect(materialPrep()).toBe('/material-prep')
    expect(materialPrepDetail(12)).toBe('/material-prep/12')
  })

  it('客户上传链接原样透传 token（后端签发，不做 URL 编码）', () => {
    expect(publicUpload('abc.def-123')).toBe('/u/abc.def-123')
  })

  it('登录页与设置页', () => {
    expect(loginPath()).toBe('/login')
    expect(settings()).toBe('/settings')
  })
})
