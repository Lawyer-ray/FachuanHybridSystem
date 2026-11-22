/**
 * 工具返回原文归一化：拆 MCP 信封 / 解转义 / JSON 美化 / HTML 兜底 / 收尾。
 *
 * 判据全部来自**真实落库形状**（只读查开发库 `agent_agentmessage` 的 679 条
 * `role='tool'` 消息），不是编的：`SEARCH_CASES` / `GET_REMINDER` 两条是逐字抄下来的
 * 真实 `content`，`web_search` / `fetch_url` 两条按真实样本剪短但保留形状（信封、
 * 双层转义、`<br>`、`\u3000`）。
 *
 * 这些规则改错了不会报错，只会「看起来正常但不对劲」：信封没拆 → 律师看到一大片
 * `{'type': 'text', ...`；解转义多解一层 → `C:\new` 变成换行；实体在剥标签之前解 →
 * `&lt;b&gt;` 被当成标签吃掉。
 */

import { describe, expect, it } from 'vitest'

import { formatToolContent } from './tool-content'

/** 真实样本：`search_cases`（237 字符，MCP 信封的 Python repr） */
const SEARCH_CASES =
  "{'type': 'text', 'text': '{\\n  \"total\": 1,\\n  \"items\": [\\n    {\\n      \"id\": 304,\\n      \"name\": \"张某诉某公司买卖合同纠纷\",\\n      \"case_type\": \"civil\",\\n      \"status\": \"在办\",\\n      \"cause_of_action\": \"买卖合同纠纷\"\\n    }\\n  ]\\n}'}"

/** `SEARCH_CASES` 归一化后应当长的样子（律师读得懂的形状） */
const SEARCH_CASES_TEXT = `{
  "total": 1,
  "items": [
    {
      "id": 304,
      "name": "张某诉某公司买卖合同纠纷",
      "case_type": "civil",
      "status": "在办",
      "cause_of_action": "买卖合同纠纷"
    }
  ]
}`

/** 真实样本：`get_reminder`（553 字符，同一种信封） */
const GET_REMINDER =
  "{'type': 'text', 'text': '{\\n  \"id\": 162,\\n  \"contract\": null,\\n  \"case\": null,\\n  \"case_log\": null,\\n  \"reminder_type\": \"hearing\",\\n  \"reminder_type_label\": \"开庭\",\\n  \"content\": \"开庭：开庭时间2026年11月23日下午15时00分\",\\n  \"metadata\": {\\n    \"source\": \"document_recognition\",\\n    \"task_id\": 20,\\n    \"source_id\": \"task:20:candidate:32\"\\n  },\\n  \"due_at\": \"2026-11-23T15:00:00+08:00\",\\n  \"is_completed\": false,\\n  \"completed_at\": null,\\n  \"created_at\": \"2026-10-20T14:28:13.173033+08:00\",\\n  \"updated_at\": \"2026-10-20T14:28:13.173037+08:00\",\\n  \"created_by\": 1\\n}'}"

const GET_REMINDER_TEXT = `{
  "id": 162,
  "contract": null,
  "case": null,
  "case_log": null,
  "reminder_type": "hearing",
  "reminder_type_label": "开庭",
  "content": "开庭：开庭时间2026年11月23日下午15时00分",
  "metadata": {
    "source": "document_recognition",
    "task_id": 20,
    "source_id": "task:20:candidate:32"
  },
  "due_at": "2026-11-23T15:00:00+08:00",
  "is_completed": false,
  "completed_at": null,
  "created_at": "2026-10-20T14:28:13.173033+08:00",
  "updated_at": "2026-10-20T14:28:13.173037+08:00",
  "created_by": 1
}`

/** 真实 `list_cases`（5288 字符）的头部，`items` 剪到一条以保持合法 JSON */
const LIST_CASES =
  "{'type': 'text', 'text': '{\\n  \"total\": 16,\\n  \"returned\": 15,\\n  \"truncated\": true,\\n  \"items\": [\\n    {\\n      \"id\": 488,\\n      \"name\": \"李某诉某公司买卖合同纠纷\",\\n      \"case_number\": null,\\n      \"status\": \"在办\"\\n    }\\n  ]\\n}'}"

