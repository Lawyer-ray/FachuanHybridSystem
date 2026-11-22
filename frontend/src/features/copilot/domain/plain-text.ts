/** Markdown → 纯文本（剪贴板 / 项目笔记都用它）。
 *
 * 从 `MessageActions.tsx` 挪出来：那个文件必须只导出组件，否则 Fast Refresh
 * 失效（`react-refresh/only-export-components`）。这里是纯函数，放 domain。
 */

/**
 * Markdown 源码 → 给剪贴板用的纯文本（`markdownToPlainText`）。
 *
 * 名字带 Markdown：本 barrel 里另有一个 `export.toPlainText`（整段转录 → 纯文本）。
 * 两者同名时 `export *` 会直接撞名（barrel 因此长期不引本模块），而且调用方也
 * 容易把 `string → string` 和 `ChatMessage[] → string` 弄反。
 *
 * 刻意**不**写完整解析器：这里只需要「粘到 Word/邮件里不难看」，任何一处
 * 改写都不该丢字。因此只剥结构性标记（标题井号、强调星号、行内反引号、
 * 列表/引用前缀、表格分隔行、链接语法），保留文字与段落换行。
 *
 * 为什么不用 DOM 的 `innerText` 取渲染结果：jsdom 不实现 `innerText`（测试里
 * 拿到 undefined），而且流式期间正文还在变，取 DOM 会把「正在增长的最后一帧」
 * 复制进去，与「复制这条回答」的语义不符。
 */
export function markdownToPlainText(markdown: string): string {
  return markdown
    // 围栏代码块：保留代码本身，只去掉 ```lang / ``` 这两行围栏
    .replace(/^[ \t]*```.*$/gm, '')
    // 表格对齐行（|---|---|）：整行都是结构，没有文字
    .replace(/^[ \t]*\|?[\s:|-]+\|[\s:|-]*$/gm, '')
    // 标题井号
    .replace(/^[ \t]{0,3}#{1,6}[ \t]+/gm, '')
    // 引用前缀（> 可嵌套）
    .replace(/^[ \t]*(?:>[ \t]?)+/gm, '')
    // 无序列表标记
    .replace(/^[ \t]*[-*+][ \t]+/gm, '')
    // 有序列表标记
    .replace(/^[ \t]*\d+[.)][ \t]+/gm, '')
    // 图片 → alt、链接 → 文字
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    // 强调/删除线/行内代码：**必须成对**才剥标记，不能无条件删字符。
    // 无条件删 `_` 会把标识符吃掉：`list_contracts` 变 `listcontracts`、
    // 文件名 `合同_终稿.docx` 变 `合同终稿.docx`——复制出去就是另一个东西了（有单测锁）。
    .replace(/(\*\*\*|\*\*|__|~~)(?=\S)([\s\S]*?)(?<=\S)\1/g, '$2')
    .replace(/(\*|_)(?=\S)([^*_\n]*?)(?<=\S)\1(?=[\s.,;:!?，。；：！？)）」』]|$)/g, '$2')
    .replace(/`([^`\n]+)`/g, '$1')
    // 表格竖线当分隔符（单元格之间原本就是空格语义）
    .replace(/[ \t]*\|[ \t]*/g, ' ')
    .replace(/[ \t]+$/gm, '')
    // 压掉多余空行（Markdown 常用两行空行分段，粘出去会变成大空隙）
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}
