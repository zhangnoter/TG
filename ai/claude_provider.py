from typing import Optional
import anthropic
from .base import BaseAIProvider
import os
import logging

logger = logging.getLogger(__name__)

class ClaudeProvider(BaseAIProvider):
    def __init__(self):
        self.client = None
        self.model = None
        self.default_model = 'claude-3-5-sonnet-latest'
        
    async def initialize(self, **kwargs):
        """初始化Claude客户端"""
        api_key = os.getenv('CLAUDE_API_KEY')
        if not api_key:
            raise ValueError("未设置CLAUDE_API_KEY环境变量")
            
        self.client = anthropic.Anthropic(api_key=api_key)
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
            
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=messages
            )
            
            return response.content[0].text
            
        except Exception as e:
            logger.error(f"Claude API 调用失败: {str(e)}")
            return f"AI处理失败: {str(e)}" 