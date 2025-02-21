from typing import Optional
import google.generativeai as genai
from .base import BaseAIProvider
import os
import logging

logger = logging.getLogger(__name__)

class GeminiProvider(BaseAIProvider):
    def __init__(self):
        self.model = None
        self.model_name = None  # 添加model_name属性
        
    async def initialize(self, **kwargs):
        """初始化Gemini客户端"""
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("未设置GEMINI_API_KEY环境变量")

        # 使用传入的model参数，如果没有才使用默认值
        if not self.model_name:  # 如果model_name还没设置
            self.model_name = kwargs.get('model')
        
        if not self.model_name:  # 如果kwargs中也没有model
            self.model_name = 'gemini-pro'  # 最后才使用默认值
            
        logger.info(f"初始化Gemini模型: {self.model_name}")
        
        # 配置安全设置 - 只使用基本类别
        safety_settings = [
            {
                "category": "HARM_CATEGORY_HARASSMENT",
                "threshold": "BLOCK_NONE"
            },
            {
                "category": "HARM_CATEGORY_HATE_SPEECH",
                "threshold": "BLOCK_NONE"
            },
            {
                "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "threshold": "BLOCK_NONE"
            },
            {
                "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                "threshold": "BLOCK_NONE"
            }
        ]
            
        genai.configure(api_key=api_key)
        # 使用self.model_name初始化模型
        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            safety_settings=safety_settings
        )
        
    async def process_message(self, 
                            message: str, 
                            prompt: Optional[str] = None,
                            **kwargs) -> str:
        """处理消息"""
        try:
            if not self.model:
                await self.initialize(**kwargs)
                
            chat = self.model.start_chat()
            
            logger.info(f"实际使用的Gemini模型: {self.model_name}")

            # 组合提示词和消息
            if prompt:
                full_message = f"{prompt}\n\n{message}"
            else:
                full_message = message
            
            response = chat.send_message(full_message)
            return response.text
            
        except Exception as e:
            logger.error(f"Gemini处理消息时出错: {str(e)}")
            return f"AI处理失败: {str(e)}" 