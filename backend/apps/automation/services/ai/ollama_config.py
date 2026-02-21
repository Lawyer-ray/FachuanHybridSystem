"""
Ollama 配置文件

通过 LLMConfig 统一读取 Ollama 相关配置（LLMConfig 内部使用 SystemConfigService）。
"""


class OllamaConfig:
    """Ollama 配置类"""

    # 默认值（当配置中未设置时使用）
    DEFAULT_MODEL = "qwen3:0.6b"
    DEFAULT_BASE_URL = "http://localhost:11434"

    @classmethod
    def get_model(cls) -> str:
        """获取 Ollama 模型名称"""
        from apps.core.llm.config import LLMConfig

        return LLMConfig.get_ollama_model()

    @classmethod
    def get_base_url(cls) -> str:
        """获取 Ollama 服务地址"""
        from apps.core.llm.config import LLMConfig

        return LLMConfig.get_ollama_base_url()


# 便捷函数
def get_ollama_model() -> str:
    """获取 Ollama 模型名称"""
    return OllamaConfig.get_model()


def get_ollama_base_url() -> str:
    """获取 Ollama 服务地址"""
    return OllamaConfig.get_base_url()
