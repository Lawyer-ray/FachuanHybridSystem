# 费率信息显示功能实现

## 实现日期
2025-11-29

## 需求
在后台（Django Admin）显示保险公司的完整费率信息：
1. **三个价格**：最低收费1 (minPremium)、最低收费2 (minAmount)、最高收费 (maxAmount)
2. **两个费率**：最低费率 (minRate)、最高费率 (maxRate)
3. **最高保全金额** (maxApplyAmount)

## 实现方案

### 1. 数据模型修改

**文件**: `backend/apps/automation/models.py`

在 `InsuranceQuote` 模型中添加 6 个新字段：

```python
class InsuranceQuote(models.Model):
    # ... 原有字段 ...
    
    # 费率信息字段
    min_premium = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
        verbose_name=_("最低收费1"), help_text=_("minPremium")
    )
    min_amount = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
        verbose_name=_("最低收费2"), help_text=_("minAmount")
    )
    max_amount = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
        verbose_name=_("最高收费"), help_text=_("maxAmount")
    )
    min_rate = models.DecimalField(
        max_digits=10, decimal_places=6, null=True, blank=True,
        verbose_name=_("最低费率"), help_text=_("minRate")
    )
    max_rate = models.DecimalField(
        max_digits=10, decimal_places=6, null=True, blank=True,
        verbose_name=_("最高费率"), help_text=_("maxRate")
    )
    max_apply_amount = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
        verbose_name=_("最高保全金额"), help_text=_("maxApplyAmount")
    )
```


### 2. 数据保存逻辑修改

**文件**: `backend/apps/automation/services/insurance/preservation_quote_service.py`

在 `_save_premium_results` 方法中，从 API 响应的 `data` 字段提取费率信息并保存：

```python
async def _save_premium_results(self, quote, results):
    for result in results:
        # 从 response_data 中提取费率信息
        rate_data = {}
        if result.response_data and isinstance(result.response_data, dict):
            rate_data = result.response_data.get("data", {})
        
        insurance_quote = InsuranceQuote(
            preservation_quote=quote,
            company_id=result.company.c_id,
            company_code=result.company.c_code,
            company_name=result.company.c_name,
            premium=result.premium,
            # 保存费率信息
            min_premium=rate_data.get("minPremium"),
            min_amount=rate_data.get("minAmount"),
            max_amount=rate_data.get("maxAmount"),
            min_rate=rate_data.get("minRate"),
            max_rate=rate_data.get("maxRate"),
            max_apply_amount=rate_data.get("maxApplyAmount"),
            status=status,
            error_message=result.error_message,
            response_data=result.response_data,
        )
```

### 3. Admin 界面修改

**文件**: `backend/apps/automation/admin/preservation_quote_admin.py`

修改 `InsuranceQuoteInline` 类，添加三个新的显示方法：

#### 3.1 价格显示 (prices_display)

显示三个价格，使用不同颜色区分：
- 最低收费1：绿色
- 最低收费2：青色
- 最高收费：红色

#### 3.2 费率显示 (rates_display)

显示两个费率：
- 最低费率：绿色
- 最高费率：红色

#### 3.3 最高保全金额显示 (max_apply_amount_display)

显示最高保全金额，蓝色字体。

### 4. 数据库迁移

生成并应用迁移：

```bash
# 生成迁移文件
python manage.py makemigrations automation

# 应用迁移
python manage.py migrate automation
```

迁移文件：`0008_insurancequote_max_amount_and_more.py`

## 显示效果

### Admin 列表页

在询价任务详情页的内联表格中，每个保险公司显示：

| 保险公司 | 收费标准 | 费率 | 最高保全金额 | 状态 |
|---------|---------|------|-------------|------|
| XX保险 | 最低1: ¥500.00<br>最低2: ¥500.00<br>最高: ¥500.00 | 最低: 0.002<br>最高: 0.005 | ¥1,000,000,000.00 | ✅ 成功 |

### 颜色方案

- **最低收费1**: 绿色 (#28a745) - 表示最优惠
- **最低收费2**: 青色 (#17a2b8) - 表示次优惠
- **最高收费**: 红色 (#dc3545) - 表示最贵
- **最低费率**: 绿色 (#28a745)
- **最高费率**: 红色 (#dc3545)
- **最高保全金额**: 蓝色 (#007bff)


## 数据流程

1. **API 调用** → `CourtInsuranceClient.fetch_premium()`
   - 发送询价请求
   - 接收包含 `data` 字段的 JSON 响应

2. **数据解析** → `CourtInsuranceClient.fetch_premium()`
   - 从 `response_data.data` 提取费率信息
   - 打印到控制台（调试用）

3. **数据保存** → `PreservationQuoteService._save_premium_results()`
   - 从 `result.response_data.data` 提取费率信息
   - 保存到 `InsuranceQuote` 模型的新字段

4. **数据展示** → `InsuranceQuoteInline`
   - 从数据库读取费率信息
   - 格式化显示在 Admin 界面

## API 响应格式

```json
{
  "code": 200,
  "message": null,
  "timestamp": 1764345285256,
  "data": {
    "minPremium": "500",
    "minAmount": "500",
    "minRate": "0.002",
    "maxRate": "0.005",
    "maxAmount": "500",
    "maxApplyAmount": "1000000000"
  }
}
```

## 注意事项

### 1. 数据类型

- **价格字段** (`min_premium`, `min_amount`, `max_amount`, `max_apply_amount`):
  - 类型: `DecimalField(max_digits=15, decimal_places=2)`
  - 单位: 元
  - 显示: 千分位格式，保留2位小数

- **费率字段** (`min_rate`, `max_rate`):
  - 类型: `DecimalField(max_digits=10, decimal_places=6)`
  - 单位: 无（比例）
  - 显示: 原始数值（如 0.002）

### 2. 空值处理

所有新字段都允许 `null=True, blank=True`，因为：
- 失败的询价不会有费率信息
- 某些保险公司可能不返回完整的费率信息

### 3. 向后兼容

- 原有的 `premium` 字段保留，用于快速排序和显示
- 新字段作为补充信息，提供更详细的费率数据

## 相关文件

- `backend/apps/automation/models.py` - 数据模型
- `backend/apps/automation/services/insurance/preservation_quote_service.py` - 数据保存
- `backend/apps/automation/admin/preservation_quote_admin.py` - Admin 界面
- `backend/apps/automation/migrations/0008_insurancequote_max_amount_and_more.py` - 数据库迁移
