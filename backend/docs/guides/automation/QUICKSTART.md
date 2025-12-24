# 🚀 司法文书下载 - 快速启动指南

## 1️⃣ 确认依赖已安装

```bash
# 检查 Playwright
python -c "import playwright; print('✅ Playwright 已安装')"

# 检查浏览器
playwright install chromium
```

## 2️⃣ 启动 Django-Q

```bash
cd backend/apiSystem
../venv311/bin/python manage.py qcluster
```

## 3️⃣ 启动 Django 服务

```bash
cd backend/apiSystem
../venv311/bin/python manage.py runserver
```

## 4️⃣ 访问快速下载页面

打开浏览器访问：
```
http://localhost:8000/admin/automation/quickdownloadtool/download/
```

## 5️⃣ 粘贴链接并下载

**测试链接 1** (zxfw.court.gov.cn):
```
https://zxfw.court.gov.cn/zxfw/#/pagesAjkj/app/wssd/index?qdbh=28938b642114470e80472ca62d5f622b&sdbh=97e29694bd324242bf4d50d00284e473&sdsin=83b0c4f5d938757e11b2cfd0292a1e31
```

**测试链接 2** (sd.gdems.com):
```
https://sd.gdems.com/v3/dzsd/B0MBNGh
```

## 6️⃣ 查看下载结果

1. 点击"查看任务详情"
2. 等待状态变为"成功"
3. 查看"执行结果"字段
4. 文件保存在 `backend/apiSystem/media/automation/downloads/`

---

## 🎯 完整流程演示

### 场景：收到法院短信，下载文书

1. **收到短信**
   ```
   【广东法院】您好，(2024)粤0106民初12345号案件有新的文书送达。
   查看链接：https://sd.gdems.com/v3/dzsd/B0MBNGh
   ```

2. **复制链接**
   ```
   https://sd.gdems.com/v3/dzsd/B0MBNGh
   ```

3. **打开快速下载页面**
   - 访问 Admin -> 🕷️ 爬虫工具 -> ⚡ 快速下载文书

4. **粘贴链接**
   - 文书链接: `https://sd.gdems.com/v3/dzsd/B0MBNGh`
   - 关联案件 ID: `123` (如果知道)

5. **点击"立即下载"**
   - 任务创建成功
   - 显示任务 ID

6. **等待 30-60 秒**
   - 后台自动执行
   - 可以查看任务详情

7. **查看结果**
   - 状态: 成功 ✅
   - 下载文件: 2 个 PDF
   - 文件路径: `/media/case_logs/123/documents/extracted/`

---

## 🐛 常见问题

### Q: 浏览器启动失败？
```bash
# 重新安装浏览器
playwright install chromium --force
```

### Q: Django-Q 没有运行？
```bash
# 检查进程
ps aux | grep qcluster

# 重新启动
python manage.py qcluster
```

### Q: 任务一直是"等待中"状态？
- 确认 Django-Q 正在运行
- 查看 Django-Q 的日志输出

### Q: 下载失败？
- 检查链接是否有效
- 查看任务的"错误信息"字段
- 查看截图（在 media/automation/screenshots/）

---

## 📞 需要帮助？

查看详细文档：
- `COURT_DOCUMENT_GUIDE.md` - 完整使用指南
- `IMPLEMENTATION_SUMMARY.md` - 实现总结
- `README.md` - 模块概述
