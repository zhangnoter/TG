from typing import Optional
from openai import OpenAI
from .base import BaseAIProvider
import os
import logging

logger = logging.getLogger(__name__)

class OpenAIBaseProvider(BaseAIProvider):
    def __init__(self, env_prefix: str, default_model: str, default_api_base: str):
        """
        初始化基础OpenAI格式提供者
        
        Args:
            env_prefix: 环境变量前缀，如 'OPENAI', 'GROK', 'DEEPSEEK', 'QWEN'
            default_model: 默认模型名称
            default_api_base: 默认API基础URL
        """
        self.client = None
        self.model = None
        self.env_prefix = env_prefix
        self.default_model = default_model
        
        # 获取环境变量中的 API_BASE，如果为空或只有空格则使用默认值
        api_base = os.getenv(f'{env_prefix}_API_BASE', '').strip()
        self.api_base = api_base if api_base else default_api_base
    
    async def initialize(self, **kwargs):
        """初始化OpenAI客户端"""
        api_key = os.getenv(f'{self.env_prefix}_API_KEY')
        if not api_key:
            raise ValueError(f"未设置{self.env_prefix}_API_KEY环境变量")
            
        self.client = OpenAI(
            api_key=api_key,
            base_url=self.api_base
        )
        self.model = kwargs.get('model', self.default_model)
        
    async def process_message(self, 
                            message: str, 
                            prompt: Optional[str] = None,
                            **kwargs) -> str:
        """处理消息"""
        try:
            if not self.client:
                await self.initialize(**kwargs)
                
            messages = []
            if prompt:
                messages.append({"role": "system", "content": prompt})
            messages.append({"role": "user", "content": message})
            
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=False
            )
            
            return completion.choices[0].message.content
            
        except Exception as e:
            logger.error(f"{self.env_prefix} API 调用失败: {str(e)}")
            return f"AI处理失败: {str(e)}" 