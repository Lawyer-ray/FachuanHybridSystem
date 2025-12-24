# 异步 vs 同步：架构决策指南

## 问题背景

在开发法院文书下载模块时，遇到了"异步上下文"相关的错误。这是因为 Playwright 的某些内部操作可能触发异步事件循环检测。

## 当前架构（推荐保持）

```
┌─────────────────────────────────────────┐
│  Django Ninja API (同步)                │
│  - 接收 HTTP 请求                        │
│  - 创建爬虫任务                          │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│  Django-Q 任务队列 (同步)                │
│  - 调度任务执行                          │
│  - 重试机制                              │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│  Playwright 爬虫 (同步 API)              │
│  - 浏览器自动化                          │
│  - 文件下载                              │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│  Django ORM (同步)                       │
│  - 保存任务状态                          │
│  - 保存下载文件记录                      │
└─────────────────────────────────────────┘
```

## 为什么不需要改成异步？

### 1. Django-Q 是同步的
- Django-Q 的 worker 进程是同步执行的
- 改成异步需要切换到 Celery + asyncio，增加复杂度

### 2. Playwright 同步 API 更简单
```python
# 同步版本（当前）- 简单直观
page.goto(url)
page.click("#download")
download = page.expect_download()

# 异步版本 - 更复杂
await page.goto(url)
await page.click("#download")
async with page.expect_download() as download_info:
    download = await download_info.value
```

### 3. Django ORM 在同步环境更稳定
- Django ORM 主要为同步设计
- 异步 ORM 需要使用 `sync_to_async` 包装，增加开销

### 4. 爬虫任务本质是 I/O 密集型
- 大部分时间在等待网页加载、下载文件
- 使用多进程（Django-Q workers）已经足够
- 不需要单进程内的异步并发

## 真正的问题：数据库连接管理

问题不是"异步 vs 同步"，而是 **Playwright 内部可能创建事件循环，导致 Django 检测到异步上下文**。

### 解决方案

在保存数据库前，关闭当前连接，让 Django 创建新的连接：

```python
from django.db import connection

def save_record():
    # 关闭当前连接（如果有）
    connection.close()
    
    # Django 会自动创建新连接
    record = DownloadedFile.objects.create(...)
    return record
```

这样做的好处：
- ✅ 避免连接在线程/事件循环间共享
- ✅ 让 Django 管理连接生命周期
- ✅ 不需要改变整体架构

## 什么时候应该考虑异步？

只有在以下情况才考虑：

1. **API 层需要高并发**
   - 单个请求需要等待多个外部 API
   - 需要同时处理大量 WebSocket 连接
   
2. **实时数据推送**
   - Server-Sent Events (SSE)
   - WebSocket 实时通知

3. **微服务间通信**
   - 需要同时调用多个微服务
   - 使用 gRPC 异步客户端

## 当前架构的优势

1. **简单可维护**：代码逻辑清晰，易于调试
2. **稳定可靠**：Django ORM + Django-Q 是成熟的技术栈
3. **足够高效**：多进程 workers 可以并行处理多个任务
4. **易于扩展**：增加 worker 数量即可提升吞吐量

## 性能优化建议

如果需要提升性能，优先考虑：

1. **增加 Django-Q workers 数量**
   ```python
   # settings.py
   Q_CLUSTER = {
       'workers': 8,  # 增加 worker 数量
   }
   ```

2. **使用任务优先级**
   ```python
   task = ScraperTask.objects.create(
       priority=1,  # 高优先级任务
   )
   ```

3. **批量处理**
   ```python
   # 批量创建记录，减少数据库往返
   DownloadedFile.objects.bulk_create([...])
   ```

4. **数据库连接池**
   ```python
   # settings.py
   DATABASES = {
       'default': {
           'CONN_MAX_AGE': 600,  # 连接复用
       }
   }
   ```

## 总结

**保持当前的同步架构**，只需要在数据库操作前调用 `connection.close()` 来避免连接共享问题。这是最简单、最稳定的解决方案。
