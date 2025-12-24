# CaptchaRecognizer 扩展指南

## 概述

CaptchaRecognizer 提供可插拔的验证码识别接口，支持多种识别服务。

## 接口定义

```python
from abc import ABC, abstractmethod
from typing import Optional

class CaptchaRecognizer(ABC):
    """验证码识别器接口"""
    
    @abstractmethod
    def recognize(self, image_bytes: bytes) -> Optional[str]:
        """从字节流识别验证码"""
        pass
    
    @abstractmethod
    def recognize_from_element(self, page, selector: str) -> Optional[str]:
        """从页面元素识别验证码"""
        pass
```

## 内置实现

### DdddocrRecognizer

使用 ddddocr 库的默认实现：

```python
from apps.automation.services.scraper.core.captcha_recognizer import DdddocrRecognizer

# 创建识别器
recognizer = DdddocrRecognizer(show_ad=False)

# 从字节流识别
with open('captcha.png', 'rb') as f:
    image_bytes = f.read()
result = recognizer.recognize(image_bytes)
print(result)  # '1234'

# 从页面元素识别
result = recognizer.recognize_from_element(page, "#captcha-img")
```

## 自定义实现

### 创建自定义识别器

```python
from apps.automation.services.scraper.core.captcha_recognizer import CaptchaRecognizer
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class CustomRecognizer(CaptchaRecognizer):
    """自定义验证码识别器"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
    
    def recognize(self, image_bytes: bytes) -> Optional[str]:
        """使用第三方 API 识别"""
        try:
            # 调用第三方 API
            result = self._call_api(image_bytes)
            return result.strip()
        except Exception as e:
            logger.error(f"识别失败: {e}")
            return None
    
    def recognize_from_element(self, page, selector: str) -> Optional[str]:
        """从页面元素识别"""
        try:
            element = page.locator(selector)
            image_bytes = element.screenshot()
            return self.recognize(image_bytes)
        except Exception as e:
            logger.error(f"获取验证码失败: {e}")
            return None
    
    def _call_api(self, image_bytes: bytes) -> str:
        """调用第三方 API"""
        # 实现 API 调用逻辑
        pass
```

### 使用自定义识别器

```python
from apps.automation.services.scraper.sites.court_zxfw import CourtZxfwService

# 创建自定义识别器
custom_recognizer = CustomRecognizer(api_key="your-api-key")

# 注入到服务
service = CourtZxfwService(
    page,
    context,
    captcha_recognizer=custom_recognizer
)

# 服务会使用自定义识别器
result = service.login(account, password)
```

## 错误处理

识别器应该：
1. **返回 None 而不是抛出异常**
2. **记录详细的错误日志**
3. **处理所有可能的异常**

```python
def recognize(self, image_bytes: bytes) -> Optional[str]:
    """识别验证码"""
    if not image_bytes:
        logger.warning("图片字节流为空")
        return None
    
    try:
        result = self._do_recognition(image_bytes)
        logger.info(f"识别成功: {result}")
        return result
    except Exception as e:
        logger.error(f"识别失败: {e}", exc_info=True)
        return None  # 不抛出异常
```

## 依赖注入

### 在 CourtZxfwService 中使用

```python
from apps.automation.services.scraper.sites.court_zxfw import CourtZxfwService
from apps.automation.services.scraper.core.captcha_recognizer import DdddocrRecognizer

# 方式 1: 使用默认识别器
service = CourtZxfwService(page, context)

# 方式 2: 注入自定义识别器
custom_recognizer = DdddocrRecognizer(show_ad=False)
service = CourtZxfwService(
    page,
    context,
    captcha_recognizer=custom_recognizer
)
```

## 测试

### 单元测试

```python
import pytest
from your_module import CustomRecognizer

def test_recognize_valid_image():
    recognizer = CustomRecognizer(api_key="test-key")
    
    with open('test_captcha.png', 'rb') as f:
        image_bytes = f.read()
    
    result = recognizer.recognize(image_bytes)
    assert result is not None
    assert len(result) > 0

def test_recognize_invalid_image():
    recognizer = CustomRecognizer(api_key="test-key")
    
    # 无效图片应该返回 None
    result = recognizer.recognize(b"invalid data")
    assert result is None
```

### Mock 测试

```python
from unittest.mock import Mock

def test_service_uses_injected_recognizer():
    # 创建 mock 识别器
    mock_recognizer = Mock()
    mock_recognizer.recognize_from_element.return_value = "MOCK1234"
    
    # 注入到服务
    service = CourtZxfwService(
        page,
        context,
        captcha_recognizer=mock_recognizer
    )
    
    # 验证使用了注入的识别器
    result = service._recognize_captcha()
    assert result == "MOCK1234"
    mock_recognizer.recognize_from_element.assert_called_once()
```

## 最佳实践

1. **实现两个方法**：`recognize()` 和 `recognize_from_element()`
2. **错误返回 None**：不要抛出异常到调用者
3. **记录详细日志**：帮助调试识别问题
4. **清理识别结果**：去除空格、特殊字符
5. **支持重试**：在服务层实现重试逻辑

## 常见问题

### Q: 如何切换识别服务？

A: 实现新的 CaptchaRecognizer 子类，然后通过依赖注入使用：

```python
new_recognizer = YourCustomRecognizer()
service = CourtZxfwService(page, context, captcha_recognizer=new_recognizer)
```

### Q: 识别失败怎么办？

A: 识别器返回 None，服务层会处理重试逻辑。

### Q: 如何提高识别准确率？

A: 
1. 使用更好的识别服务
2. 预处理图片（去噪、二值化）
3. 增加重试次数
4. 使用多个识别服务投票

## 参考

- [CaptchaRecognizer 接口](../services/scraper/core/captcha_recognizer.py)
- [CourtZxfwService 文档](COURT_ZXFW_SERVICE.md)
- [依赖注入测试](../tests/test_court_zxfw_di.py)
