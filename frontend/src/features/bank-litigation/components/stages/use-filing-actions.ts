/**
 * ⑥ 校验阶段的三个动作剧本：跑校验 / 一键修正 / 通知律师。
 *
 * 剧本（步骤文案、耗时、重试、并行子任务、确认话术）本身就是这一屏的"业务叙述"，
 * 埋在 `FilingPanel` 里会让面板看不出还剩多少编排。挪到这里后，面板只剩
 * 「统计 → 左列四张卡 → 右栏 → 两个抽屉」。
 *
 * ⚠️ steps 数组仍写在 hook 内部（每次渲染新建）：`useStageAction` 的 `execute`
 * 依赖数组含 `steps`，提到模块级会改变它的引用稳定性 —— 那不是本次重构要动的东西。
 */

import { useStageAction } from './use-stage-action'

/** 跑一遍完整校验：法律要件 + 卷宗要件 + 三处金额 + 签章识别 */
export function useFilingVerify() {
  return useStageAction({
    steps: [
      { text: '加载校验规则', ms: 400 },
      { text: '核对当事人主体适格 · 通过', ms: 400 },
      { text: '核对管辖法院 · 通过', ms: 380 },
      { text: '核对诉讼时效 · 未届满', ms: 400 },
      {
        text: '比对三处金额',
        ms: 900,
        retry: { times: 1, delay: 800, reason: '立案表单回读超时，重新拉取' },
      },
      { text: '识别印章（6 份文书）', ms: 1200, parallel: ['起诉状', '证据清单', '授权委托书', '送达确认书', '退费确认书', '委托证明'] },
      { text: '识别签名区域', ms: 900 },
      { text: '检查要素式起诉状', ms: 450 },
      { text: '汇总校验结果', ms: 350 },
    ],
    toSummary: () => '校验完成：4 项通过 / 1 项提示 / 2 项不通过，暂不能送法院',
  })
}

/** 一键修系统能自动修的那两项（只在 diff 预览确认后才跑） */
export function useFilingAutoFix() {
  return useStageAction({
    steps: [
      { text: '按起诉状定稿基准重写立案表单标的额', ms: 420 },
      { text: '重写后回读校验：998,670.21 = 998,670.21', ms: 380 },
      { text: '调用要素式转换服务', ms: 640 },
      { text: '生成要素式起诉状 docx', ms: 520 },
    ],
    toSummary: () => '已自动修正 2 项：金额对齐、要素式转换完成；剩 2 份签章待人工',
  })
}

/** 通知律师去一张网（提交那一下仍由律师本人点） */
export function useFilingNotify() {
  return useStageAction({
    steps: [
      { text: '检查硬阻塞：签章是否全部通过', ms: 300 },
      { text: '生成待办：去一张网核对立案表单', ms: 420 },
      { text: '推送站内待办 + AI 助手卡片', ms: 380 },
      { text: '发送短信', ms: 300 },
    ],
    toSummary: () => '已送达',
  })
}
