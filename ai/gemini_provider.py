from typing import Optional
import google.generativeai as genai
from .base import BaseAIProvider
import os
import logging

logger = logging.getLogger(__name__)

class GeminiProvider(BaseAIProvider):
    def __init__(self):
        self.model = None
        
    async def initialize(self, **kwargs):
        """初始化Gemini客户端"""
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("未设置GEMINI_API_KEY环境变量")
            
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-pro')
        
    async def process_message(self, 
                            message: str, 
                            prompt: Optional[str] = None,
                            **kwargs) -> str:
        """处理消息"""
        try:
            if not self.model:
                await self.initialize(**kwargs)
                
            chat = self.model.start_chat()
            if prompt:
                chat.send_message(prompt)
            
            response = chat.send_message(message)
            return response.text
            
        except Exception as e:
            logger.error(f"Gemini处理消息时出错: {str(e)}")
            return f"AI处理失败: {str(e)}" 