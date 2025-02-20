from .base import BaseAIProvider
from .openai_provider import OpenAIProvider
from .gemini_provider import GeminiProvider
from .deepseek_provider import DeepSeekProvider
from .qwen_provider import QwenProvider
from .grok_provider import GrokProvider
from .claude_provider import ClaudeProvider
import os

def get_ai_provider(model=None):
    """获取AI提供者实例"""
    if not model:
        model = os.getenv('DEFAULT_AI_MODEL', 'gemini-2.0-flash')
        
    # 根据模型名称选择对应的提供者
    provider = None
    if any(model.startswith(prefix) for prefix in ('gpt-', 'o1', 'o3', 'chatgpt')):
        provider = OpenAIProvider()
    elif model.startswith('gemini-'):
        provider = GeminiProvider()
    elif model.startswith('deepseek-'):
        provider = DeepSeekProvider()
    elif model.startswith('qwen-'):
        provider = QwenProvider()
    elif model.startswith('grok-'):
        provider = GrokProvider()
    elif model.startswith('claude-'):
        provider = ClaudeProvider()
    else:
        raise ValueError(f"不支持的模型: {model}")
        
    return provider

__all__ = [
    'BaseAIProvider',
    'OpenAIProvider',
    'GeminiProvider',
    'DeepSeekProvider',
    'QwenProvider',
    'GrokProvider',
    'ClaudeProvider',
    'get_ai_provider'
]