from typing import Optional
import openai
from .base import BaseAIProvider
import os
import logging
from .openai_base_provider import OpenAIBaseProvider

logger = logging.getLogger(__name__)

class OpenAIProvider(OpenAIBaseProvider):
    def __init__(self):
        super().__init__(
            env_prefix='OPENAI',
            default_model='gpt-4o-mini',
            default_api_base='https://api.openai.com/v1'
        )

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
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"OpenAI处理消息时出错: {str(e)}")
            return f"AI处理失败: {str(e)}"