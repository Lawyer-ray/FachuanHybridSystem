/**
 * ④ 文书阶段的三个动作剧本：生成委托材料 / 派机器人做利冲检索 / 导出利冲报告。
 *
 * 剧本本身是这一屏的业务叙述（检索哪几方、哪一步会命中红色冲突、命中后停在哪儿），
 * 埋在 `ContractPanel` 里会让面板看不出还剩多少编排。
 *
 * ⚠️ steps 数组仍写在 hook 内部（每次渲染新建）：`useStageAction` 的 `execute`
 * 依赖数组含 `steps`，提到模块级会改变它的引用稳定性 —— 那不是本次重构要动的东西。
 */

import { useStageAction } from './use-stage-action'

/** ① 生成委托材料：读案件数据 → 套模板 → 填字段 → 生成四份文书 */
export function useGenDocs() {
  return useStageAction({
    steps: [
      { text: '读取案件数据', ms: 500, parallel: ['当事人', '案由与标的', '管辖法院', '收费约定'] },
      { text: '套用《民事委托代理合同 v3.2》', ms: 900 },
      { text: '填充 24 个字段', ms: 700 },
      {
        text: '生成授权委托书',
        ms: 600,
        retry: { times: 1, delay: 800, reason: '共同借款人信息不完整，补齐后重试' },
      },
      { text: '生成风险告知书 / 收费协议', ms: 600 },
      { text: '检查必填项', ms: 500 },
    ],
    toSummary: () => '4 份文书已生成，1 份待补（送达地址确认书需选管辖法院模板）',
  })
}

/** ② 派机器人去 OA 做利冲检索 —— 这是本页的核心动作；命中红色冲突会停下等人决定 */
export function useConflictRun() {
  return useStageAction({
    steps: [
      { text: '启动服务端浏览器', ms: 700, parallel: ['分配容器', '加载自动化脚本'] },
      { text: '打开律所 OA 登录页', ms: 800 },
      {
        text: '登录 OA',
        ms: 900,
        retry: { times: 2, delay: 1500, reason: '登录会话超时，重新认证' },
      },
      { text: '进入当事人库检索', ms: 600 },
      { text: '检索：委托人 某某银行某某支行 → 无冲突', ms: 500 },
      { text: '检索：被告 谭某某 → 无同名记录', ms: 450 },
      { text: '检索：共同借款人 李某某 → 命中！', ms: 900 },
      {
        text: '命中红色冲突',
        ms: 600,
        confirm: '共同借款人李某某与本所在办「离婚案」当事人为同一人（证件号一致）。这属于禁止性冲突，是否终止本次委托？',
      },
      { text: '停止建卷，保留利冲结果页快照', ms: 500 },
    ],
    toSummary: () => '命中 1 处红色冲突（李某某），OA 立案已自动阻断',
  })
}

/** ③ 导出利冲报告：短进度，落一个 PDF */
export function useExportConflictReport() {
  return useStageAction({
    steps: [
      { text: '汇总 6 方检索记录', ms: 350 },
      { text: '附上命中快照与证件号比对', ms: 450 },
      { text: '渲染 PDF 并加律所抬头', ms: 550 },
    ],
    toSummary: () => 'LCA-20261101-0007 利冲审查报告.pdf 已生成，可在文书库下载',
  })
}
