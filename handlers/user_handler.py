from models.models import ForwardMode
import re
import logging
import asyncio
from handlers.message_handler import pre_handle

logger = logging.getLogger(__name__)

async def process_forward_rule(client, event, chat_id, rule):
    """处理转发规则（用户模式）"""
    should_forward = False
    message_text = event.message.text or ''
    check_message_text = await pre_handle(message_text)
    # 添加日志
    logger.info(f'处理规则 ID: {rule.id}')
    logger.info(f'消息内容: {message_text}')
    logger.info(f'规则模式: {rule.mode.value}')
    
    # 处理关键字规则
    if rule.mode == ForwardMode.WHITELIST:
        # 白名单模式：必须匹配任一关键字
        for keyword in rule.keywords:
            logger.info(f'检查白名单关键字: {keyword.keyword} (正则: {keyword.is_regex})')
            if keyword.is_regex:
                # 正则表达式匹配
                try:
                    if re.search(keyword.keyword, check_message_text):
                        should_forward = True
                        logger.info(f'正则匹配成功: {keyword.keyword}')
                        break
                except re.error:
                    logger.error(f'正则表达式错误: {keyword.keyword}')
            else:
                # 普通关键字匹配（包含即可，不区分大小写）
                if keyword.keyword.lower() in check_message_text.lower():
                    should_forward = True
                    logger.info(f'关键字匹配成功: {keyword.keyword}')
                    break
    else:
        # 黑名单模式：不能匹配任何关键字
        should_forward = True
        for keyword in rule.keywords:
            logger.info(f'检查黑名单关键字: {keyword.keyword} (正则: {keyword.is_regex})')
            if keyword.is_regex:
                # 正则表达式匹配
                try:
                    if re.search(keyword.keyword, check_message_text):
                        should_forward = False
                        logger.info(f'正则匹配成功，不转发: {keyword.keyword}')
                        break
                except re.error:
                    logger.error(f'正则表达式错误: {keyword.keyword}')
            else:
                # 普通关键字匹配（包含即可，不区分大小写）
                if keyword.keyword.lower() in check_message_text.lower():
                    should_forward = False
                    logger.info(f'关键字匹配成功，不转发: {keyword.keyword}')
                    break
    
    logger.info(f'最终决定: {"转发" if should_forward else "不转发"}')
    
    if should_forward:
        target_chat = rule.target_chat
        target_chat_id = int(target_chat.telegram_chat_id)
        
        try:
            # 如果启用了替换模式，处理文本
            if rule.is_replace and message_text:
                try:
                    # 应用所有替换规则
                    for replace_rule in rule.replace_rules:
                        if replace_rule.pattern == '.*':
                            message_text = replace_rule.content or ''
                            break  # 如果是全文替换，就不继续处理其他规则
                        else:
                            try:
                                message_text = re.sub(
                                    replace_rule.pattern,
                                    replace_rule.content or '',
                                    message_text
                                )
                            except re.error:
                                logger.error(f'替换规则格式错误: {replace_rule.pattern}')
                except Exception as e:
                    logger.error(f'应用替换规则时出错: {str(e)}')
            
            # 如果启用了原始链接，生成链接
            original_link = ''
            if rule.is_original_link:
                original_link = f"\n\n原始消息: https://t.me/c/{str(event.chat_id)[4:]}/{event.message.id}"
            
            if event.message.grouped_id:
                # 等待一段时间以确保收到所有媒体组消息
                await asyncio.sleep(1)
                
                # 收集媒体组的所有消息
                messages = []
                async for message in client.iter_messages(
                    event.chat_id,
                    limit=20,  # 限制搜索范围
                    min_id=event.message.id - 10,
                    max_id=event.message.id + 10
                ):
                    if message.grouped_id == event.message.grouped_id:
                        messages.append(message.id)
                        logger.info(f'找到媒体组消息: ID={message.id}')
                
                # 按照ID排序，确保转发顺序正确
                messages.sort()
                
                # 一次性转发所有消息
                await client.forward_messages(
                    target_chat_id,
                    messages,
                    event.chat_id
                )
                logger.info(f'[用户] 已转发 {len(messages)} 条媒体组消息到: {target_chat.name} ({target_chat_id})')
                
                # 如果有替换过的文本或原始链接，额外发送一条消息
                if (rule.is_replace and message_text and message_text != event.message.text) or original_link:
                    text_to_send = (message_text + original_link) if message_text else original_link
                    await client.send_message(
                        target_chat_id,
                        text_to_send,
                        link_preview=False
                    )
            else:
                # 处理单条消息
                await client.forward_messages(
                    target_chat_id,
                    event.message.id,
                    event.chat_id
                )
                logger.info(f'[用户] 消息已转发到: {target_chat.name} ({target_chat_id})')
                
                # 如果有替换过的文本或原始链接，额外发送一条消息
                if (rule.is_replace and message_text and message_text != event.message.text) or original_link:
                    text_to_send = (message_text + original_link) if message_text else original_link
                    await client.send_message(
                        target_chat_id,
                        text_to_send,
                        link_preview=False
                    )
                
        except Exception as e:
            logger.error(f'转发消息时出错: {str(e)}')
            logger.exception(e) 