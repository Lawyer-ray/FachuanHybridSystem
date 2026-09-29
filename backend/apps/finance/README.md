# 💰 金融工具 / LPR（finance）

LPR 利率数据管理（央行数据 Playwright 自动同步 / 种子加载）+ 面向诉讼的利息计算器（LPR 分段计息、房贷摊销、房贷逾期违约债权计算）。

## 功能概述

- `LPRRate` 存 1Y / 5Y 报价（每月 20 日发布）；支持按日查询、区间利率分段（RateSegment）、数据新旧判断
- 同步：`LPRSyncService` 用 Playwright headless 抓取中国银行 LPR 页面表格，解析去重后 update_or_create；`/calculate` 在 LPR 模式下发现数据过期会在线程池中自动同步（120s 超时兜底，失败降级用旧数据）
- `InterestCalculator`：固定本金或变动本金（PrincipalPeriod 段，如租金场景），LPR / 自定义利率（支持利率单位换算）、倍数（LPR 上浮/加成）、360/365 计息基数、头尾天数包含规则
- `MortgageDefaultCalculator`（房贷逾期违约债权，银行诉讼场景）：等额本息/等额本金摊销 + 还款流水冲抵（冲抵顺序/立场可配）+ 罚息/复利（利滚利开关、封顶）+ 一次性违约金 + 加速到期 + 止息区间 + 工作日顺延 + 提前还款 + 阶梯罚息 + 舍入模式
- **银行口径档案（bank_profiles）**：把各行计息/复利/冲抵/首期差异数据化为预设，前端一键填表；加银行 = 加数据不改代码（档案仅为常见口径起始模板，须对照具体合同核对）
- post_migrate 自动加载 `data/seed_lpr_rates.json` 种子（仅表空时；另有 load_seed_data 管理命令）

## 目录结构

```
finance/
├── apps.py                      # post_migrate 加载 LPR 种子（test/pytest 跳过）
├── models/lpr_rate.py           # LPRRate
├── api/lpr_api.py               # 8 个端点
├── schemas/lpr_schemas.py
├── admin/lpr_admin.py           # 全只读 + sync/ + calculator/ 自定义视图
├── tasks.py                     # 定时任务 + 调度注册
├── data/seed_lpr_rates.json     # 种子数据
└── services/
    ├── lpr/                     # rate_service / sync_service / seed_data_loader
    └── calculator/              # interest_calculator + mortgage 全家桶
        （validation / rate_resolver / schedule / simulation /
          accrual / ledger / claim / mortgage_models / bank_profiles）
```

## 数据模型

- `LPRRate` — LPR 利率记录（effective_date 唯一、1Y/5Y Decimal(5,2)、来源、is_auto_synced）

## API 端点

前缀 `/api/v1/lpr`：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/rates`、`/rates/latest` | 利率历史 / 最新利率 |
| POST | `/sync` | 手动触发同步（需 is_staff） |
| GET | `/sync/status` | 同步状态统计 |
| POST | `/calculate` | LPR / 自定义利息计算（LPR 模式自动同步过期数据） |
| POST | `/amortize` | 房贷摊销计划（等额本息/本金） |
| GET | `/bank-profiles` | 银行口径档案列表 |
| POST | `/mortgage-default-calculate` | 房贷逾期违约债权计算 |

## Admin

`LPRRateAdmin`（继承 cases.BaseModelAdmin）——数据「只进不改」，禁止增删改；自定义 `sync/`（直接执行同步）与 `calculator/`（计算器页面）视图。

## 异步任务与信号

- 定时任务 `lpr_monthly_sync`：**每月 20 日 9:30**（setup_lpr_sync_schedule 创建，repeats=-1）
- post_migrate 信号自动加载种子（apps.py 内连接）

## 设计要点

- 数据源选中国银行页面（结构稳定无反爬），source 字段仍记「中国人民银行官网」
- 利息止算（interest_cutoff_date）与加速到期互斥的合并规则在 API 层实现，并写入 warnings 说明口径
- 解析失败会截图 `/tmp/lpr_sync_debug.png` 便于排查

## 外部集成

Playwright headless（apps.core.services.browser.create_browser）；无 LLM。

## 依赖模块

- `apps.core`（异常、认证、任务提交、浏览器服务）、`apps.cases.admin.base_admin.BaseModelAdmin`
