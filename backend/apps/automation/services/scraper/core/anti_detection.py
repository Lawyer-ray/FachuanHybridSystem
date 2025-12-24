"""
反爬虫检测对抗
"""
import random
import time
from typing import List


class AntiDetection:
    """反爬虫对抗工具"""
    
    # User-Agent 池
    USER_AGENTS = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]
    
    @staticmethod
    def get_random_user_agent() -> str:
        """获取随机 User-Agent"""
        return random.choice(AntiDetection.USER_AGENTS)
    
    @staticmethod
    def get_browser_context_options() -> dict:
        """
        获取浏览器上下文配置（反检测）
        
        Returns:
            配置字典
        """
        return {
            "viewport": {"width": 1920, "height": 1080},
            "user_agent": AntiDetection.get_random_user_agent(),
            "locale": "zh-CN",
            "timezone_id": "Asia/Shanghai",
            # 伪装地理位置
            "geolocation": {"longitude": 113.264385, "latitude": 23.129112},  # 广州
            "permissions": ["geolocation"],
            # 额外的 HTTP 头
            "extra_http_headers": {
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            },
        }
    
    @staticmethod
    def inject_stealth_script(page):
        """
        注入反检测脚本
        
        Args:
            page: Playwright Page 对象
        """
        # 隐藏 webdriver 特征
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // 伪装 Chrome 插件
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            
            // 伪装语言
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en']
            });
            
            // 伪装 Chrome
            window.chrome = {
                runtime: {}
            };
            
            // 伪装权限
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
        """)
    
    @staticmethod
    def random_delay(min_seconds: float = 0.5, max_seconds: float = 2.0):
        """
        随机延迟（模拟人类操作）
        
        Args:
            min_seconds: 最小延迟秒数
            max_seconds: 最大延迟秒数
        """
        delay = random.uniform(min_seconds, max_seconds)
        time.sleep(delay)
    
    @staticmethod
    def human_like_typing(page, selector: str, text: str, delay_range=(0.05, 0.15)):
        """
        模拟人类打字
        
        Args:
            page: Playwright Page 对象
            selector: 输入框选择器
            text: 要输入的文本
            delay_range: 每个字符的延迟范围（秒）
        """
        page.click(selector)
        for char in text:
            page.keyboard.type(char)
            time.sleep(random.uniform(*delay_range))
    
    @staticmethod
    def random_mouse_move(page):
        """
        随机鼠标移动（增加真实性）
        
        Args:
            page: Playwright Page 对象
        """
        x = random.randint(100, 1800)
        y = random.randint(100, 900)
        page.mouse.move(x, y)


# 全局实例
anti_detection = AntiDetection()
