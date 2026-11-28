# 真机 UI 动作冒烟（`make e2e-ui-action`）

一条命令把「AI 让页面改库」的四条链路在真浏览器、真 MCP、真库上跑一遍。它不替代
单元测试，补的是单元测试看不到的那一层：审批卡真的弹出来了吗、点「同意」后页面真的
写库了吗、服务端真的回库核实了吗、审计台账记对了吗。

## 它证明什么

| # | 动作 | 操作 | 断言 |
|:-|:-|:-|:-|
| ① | `ui_material_prep_judge`（confirm） | 审批卡点「同意」 | 材料包 `draft_state.status` 真的变成 `done`；审计 `outcome=ok` 且 `verified=true` |
| ② | `ui_material_prep_judge`（confirm） | 审批卡点「拒绝」→「确认拒绝」 | 材料包零变化；审计 `outcome=denied` |
| ③ | `ui_material_prep_delete_pack`（guarded） | 审批点「同意」+ 本地弹框点「确认执行」 | 包真的不存在；审计 `outcome=ok` 且 `verified=true` |
| ④ | `ui_material_prep_delete_pack`（guarded） | 审批点「同意」+ 本地弹框点「取消」 | 包还在、零变化；审计 `outcome=aborted` |

「零变化」比较的是业务指纹（subject / 附件数 / `draft_state`），不看 `read_at`
这类页内态。任何一段不成立都会非零退出，并打印 before / after 与当时的审计行。

## 前置条件

1. 三个服务都在跑：
   - 前端 dev server `:5090`（`make frontend`）
   - Django `:8002`（`make backend`）
   - 共享 MCP `:8011`（`make mcp`；改过 `mcp_server` 代码后先 `make mcp`）
2. 后端 venv 里有 playwright 与 Chromium：
   ```bash
   backend/.venv/bin/python -m pip install playwright
   backend/.venv/bin/python -m playwright install chromium
   ```
3. 开发库已应用迁移（脚本会造材料包、会话与审计行）。

## 怎么跑

```bash
make e2e-ui-action
```

等价于：

```bash
cd backend && env -u PYTHONHOME -u PYTHONPATH DB_NAME=fachuan_dev \
  .venv/bin/python ../scripts/e2e/ui_action_smoke.py --require
```

不带 `--require` 时，三个端口任一不通会打印 `[skip]` 并**退出 0**（避免 CI 因环境红）；
本地自证用 `--require`，前置不全直接退出 2。

### 身份票

- 优先用环境变量 `FACHUAN_E2E_TOKEN`（不打印、不落文件）；
- 没给就用 Django 现场铸一张（子进程 `mint_user_access_token`），默认取第一个启用的
  超级管理员。要换人：`FACHUAN_E2E_USERNAME=<username>` 或 `FACHUAN_E2E_USER_ID=<id>`。

### 退出码

| 码 | 含义 |
|:-:|:-|
| 0 | 四段全过；或按约定 skip（服务未起 / 缺 playwright） |
| 1 | 服务都在、脚本跑完了，但至少一段断言不成立 |
| 2 | 准备失败：`--require` 下前置服务不全、铸票失败、建会话/造包失败、浏览器起不来 |

## 数据边界与清理

- 只碰脚本自造的数据：四个 `E2E-<时间戳>-<随机>-*.txt` 材料包 + 一个专用会话；
- 跑完在 `finally` 里删这四个包、删这个会话；
- **审计行一行都不删**：它们是「谁让 AI 干了什么」的证据，脚本退出前会把本次会话留下
  的行全部打印出来（删会话后审计行按 `SET_NULL` 保留）；
- 截图写到 `/tmp/fachuan-e2e-shots/<时间戳>/`，不进仓库。

> 脚本每个动作前会发一句需要长回答的聊天。这是为了打开会话的 SSE 订阅——审批卡
> 走 `approval_request` 帧，没有在途的流就送不到页面。这一句会真的调模型，有 token
> 成本；它不是模型能力测试，回答内容不参与断言。

> 已知抖动：`publish_ui_action` 默认只等 2s 回执（`FACHUAN_UI_ACTION_ACK_WAIT`）。
> 机器负载很高时页面可能超过 2s，工具返回 `observed=false`、审计 `verified=null`，
> 该段会红。这不是核实器坏了：重跑一次，或给共享 MCP 设
> `FACHUAN_UI_ACTION_ACK_WAIT=8` 后 `make mcp` 再跑。

## 跑挂了看什么

1. 截图目录：审批卡到底有没有出现、页面是不是被重定向到登录页；
2. `[preflight]` 三行：哪个端口没起；
3. `make mcp-status` / `make mcp-verify`：共享 MCP 是否加载了当前分支的工具面；
4. `[audit]` 打印的行：`outcome=unknown` 说明页面没回执（多半没订阅者或执行器报错），
   `verified=null` 说明服务端没核到（对应 `verify_note` 会写明原因）。

## 它不覆盖什么

- `safe` 动作（`ui_navigate` / `ui_copilot_open` / `ui_material_prep_set_stage`）：它们
  不写台账、不弹审批，已有单测覆盖；
- 批量下发、多标签页抢占、风险下限抬高这些治理分支：见
  `frontend/src/features/copilot/store/ui-tools.*.test.ts` 与
  `backend/tests/ci/unit/agent/test_ui_action_*.py`；
- 生产环境：脚本用 `127.0.0.1` 的三个固定端口，只面向本地开发栈。
