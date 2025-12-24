# Django Ninja 异步视图指南

## Ninja 支持异步吗？

**完全支持！** Django Ninja 从 v0.16.0 开始原生支持异步视图。

## 同步 vs 异步视图

### 同步视图（当前）

```python
from ninja import Router
from ..services import CaseService

router = Router()

@router.get("/cases")
def list_cases(request, case_type: str = None):
    """同步视图"""
    return CaseService.list_cases(case_type=case_type)

@router.post("/cases")
def create_case(request, payload: CaseIn):
    """同步视图"""
    return CaseService.create_case(payload.dict())
```

### 异步视图

```python
from ninja import Router
from asgiref.sync import sync_to_async
from ..services import CaseService

router = Router()

@router.get("/cases")
async def list_cases(request, case_type: str = None):
    """异步视图"""
    # 包装同步 Service 方法
    list_cases_async = sync_to_async(CaseService.list_cases)
    return await list_cases_async(case_type=case_type)

@router.post("/cases")
async def create_case(request, payload: CaseIn):
    """异步视图"""
    create_case_async = sync_to_async(CaseService.create_case)
    return await create_case_async(payload.dict())
```

## 何时使用异步视图？

### ✅ 适合异步的场景

#### 1. 并发调用多个外部 API

```python
import httpx

@router.get("/case/{case_id}/enriched")
async def get_enriched_case(request, case_id: int):
    """同时获取案件信息和相关数据"""
    async with httpx.AsyncClient() as client:
        # 并发请求多个 API
        case_task = client.get(f"http://api1.com/cases/{case_id}")
        parties_task = client.get(f"http://api2.com/parties?case={case_id}")
        documents_task = client.get(f"http://api3.com/documents?case={case_id}")
        
        # 等待所有请求完成
        case_resp, parties_resp, docs_resp = await asyncio.gather(
            case_task, parties_task, documents_task
        )
        
        return {
            "case": case_resp.json(),
            "parties": parties_resp.json(),
            "documents": docs_resp.json(),
        }
```

**性能提升：** 3 个串行请求 3 秒 → 并发 1 秒

#### 2. WebSocket 实时推送

```python
from ninja import Router
from channels.layers import get_channel_layer

router = Router()

@router.post("/tasks/{task_id}/start")
async def start_task(request, task_id: int):
    """启动任务并实时推送进度"""
    channel_layer = get_channel_layer()
    
    # 发送开始消息
    await channel_layer.group_send(
        f"task_{task_id}",
        {"type": "task.started", "task_id": task_id}
    )
    
    # 启动任务
    task = await sync_to_async(ScraperTask.objects.get)(id=task_id)
    # ...
    
    return {"status": "started"}
```

#### 3. 长轮询（Long Polling）

```python
@router.get("/tasks/{task_id}/wait")
async def wait_for_task(request, task_id: int, timeout: int = 30):
    """等待任务完成"""
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        task = await sync_to_async(ScraperTask.objects.get)(id=task_id)
        
        if task.status in ["success", "failed"]:
            return {"status": task.status, "result": task.result}
        
        # 异步等待，不阻塞其他请求
        await asyncio.sleep(1)
    
    return {"status": "timeout"}
```

### ❌ 不适合异步的场景

#### 1. 简单的 CRUD 操作

```python
# 不需要异步
@router.get("/cases/{case_id}")
def get_case(request, case_id: int):
    """简单查询，同步就够了"""
    return CaseService.get_case(case_id)
```

**原因：**
- 数据库查询很快（< 100ms）
- 异步包装反而增加开销
- 代码更复杂

#### 2. CPU 密集型操作

```python
# 异步没用
@router.post("/cases/analyze")
async def analyze_cases(request):
    """CPU 密集型任务"""
    # 即使用 async，这里还是会阻塞
    result = heavy_computation()  # 计算密集
    return result
```

**原因：**
- 异步只能优化 I/O 等待
- CPU 密集型任务应该用 Celery 后台处理

#### 3. 已经有任务队列的操作

```python
# 不需要异步
@router.post("/scraper/tasks")
def create_scraper_task(request, payload: TaskIn):
    """创建爬虫任务"""
    task = ScraperTask.objects.create(...)
    
    # 提交到 Django-Q
    async_task('execute_scraper_task', task.id)
    
    return {"task_id": task.id}
```

**原因：**
- 任务已经异步执行（通过队列）
- API 只负责创建任务，立即返回

## 混合使用：部分异步

你可以在同一个项目中混合使用同步和异步视图：

```python
# cases/api.py
router = Router()

# 同步视图 - 简单 CRUD
@router.get("/cases")
def list_cases(request):
    return CaseService.list_cases()

# 异步视图 - 需要并发
@router.get("/cases/{case_id}/full")
async def get_case_full(request, case_id: int):
    """并发获取案件完整信息"""
    async with httpx.AsyncClient() as client:
        case, logs, documents = await asyncio.gather(
            sync_to_async(CaseService.get_case)(case_id),
            sync_to_async(CaseLogService.list_logs)(case_id),
            client.get(f"http://docs-api/cases/{case_id}/documents")
        )
    
    return {
        "case": case,
        "logs": logs,
        "documents": documents.json(),
    }
```

