from handlers.models import ForwardMode
import re
import logging
import asyncio

logger = logging.getLogger(__name__)

async def process_forward_rule(client, event, chat_id, rule):
    """处理转发规则"""
    should_forward = False
    message_text = event.message.text or ''
    
    # 添加日志：开始处理规则
    logger.info(f'开始处理规则 ID: {rule.id}')
    logger.info(f'规则模式: {rule.mode.value}')
    logger.info(f'关键字数量: {len(rule.keywords)}')
    
    # 处理关键字规则
    if rule.mode == ForwardMode.WHITELIST:
        # 白名单模式：必须匹配任一关键字
        for keyword in rule.keywords:
            logger.info(f'检查白名单关键字: {keyword.keyword} (正则: {keyword.is_regex})')
            if keyword.is_regex:
                if re.search(keyword.keyword, message_text):
                    should_forward = True
                    logger.info(f'正则匹配成功: {keyword.keyword}')
                    break
            else:
                if keyword.keyword.lower() in message_text.lower():
                    should_forward = True
                    logger.info(f'关键字匹配成功: {keyword.keyword}')
                    break
    else:
        # 黑名单模式：不能匹配任何关键字
        should_forward = True
        for keyword in rule.keywords:
            logger.info(f'检查黑名单关键字: {keyword.keyword} (正则: {keyword.is_regex})')
            if keyword.is_regex:
                if re.search(keyword.keyword, message_text):
                    should_forward = False
                    logger.info(f'正则匹配成功，不转发: {keyword.keyword}')
                    break
            else:
                if keyword.keyword.lower() in message_text.lower():
                    should_forward = False
                    logger.info(f'关键字匹配成功，不转发: {keyword.keyword}')
                    break
    
    logger.info(f'最终决定: {"转发" if should_forward else "不转发"}')
    
    if should_forward:
        target_chat = rule.target_chat
        target_chat_id = int(target_chat.telegram_chat_id)
        
        try:
            # 直接使用event.message.chat_id作为源聊天
            await client.forward_messages(
                target_chat_id,
                messages=event.message,
                from_peer=event.message.chat_id
            )
            logger.info(f'[用户] 消息已转发到: {target_chat.name} ({target_chat_id})')
        except Exception as e:
            logger.error(f'转发消息时出错: {str(e)}')
            logger.exception(e) 