describe('MCP 信封（Python dict repr，单引号）', () => {
  it('search_cases 真实样本：拆掉信封 + 缩进两格，不再有 `{\'type\'` 与字面 \\n', () => {
    expect(formatToolContent(SEARCH_CASES)).toBe(SEARCH_CASES_TEXT)
    expect(formatToolContent(SEARCH_CASES)).not.toContain("'type'")
  })

  it('get_reminder 真实样本：值里的中文与 null 原样保留', () => {
    expect(formatToolContent(GET_REMINDER)).toBe(GET_REMINDER_TEXT)
  })

  it('list_cases 真实样本：三个统计字段 + items 数组', () => {
    const text = formatToolContent(LIST_CASES)
    expect(text).toContain('"truncated": true')
    expect(text).toContain('"name": "李某诉某公司买卖合同纠纷"')
    expect(text.split('\n')[0]).toBe('{')
  })

  it('信封里的值含转义单引号 `\\\'` 时不提前收尾', () => {
    const raw = `{'type': 'text', 'text': '{"name": "王\\'五"}'}`
    expect(formatToolContent(raw)).toBe(`{
  "name": "王'五"
}`)
  })

  it('只认 `type`/`text` 这一种形状：头部像但收尾有别的尾巴 → 不当信封', () => {
    const raw = `{'type': 'text', 'text': 'abc'} 后面还有一句`
    expect(formatToolContent(raw)).toBe(raw)
  })

  it('同一段文本不是信封时不动它（花括号当普通字符）', () => {
    expect(formatToolContent('{待补充}')).toBe('{待补充}')
  })
})

describe('纯 JSON（无信封，换行是字面 \\n 两个字符）', () => {
  it('get_current_user 真实形状：字面 \\n → 缩进两格', () => {
    const raw = '{\\n  "id": 1,\\n  "username": "测试账号",\\n  "phone": "138****0000"\\n}'
    expect(formatToolContent(raw)).toBe(`{
  "id": 1,
  "username": "测试账号",
  "phone": "138****0000"
}`)
  })

  it('本来就合法的 JSON 也缩进两格（单行 → 多行）', () => {
    expect(formatToolContent('{"cases":1}')).toBe(`{
  "cases": 1
}`)
    expect(formatToolContent('[1,2]')).toBe(`[
  1,
  2
]`)
  })

  it('空数组 / 空对象照原样（不留一堆换行）', () => {
    expect(formatToolContent('[]')).toBe('[]')
    expect(formatToolContent('{}')).toBe('{}')
  })

  it('合法 JSON 里的 `\\\\` 不能先被解转义：`C:\\\\new` 仍是文件名不是换行', () => {
    expect(formatToolContent('{"path":"C:\\\\new"}')).toBe(`{
  "path": "C:\\\\new"
}`)
  })
})

describe('JSON 字符串体（整段就是被引号包起来的正文）', () => {
  it('引号里的 JSON 继续下一次美化', () => {
    expect(formatToolContent('"{\\"a\\":1}"')).toBe(`{
  "a": 1
}`)
  })

  it('引号里是纯正文时取正文', () => {
    expect(formatToolContent('"合同有效，建议按第 5 条主张违约金"')).toBe('合同有效，建议按第 5 条主张违约金')
  })
})

describe('字面转义（信封内层与纯 JSON 都吃这一层）', () => {
  it(`\\n \\t \\r \\" \\\\ 还原成真字符`, () => {
    expect(formatToolContent('第一行\\n第二行')).toBe('第一行\n第二行')
    expect(formatToolContent('甲\\t乙')).toBe('甲\t乙')
    expect(formatToolContent('甲\\r\\n乙')).toBe('甲\r\n乙')
    expect(formatToolContent('他说：\\"可以\\"')).toBe('他说："可以"')
    expect(formatToolContent('路径 C:\\\\a')).toBe('路径 C:\\a')
  })

  it('未知转义原样保留（`\\u3000` 交给 JSON.parse，不给纯文本乱解）', () => {
    expect(formatToolContent('原文\\u3000保留')).toBe('原文\\u3000保留')
  })

  it('web_search 真实形状：信封里是**纯文本 + 字面 \\n**，剥信封后按真换行排版', () => {
    const raw =
      "{'type': 'text', 'text': '找到 5 条搜索结果：\\n\\n1. 山丹县人民政府-刑法\\n   链接: https://shandan.gov.cn/a.html\\n   摘要: 第二百八十六条之一'}"
    expect(formatToolContent(raw)).toBe(
      '找到 5 条搜索结果：\n\n1. 山丹县人民政府-刑法\n   链接: https://shandan.gov.cn/a.html\n   摘要: 第二百八十六条之一',
    )
  })
})

