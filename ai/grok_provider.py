from typing import Optional
from openai import OpenAI
from .openai_base_provider import OpenAIBaseProvider
import os
import logging

logger = logging.getLogger(__name__)

class GrokProvider(OpenAIBaseProvider):
    def __init__(self):
        super().__init__(
            env_prefix='GROK',
            default_model='grok-2-latest',
            default_api_base='https://api.x.ai/v1'
        )