## Django ORM 异步支持

Django 4.1+ 支持异步 ORM：

```python
# 异步查询
@router.get("/cases")
async def list_cases(request):
    cases = await Case.objects.filter(status="active").all()
    return [CaseOut.from_orm(c) for c in cases]

# 异步创建
@router.post("/cases")
async def create_case(request, payload: CaseIn):
    case = await Case.objects.acreate(**payload.dict())
    return CaseOut.from_orm(case)

# 异步事务
from django.db import transaction

@router.post("/cases/bulk")
async def create_cases_bulk(request, cases: List[CaseIn]):
    async with transaction.atomic():
        created = []
        for case_data in cases:
            case = await Case.objects.acreate(**case_data.dict())
            created.append(case)
    return created
```

**注意：** 异步 ORM 有一些限制：
- 不支持 `select_related`、`prefetch_related`
- 某些复杂查询需要用 `sync_to_async` 包装

## 性能对比

### 场景 1：单个数据库查询

```python
# 同步
@router.get("/cases/{case_id}")
def get_case(request, case_id: int):
    return Case.objects.get(id=case_id)

# 异步
@router.get("/cases/{case_id}")
async def get_case(request, case_id: int):
    return await Case.objects.aget(id=case_id)
```

**结果：** 性能几乎相同（异步甚至可能稍慢，因为有包装开销）

### 场景 2：并发调用 3 个外部 API

```python
# 同步（串行）
@router.get("/case/{case_id}/full")
def get_case_full(request, case_id: int):
    case = requests.get(f"http://api1/cases/{case_id}").json()  # 1s
    logs = requests.get(f"http://api2/logs?case={case_id}").json()  # 1s
    docs = requests.get(f"http://api3/docs?case={case_id}").json()  # 1s
    return {"case": case, "logs": logs, "docs": docs}
# 总耗时：3 秒

# 异步（并发）
@router.get("/case/{case_id}/full")
async def get_case_full(request, case_id: int):
    async with httpx.AsyncClient() as client:
        case, logs, docs = await asyncio.gather(
            client.get(f"http://api1/cases/{case_id}"),
            client.get(f"http://api2/logs?case={case_id}"),
            client.get(f"http://api3/docs?case={case_id}"),
        )
    return {
        "case": case.json(),
        "logs": logs.json(),
        "docs": docs.json(),
    }
# 总耗时：1 秒
```

**结果：** 异步快 3 倍

## 你的项目应该用异步视图吗？

### 当前情况分析

看你的 `case_api.py`：

```python
@router.get("/cases")
def list_cases(request, case_type: str = None):
    return CaseService.list_cases(case_type=case_type)
```

这是简单的数据库查询，**不需要改成异步**。

### 何时考虑异步？

只有在以下情况：

1. **需要调用多个外部 API**
   ```python
   # 例如：获取案件时需要调用法院 API、律师 API、文书 API
   @router.get("/cases/{case_id}/enriched")
   async def get_enriched_case(request, case_id: int):
       # 并发调用多个 API
       pass
   ```

2. **需要实时推送**
   ```python
   # 例如：任务进度实时推送
   @router.get("/tasks/{task_id}/stream")
   async def stream_task_progress(request, task_id: int):
       # Server-Sent Events
       pass
   ```

3. **需要长轮询**
   ```python
   # 例如：等待爬虫任务完成
   @router.get("/tasks/{task_id}/wait")
   async def wait_for_task(request, task_id: int):
       # 长轮询
       pass
   ```

## 推荐方案

### 当前阶段
**保持同步视图**
- 理由：代码简单、够用
- 你的 API 主要是 CRUD，不需要异步

### 未来扩展
**按需添加异步视图**
- 只在需要并发 I/O 的地方用异步
- 其他地方保持同步

### 示例：混合架构

```python
# cases/api.py
router = Router()

# 同步视图 - CRUD
@router.get("/cases")
def list_cases(request):
    return CaseService.list_cases()

@router.post("/cases")
def create_case(request, payload: CaseIn):
    return CaseService.create_case(payload.dict())

# 异步视图 - 需要并发的场景
@router.get("/cases/{case_id}/external-data")
async def get_external_data(request, case_id: int):
    """并发获取外部数据"""
    async with httpx.AsyncClient() as client:
        court_data, lawyer_data = await asyncio.gather(
            client.get(f"http://court-api/cases/{case_id}"),
            client.get(f"http://lawyer-api/cases/{case_id}"),
        )
    return {
        "court": court_data.json(),
        "lawyer": lawyer_data.json(),
    }
```

## 总结

1. **Ninja 支持异步**，但不是必须的
2. **你的项目不需要全部改成异步**
3. **只在需要并发 I/O 的地方用异步**
4. **简单的 CRUD 保持同步更好**

**不要为了异步而异步**，只在真正能带来性能提升的地方使用。
