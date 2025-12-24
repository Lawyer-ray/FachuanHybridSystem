"""
Ollama 配置文件

从 Django settings 统一读取 Ollama 相关配置。
"""
from django.conf import settings


class OllamaConfig:
    """Ollama 配置类"""
    
    # 默认值（当 settings 中未配置时使用）
    DEFAULT_MODEL = "qwen3:0.6b"
    DEFAULT_BASE_URL = "http://localhost:11434"
    
    @classmethod
    def get_model(cls) -> str:
        """
        获取 Ollama 模型名称
        
        优先从 Django settings.OLLAMA['MODEL'] 读取
        """
        ollama_config = getattr(settings, 'OLLAMA', {})
        return ollama_config.get('MODEL', cls.DEFAULT_MODEL)
    
    @classmethod
    def get_base_url(cls) -> str:
        """
        获取 Ollama 服务地址
        
        优先从 Django settings.OLLAMA['BASE_URL'] 读取
        """
        ollama_config = getattr(settings, 'OLLAMA', {})
        return ollama_config.get('BASE_URL', cls.DEFAULT_BASE_URL)


# 便捷函数
def get_ollama_model() -> str:
    """获取 Ollama 模型名称"""
    return OllamaConfig.get_model()


def get_ollama_base_url() -> str:
    """获取 Ollama 服务地址"""
    return OllamaConfig.get_base_url()
