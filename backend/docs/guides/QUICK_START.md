# 快速开始

本页是给“第一次拉仓库的人”的最短路径。更完整说明见 `backend/README.md`。

## 1) 环境准备

- Python：3.12.x
- 依赖：`requirements.txt` + `requirements-dev.txt` + `requirements-test.txt`（配合 `constraints/py312.txt`）

## 2) 本地启动（开发模式）

```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt -r requirements-dev.txt -r requirements-test.txt -c constraints/py312.txt
python apiSystem/manage.py migrate
python apiSystem/manage.py runserver 0.0.0.0:8000
```

## 3) 常用命令

- Django 自检

```bash
python apiSystem/manage.py check
```

- 跑 CI 同款结构门禁（快速）

```bash
pytest -c pytest.ini --no-cov -q tests/structure/test_cross_module_import_properties.py
```

- 跑单测（按需增减）

```bash
pytest -c pytest.ini --no-cov -q tests/unit
```

## 4) 常见问题排查

- 运行报 “No module named django”：说明没激活 venv 或没安装依赖
- 结构测试失败：优先检查是否引入了跨模块导入/越界依赖
- 日志排障：优先使用 request_id/trace_id 关联同一请求内日志
