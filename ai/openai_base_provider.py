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
        logger.info(f"初始化OpenAI模型: {kwargs.get('model')}")
        
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

            logger.info(f"实际使用的OpenAI模型: {self.model}")
            
            # 所有模型统一使用流式调用
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True
            )
            
            # 收集所有内容
            collected_content = ""
            collected_reasoning = ""
            
            for chunk in completion:
                if not chunk.choices:
                    continue
                    
                delta = chunk.choices[0].delta
                
                # 处理思考内容（如果存在）
                if hasattr(delta, 'reasoning_content') and delta.reasoning_content is not None:
                    collected_reasoning += delta.reasoning_content
                
                # 处理回答内容
                if hasattr(delta, 'content') and delta.content is not None:
                    collected_content += delta.content
            
            # 如果没有内容但有思考过程，可能是思考模型只返回了思考过程
            if not collected_content and collected_reasoning:
                logger.warning("模型只返回了思考过程，没有最终回答")
                # 可以选择返回思考过程或返回错误信息
                # 这里选择返回提示，也可以修改为返回思考内容
                return "模型未能生成有效回答"
            
            return collected_content
            
        except Exception as e:
            logger.error(f"{self.env_prefix} API 调用失败: {str(e)}")
            return f"AI处理失败: {str(e)}" 