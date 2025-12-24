import httpx
import json

from apps.automation.services.ai import get_ollama_base_url


def chat(model: str, messages: list[dict], base_url: str | None = None) -> dict:
    """
    调用Ollama API进行聊天
    
    Args:
        model: 模型名称
        messages: 消息列表
        base_url: Ollama服务的基础URL，如果不提供则从 Django settings 读取
    
    Returns:
        dict: Ollama API返回的JSON响应
    """
    base = base_url or get_ollama_base_url()
    url = base.rstrip("/") + "/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "stream": False  # 设置为False以获取完整响应而不是流式响应
    }
    
    try:
        with httpx.Client(timeout=120) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            
            # 尝试解析JSON响应
            try:
                return resp.json()
            except json.JSONDecodeError as e:
                # 如果JSON解析失败，可能是流式响应，尝试读取最后一行
                text = resp.text.strip()
                if text:
                    # 尝试解析每一行JSON（流式响应格式）
                    lines = text.split('\n')
                    last_valid_json = None
                    for line in lines:
                        line = line.strip()
                        if line:
                            try:
                                data = json.loads(line)
                                if 'message' in data:
                                    last_valid_json = data
                            except json.JSONDecodeError:
                                continue
                    
                    if last_valid_json:
                        return last_valid_json
                
                raise ValueError(f"无法解析Ollama响应: {str(e)}\n响应内容: {text[:500]}")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise ConnectionError(
                f"Ollama API未找到 (404)。请检查：\n"
                f"1. Ollama服务是否运行在 {base}\n"
                f"2. 模型 '{model}' 是否已安装 (运行: ollama pull {model})\n"
                f"3. API路径是否正确"
            )
        raise ConnectionError(f"Ollama API错误 ({e.response.status_code}): {e.response.text}")
    except httpx.ConnectError as e:
        raise ConnectionError(
            f"无法连接到Ollama服务 ({base})。请确保Ollama服务正在运行。\n"
            f"错误详情: {str(e)}"
        )
    except Exception as e:
        raise RuntimeError(f"调用Ollama API时发生错误: {str(e)}")
