/**
 * Content-Ops Types Tests
 * 测试内容运营模块的标签映射和选项常量
 */

import {
  HOT_TOPIC_SOURCE_LABEL,
  VOICE_OPTIONS,
  STATUS_LABEL,
  REVIEW_STATUS_LABEL,
  MODE_LABEL,
  OUTPUT_MODE_LABEL,
  CONTENT_SOURCE_LABEL,
} from '../types'
import type { TaskStatus, ReviewStatus, TaskMode, OutputMode, ContentSource } from '../types'

const TASK_STATUS_VALUES: TaskStatus[] = ['pending', 'queued', 'running', 'completed', 'failed', 'cancelled']
const REVIEW_STATUS_VALUES: ReviewStatus[] = ['draft', 'approved', 'rejected']
const TASK_MODE_VALUES: TaskMode[] = ['search', 'direct']
const OUTPUT_MODE_VALUES: OutputMode[] = ['narration', 'discussion', 'both']
const CONTENT_SOURCE_VALUES: ContentSource[] = ['article', 'discussion']

describe('HOT_TOPIC_SOURCE_LABEL', () => {
  it('defines labels for all known sources', () => {
    expect(HOT_TOPIC_SOURCE_LABEL.toutiao).toBe('头条')
    expect(HOT_TOPIC_SOURCE_LABEL.baidu).toBe('百度')
    expect(HOT_TOPIC_SOURCE_LABEL.douyin).toBe('抖音')
    expect(HOT_TOPIC_SOURCE_LABEL['36kr']).toBe('36氪')
    expect(HOT_TOPIC_SOURCE_LABEL.thepaper).toBe('澎湃')
    expect(HOT_TOPIC_SOURCE_LABEL.legaltech).toBe('法律科技')
  })

  it('has 6 entries', () => {
    expect(Object.keys(HOT_TOPIC_SOURCE_LABEL)).toHaveLength(6)
  })
})

describe('VOICE_OPTIONS', () => {
  it('defines 4 voice options', () => {
    expect(VOICE_OPTIONS).toHaveLength(4)
  })

  it('each option has value and label', () => {
    for (const opt of VOICE_OPTIONS) {
      expect(opt.value).toBeTruthy()
      expect(opt.label).toBeTruthy()
      expect(opt.value).toBe(opt.label)
    }
  })

  it('contains expected voices', () => {
    const values = VOICE_OPTIONS.map((v) => v.value)
    expect(values).toContain('冰糖')
    expect(values).toContain('茉莉')
    expect(values).toContain('苏打')
    expect(values).toContain('白桦')
  })
})

describe('STATUS_LABEL', () => {
  it('maps every TaskStatus to a non-empty string', () => {
    for (const val of TASK_STATUS_VALUES) {
      expect(STATUS_LABEL[val]).toBeTruthy()
      expect(typeof STATUS_LABEL[val]).toBe('string')
    }
  })

  it('has 6 entries', () => {
    expect(Object.keys(STATUS_LABEL)).toHaveLength(6)
  })
})

describe('REVIEW_STATUS_LABEL', () => {
  it('maps every ReviewStatus to a non-empty string', () => {
    for (const val of REVIEW_STATUS_VALUES) {
      expect(REVIEW_STATUS_LABEL[val]).toBeTruthy()
    }
  })

  it('has 3 entries', () => {
    expect(Object.keys(REVIEW_STATUS_LABEL)).toHaveLength(3)
  })
})

describe('MODE_LABEL', () => {
  it('maps every TaskMode to a non-empty string', () => {
    for (const val of TASK_MODE_VALUES) {
      expect(MODE_LABEL[val]).toBeTruthy()
    }
  })

  it('has 2 entries', () => {
    expect(Object.keys(MODE_LABEL)).toHaveLength(2)
  })
})

describe('OUTPUT_MODE_LABEL', () => {
  it('maps every OutputMode to a non-empty string', () => {
    for (const val of OUTPUT_MODE_VALUES) {
      expect(OUTPUT_MODE_LABEL[val]).toBeTruthy()
    }
  })

  it('has 3 entries', () => {
    expect(Object.keys(OUTPUT_MODE_LABEL)).toHaveLength(3)
  })
})

describe('CONTENT_SOURCE_LABEL', () => {
  it('maps every ContentSource to a non-empty string', () => {
    for (const val of CONTENT_SOURCE_VALUES) {
      expect(CONTENT_SOURCE_LABEL[val]).toBeTruthy()
    }
  })

  it('has 2 entries', () => {
    expect(Object.keys(CONTENT_SOURCE_LABEL)).toHaveLength(2)
  })
})
