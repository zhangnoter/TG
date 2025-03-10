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
            
        # 检查是否配置了自定义API基础URL
        api_base = os.getenv('CLAUDE_API_BASE', '').strip()
        if api_base:
            logger.info(f"使用自定义Claude API基础URL: {api_base}")
            self.client = anthropic.Anthropic(
                api_key=api_key,
                base_url=api_base
            )
        else:
            # 使用默认URL
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
            
            # 使用流式输出 - 按照官方文档正确实现
            with self.client.messages.stream(
                model=self.model,
                max_tokens=4096,
                messages=messages
            ) as stream:
                # 使用专用的text_stream迭代器直接获取文本
                full_response = ""
                for text in stream.text_stream:
                    full_response += text
        
            return full_response
            
        except Exception as e:
            logger.error(f"Claude API 调用失败: {str(e)}")
            return f"AI处理失败: {str(e)}" 