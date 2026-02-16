# 🧭 立案引导模块 (Onboarding)

Onboarding 模块提供“立案引导/向导式录入”的页面与后端接口，帮助用户按步骤完成当事人、合同、案件等关键数据的初始化与关联。

## 📚 模块概述

本模块提供：
- 向导页面（templates + static）与路由（urls/views）
- 与案件/当事人/合同等模块交互的表单与校验 schema
- 管理后台入口（如需要扩展，可在 admin 下补充）

## 📁 目录结构（简要）

```
onboarding/
├── templates/  # wizard 页面与步骤组件
├── static/     # wizard 前端资源（css/js）
├── views.py    # 页面/接口视图
├── urls.py     # 路由
├── models.py   # 引导过程相关数据（如有）
└── schemas.py  # 输入输出 schema
```

## 🔑 核心入口

- 页面与路由：`views.py`、`urls.py`
- 模板：`templates/onboarding/wizard.html`、`templates/onboarding/components/*`
- 静态资源：`static/onboarding/*`

