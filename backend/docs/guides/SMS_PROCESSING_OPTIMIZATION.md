# 短信处理系统优化

## 概述

本次更新包含两个主要改进：
1. **案件状态过滤**：为法院短信自动匹配功能添加了案件状态过滤规则
2. **通知方式优化**：完全移除传统飞书 Webhook 通知，采用一案一群的方式

## 1. 案件状态过滤功能

确保只有"在办"状态的案件才能被自动匹配，"已结案"状态的案件需要人工处理。

## 功能说明

### 过滤规则

- **自动匹配**：只有状态为 `CaseStatus.ACTIVE`（"在办"）的案件才能被自动匹配
- **人工处理**：状态为 `CaseStatus.CLOSED`（"已结案"）的案件会被跳过，需要人工指定

### 匹配策略

1. **案号匹配**：在 `CaseNumber` 表中查找匹配的案号时，会检查关联案件的状态
2. **当事人匹配**：在 `CaseParty` 表中查找时，添加了 `case__status=CaseStatus.ACTIVE` 过滤条件
3. **日志记录**：发现已结案案件时会记录详细的警告日志，提示需要人工处理

## 修改文件

### 1. `backend/apps/automation/services/sms/case_matcher.py`

#### 修改的方法：

- `match()` - 添加状态过滤说明和已结案案件检查
- `match_by_case_number()` - 添加案件状态检查
- `match_by_party_names()` - 添加状态过滤条件
- `_check_and_log_closed_cases()` - 新增方法，检查并记录已结案案件

#### 关键代码：

```python
# 案号匹配时的状态检查
if case.status == CaseStatus.ACTIVE:
    logger.info(f"找到匹配的案号记录: {case_number}, 案件状态: {case.status}")
    return case
else:
    logger.info(f"案号 {case_number} 匹配到案件，但状态为 '{case.status}'，需要人工处理")
    continue

# 当事人匹配时的状态过滤
case_parties = CaseParty.objects.filter(
    client__in=matched_clients,
    case__status=CaseStatus.ACTIVE  # 只匹配"在办"状态的案件
).select_related('case')
```

### 2. `backend/apps/automation/services/sms/court_sms_service.py`

#### 修改的方法：

- `_process_matching()` - 添加状态过滤说明日志

## 日志输出示例

### 成功匹配在办案件
```
[INFO] 找到匹配的案号记录: （2024）粤01民初1001号, 案件状态: active
[INFO] 通过案号匹配到案件: 测试在办案件
```

### 跳过已结案案件
```
[INFO] 案号 （2024）粤01民初1002号 匹配到案件，但状态为 'closed'，需要人工处理
[WARNING] 发现已结案案件（案号匹配）: 案号=（2024）粤01民初1002号, 案件='测试已结案案件', 需要人工处理
[INFO] 共发现 1 个已结案案件，已跳过自动匹配，等待人工处理
[INFO] 未能匹配到任何在办状态的案件，需要人工处理
```

## 测试验证

创建了测试脚本 `backend/scripts/test_case_status_filtering.py` 来验证功能：

- ✅ 案号匹配：在办案件成功匹配，已结案案件被跳过
- ✅ 当事人匹配：只匹配在办状态的案件
- ✅ 完整流程：端到端测试通过
- ✅ 日志记录：详细记录处理过程和跳过原因

## 使用说明

### 自动处理流程

1. 短信提交后，系统会尝试自动匹配案件
2. 只有"在办"状态的案件会被自动匹配
3. 如果匹配到"已结案"案件，会在日志中记录并跳过
4. 无法自动匹配的短信会标记为 `PENDING_MANUAL`，等待人工处理

### 人工处理

对于无法自动匹配的短信（包括匹配到已结案案件的情况）：

1. 在 Django Admin 中查看短信记录
2. 查看日志了解跳过原因
3. 使用"指定案件"功能手动绑定正确的案件
4. 系统会继续后续的处理流程

## 配置说明

无需额外配置，功能基于现有的 `CaseStatus` 枚举：

- `CaseStatus.ACTIVE` - "在办"（可自动匹配）
- `CaseStatus.CLOSED` - "已结案"（需人工处理）

## 2. 通知方式优化

### 变更说明

完全移除了传统的飞书 Webhook 通知方式，现在只使用案件群聊通知（一案一群）。

### 修改的文件

#### `backend/apps/automation/services/sms/court_sms_service.py`

**修改的方法：**
- `_process_notifying()` - 简化通知逻辑，只使用案件群聊通知

**关键变更：**
```python
# 移除传统飞书 Webhook 通知代码
# 只保留案件群聊通知逻辑
case_chat_success = self._send_case_chat_notification(sms, document_path)

# 将案件群聊通知结果同步到飞书通知字段，便于后台显示
if case_chat_success:
    sms.feishu_sent_at = timezone.now()
    sms.feishu_error = None
```

#### `backend/apps/automation/services/chat/feishu_provider.py`

**修改的方法：**
- `_send_file_message()` - 修复文件消息发送的 400 错误

**关键修复：**
```python
# 将 receive_id_type 作为查询参数传递，而不是放在请求体中
params = {
    "receive_id_type": "chat_id"
}

# 请求体中不再包含 receive_id_type
payload = {
    "receive_id": chat_id,
    "msg_type": "file",
    "content": json.dumps({
        "file_key": file_key,
        "file_name": file_name
    })
}
```

### 功能验证

通过完整测试验证了以下功能：
- ✅ 文本消息发送正常
- ✅ 文件上传功能正常
- ✅ 文件消息发送正常
- ✅ 完整的文件发送流程正常

### 优势

1. **简化架构**：移除了复杂的双通知机制
2. **统一管理**：所有通知都通过案件群聊进行
3. **更好的用户体验**：一案一群，信息更集中
4. **减少配置依赖**：不再需要配置 Webhook URL

## 注意事项

1. 此功能不影响手动指定案件的流程
2. 已结案案件仍可通过人工方式绑定短信
3. 日志级别为 WARNING 的消息需要关注，通常表示需要人工干预
4. 建议定期检查 `PENDING_MANUAL` 状态的短信，及时进行人工处理
5. 现在所有通知都通过案件群聊发送，确保飞书应用配置正确