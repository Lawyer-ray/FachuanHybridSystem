# 一张网立案 HTTP 接口插件

法穿AI Copilot 的私有插件，通过纯 HTTP 接口与全国法院"一张网"（zxfw.court.gov.cn）交互，实现在线立案。

## 功能

- 民事一审立案
- 行政一审立案
- 申请执行立案
- 当事人/代理人信息填写
- 材料上传（并发）
- 执行标的信息填写
- 立案完整性校验

## 架构

```
api_service.py              # 入口服务类（同步+异步双模式）
├── http_transport_mixin.py # HTTP 传输层（GET/POST/PATCH）
├── court_case_mixin.py     # 法院/案由查询
├── material_mixin.py       # 材料上传（OSS签名→上传→回调）
├── party_mixin.py          # 当事人/代理人管理
├── execution_validation_mixin.py  # 执行标的信息填写+校验
├── filing_flow_mixin.py    # 立案流程编排
└── constants.py            # 常量定义
```

## 使用方式

### 同步调用（Playwright 回退场景）

```python
from plugins.court_filing_http.api_service import CourtZxfwFilingApiService

api_svc = CourtZxfwFilingApiService(token)
result = api_svc.file_civil_case_sync(case_data)
```

### 异步调用

```python
async with CourtZxfwFilingApiService(token) as api_svc:
    result = await api_svc.file_civil_case(case_data)
```

## 安装位置

此插件部署在主项目的 `backend/plugins/court_filing_http/` 目录下。
主项目的 `.gitignore` 已忽略此目录，本仓库独立进行版本控制。