describe('HTML 兜底（结构标签 → 换行，其余标签剥掉）', () => {
  it('`<br>` 与块级闭合标签转换成行', () => {
    expect(formatToolContent('甲<br>乙<br/>丙')).toBe('甲\n乙\n丙')
    expect(formatToolContent('<p>第一段</p><p>第二段</p>')).toBe('第一段\n第二段')
    expect(formatToolContent('<div>标题</div><ul><li>一</li><li>二</li></ul>')).toBe('标题\n一\n二')
    expect(formatToolContent('<table><tr><td>甲</td></tr></table>')).toBe('甲')
    expect(formatToolContent('<h3>小节</h3>正文')).toBe('小节\n正文')
  })

  it('其余标签剥掉、文字留着', () => {
    expect(formatToolContent('<span class="x">正文</span>')).toBe('正文')
    expect(formatToolContent('《民法典》<b>第五百五十二条</b>')).toBe('《民法典》第五百五十二条')
  })

  it('带脚本/事件的标签只会变成纯文本，返回值里绝不含可执行的 HTML', () => {
    expect(formatToolContent('<img src=x onerror=alert(1)>正文')).toBe('正文')
    expect(formatToolContent('<script>alert(1)</script>')).toBe('alert(1)')
  })

  it('fetch_url 真实形状：内层 JSON 多一层转义 + 标题里的 `<br>`', () => {
    const raw =
      "{'type': 'text', 'text': '{\\n  \"ok\": true,\\n  \"title\": \"《民法典》<br>第三编\\\\u3000合同\",\\n  \"text\": \"第五百五十二条\\\\n第三人与债务人约定加入债务\"\\n}'}"
    const text = formatToolContent(raw)
    expect(text).toContain('"ok": true')
    // `<br>` 是页面里的换行，转成真换行（不再让律师看见标签）
    expect(text).toContain('《民法典》\n第三编')
    expect(text).not.toContain('<br>')
  })

  it('3 个以上连续换行折成 2 个', () => {
    expect(formatToolContent('<p>甲</p><p></p><p></p><p>乙</p>')).toBe('甲\n\n乙')
    expect(formatToolContent('甲\n\n\n\n\n乙')).toBe('甲\n\n乙')
  })
})

describe('HTML 实体解码', () => {
  it('命名实体一趟解一层', () => {
    expect(formatToolContent('a&nbsp;b&amp;c&lt;d&gt;e&quot;f&#39;g')).toBe('a b&c<d>e"f\'g')
  })

  it('数字实体（十进制 / 十六进制）', () => {
    expect(formatToolContent('&#x4E2D;&#25991;')).toBe('中文')
  })

  it('剥标签在解实体之前：`&lt;b&gt;` 是文字不是标签', () => {
    expect(formatToolContent('&lt;b&gt;不是粗体&lt;/b&gt;')).toBe('<b>不是粗体</b>')
  })

  it('越界码点原样保留，不抛异常', () => {
    expect(formatToolContent('&#x110000;')).toBe('&#x110000;')
  })
})

describe('纯文本原样返回', () => {
  it('中文正文一字不改', () => {
    const text = '开庭：开庭时间2026年11月23日下午15时00分（佛山市顺德区人民法院）'
    expect(formatToolContent(text)).toBe(text)
  })

  it('真换行的多行纯文本（tool_search 真实形状）不动', () => {
    const text =
      'Loaded 8 tools. They are available from your next call:\n- mcp__fachuan__list_lawyers: 按姓名/用户名搜索律师。\n- mcp__fachuan__forget_memory: 删除一条记忆（``restore_memory`` 恢复）。'
    expect(formatToolContent(text)).toBe(text)
  })

  it('首尾空白 trim，正文内的空格不动', () => {
    expect(formatToolContent('\n\n  正文 甲乙 \n\n\n')).toBe('正文 甲乙')
  })
})

describe('空输入', () => {
  it('空串 / 全空白 / null / undefined 一律空串（调用方据此不渲染内容区）', () => {
    expect(formatToolContent('')).toBe('')
    expect(formatToolContent('   \n\t ')).toBe('')
    expect(formatToolContent(null)).toBe('')
    expect(formatToolContent(undefined)).toBe('')
  })
})

describe('8000 字符（后端截断上限）', () => {
  /** 截断的真实形状：信封有头无尾（收尾引号被 8000 字砍掉了） */
  const truncated = `{'type': 'text', 'text': '{\\n  "total": 49,\\n  "items": [${'{\\n    "id": 1,\\n    "content": "甲方与乙方建筑设备租赁合同纠纷"\\n  },\\n'.repeat(200)}`

  it('信封头剥掉、换行变真换行、不丢字也不炸', () => {
    const raw = truncated.slice(0, 8000)
    const text = formatToolContent(raw)

    expect(raw.length).toBe(8000)
    expect(text.startsWith('{')).toBe(true)
    expect(text).not.toContain("'type'")
    expect(text.split('\n').length).toBeGreaterThan(100)
    // 截断的 JSON parse 不通，所以原样给出（长度只会因为折行/trim 变小，不会突然缩水）
    expect(text.length).toBeGreaterThan(7000)
  })
})
