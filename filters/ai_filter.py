import logging
from handlers.message_handler import ai_handle
from filters.base_filter import BaseFilter
from filters.keyword_filter import KeywordFilter
from utils.common import check_keywords

logger = logging.getLogger(__name__)

class AIFilter(BaseFilter):
    """
    AI处理过滤器，使用AI处理消息文本
    """
    
    async def _process(self, context):
        """
        使用AI处理消息文本
        
        Args:
            context: 消息上下文
            
        Returns:
            bool: 是否继续处理
        """
        rule = context.rule
        message_text = context.message_text
        original_message_text = context.original_message_text

        logger.info(f"AIFilter处理消息前，context: {context.__dict__}")
        try:
            if not rule.is_ai:
                logger.info("AI处理未开启，返回原始消息")
                return True

            # 处理媒体组消息
            if context.is_media_group:
                logger.info(f"is_media_group: {context.is_media_group}")
            
            # 如果有消息文本，使用AI处理
            if original_message_text:
                try:
                    processed_text = await ai_handle(message_text, rule)
                    context.message_text = processed_text
                    
                    # 如果需要在AI处理后再次检查关键字
                    if rule.is_keyword_after_ai:
                        should_forward = await check_keywords(rule, processed_text)
                        
                        if not should_forward:
                            logger.info('AI处理后的文本未通过关键字检查，取消转发')
                            context.should_forward = False
                            return False
                except Exception as e:
                    logger.error(f'AI处理消息时出错: {str(e)}')
                    context.errors.append(f"AI处理错误: {str(e)}")
                    # 即使AI处理失败，仍然继续处理
            return True 
        finally:
            logger.info(f"AIFilter处理消息后，context: {context.__dict__}")
