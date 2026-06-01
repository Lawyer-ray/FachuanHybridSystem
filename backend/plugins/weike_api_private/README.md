# 威科信息私有 API 适配器插件

法穿AI Copilot 的私有插件，通过 HTTP API 直接与威科信息系统（law.wkinfo.com.cn）交互，替代默认的 Playwright 浏览器自动化方式。

## 功能

- HTTP 方式登录威科信息系统（SSO 表单自动提取与提交）
- 通过 API 进行案例检索（替代 DOM 解析）
- 支持高级检索、案由筛选、法院筛选、日期范围筛选
- 检索事件记录（可观测性）

## 架构

```
adapter.py              # 核心适配器（PrivateWeikeApiAdapter 类 + 单例）
├── open_http_session()        # HTTP 登录流程
├── search_cases_via_api()     # API 检索
├── _build_case_search_payload()  # 构建检索请求体
├── _encode_login_field()      # 登录字段编码
└── _extract_law_form_payload()   # SSO 表单解析
```

## 使用方式

插件通过主项目的 `api_optional.py` 动态加载，无需显式导入：

```python
from apps.legal_research.services.sources.weike.api_optional import get_private_weike_api

adapter = get_private_weike_api()
if adapter is not None:
    session = adapter.open_http_session(client=client, username=u, password=p, login_url=url)
    results = adapter.search_cases_via_api(client=client, session=session, keyword="合同纠纷", ...)
```

## 安装位置

此插件部署在主项目的 `backend/plugins/weike_api_private/` 目录下。
主项目的 `.gitignore` 已忽略此目录，本仓库独立进行版本控制。
