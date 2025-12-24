# 验证码识别 API 路由配置

## 路由注册链

验证码识别 API 的路由通过以下层级注册：

```
urls.py (Django)
  └── /api/v1/ → api_v1 (NinjaAPI)
      └── /automation → automation_router
          └── /captcha → captcha_recognition_router
              └── /recognize (POST)
```

## 完整端点路径

**主要端点**: `POST /api/v1/automation/captcha/recognize`

**重定向**: `/api/automation/captcha/recognize` → `/api/v1/automation/captcha/recognize`

## 注册位置

### 1. captcha_recognition_api.py
```python
# backend/apps/automation/api/captcha_recognition_api.py
router = Router(tags=["验证码识别"])

@router.post("/recognize", response=CaptchaRecognizeOut)
def recognize_captcha(request, payload: CaptchaRecognizeIn):
    ...
```

### 2. automation/api/__init__.py
```python
# backend/apps/automation/api/__init__.py
from .captcha_recognition_api import router as captcha_recognition_router

router = Router()
router.add_router("/captcha", captcha_recognition_router)
```

### 3. apiSystem/api.py
```python
# backend/apiSystem/apiSystem/api.py
from apps.automation.api import router as automation_router

api_v1.add_router("/automation", automation_router)
```

### 4. urls.py
```python
# backend/apiSystem/apiSystem/urls.py
from .api import api_v1

urlpatterns = [
    path("api/v1/", api_v1.urls),
    path("api/", api_redirect),  # 重定向到 v1
]
```

## API 文档

访问 `/api/v1/docs` 查看完整的 API 文档，包括验证码识别端点的详细说明。

## 测试端点

使用 curl 测试：

```bash
curl -X POST http://localhost:8000/api/v1/automation/captcha/recognize \
  -H "Content-Type: application/json" \
  -d '{"image_base64": "iVBORw0KGgoAAAANSUhEUgAAAAUA..."}'
```

预期响应：
```json
{
  "success": true,
  "text": "AB12",
  "processing_time": 0.234,
  "error": null
}
```

## 验证状态

✅ 路由器已正确注册  
✅ 端点可通过 `/api/v1/automation/captcha/recognize` 访问  
✅ API 文档已自动生成  
✅ 符合项目架构规范
