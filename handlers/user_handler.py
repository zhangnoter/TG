from db.models import ForwardMode
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
                    logger.info('匹配成功')
                    break
            elif keyword.keyword in message_text:
                should_forward = True
                logger.info('匹配成功')
                break
    else:
        # 黑名单模式：不能匹配任何关键字
        should_forward = True
        for keyword in rule.keywords:
            logger.info(f'检查黑名单关键字: {keyword.keyword} (正则: {keyword.is_regex})')
            if keyword.is_regex:
                if re.search(keyword.keyword, message_text):
                    should_forward = False
                    logger.info('匹配成功，不转发')
                    break
            elif keyword.keyword in message_text:
                should_forward = False
                logger.info('匹配成功，不转发')
                break
    
    logger.info(f'最终决定: {"转发" if should_forward else "不转发"}')
    
    if should_forward:
        target_chat = rule.target_chat
        
        # 如果是媒体组的一部分，等待一小段时间收集所有媒体
        if event.message.grouped_id:
            # 等待一小段时间（比如0.5秒）让所有媒体消息都到达
            await asyncio.sleep(0.5)
            # 获取同一组的所有消息
            messages = []
            async for message in client.iter_messages(
                chat_id,
                limit=10,  # 限制查找的消息数量
                grouped_id=event.message.grouped_id
            ):
                messages.append(message)
            
            # 按照正确的顺序发送所有消息
            messages.reverse()  # 反转顺序，因为较新的消息在前面
            for message in messages:
                try:
                    await client.send_message(
                        int(target_chat.telegram_chat_id),
                        message.text if message.text else None,
                        file=message.media
                    )
                except Exception as e:
                    logger.error(f'转发媒体组消息时出错: {str(e)}')
            
            logger.info(f'[用户] 媒体组消息已转发到: {target_chat.name} ({target_chat.telegram_chat_id})')
        else:
            # 如果启用了替换模式
            if rule.is_replace and rule.replace_rule and message_text:
                logger.info('应用替换规则')
                try:
                    # 使用替换规则替换文本
                    if rule.replace_rule == '.*':
                        # 如果规则是 .* 则直接替换整个文本
                        message_text = rule.replace_content or ''
                        logger.info(f'替换全文为: {message_text}')
                    else:
                        # 否则使用正则替换
                        message_text = re.sub(
                            rule.replace_rule,
                            rule.replace_content or '',
                            message_text
                        )
                        logger.info(f'替换后文本: {message_text}')
                except re.error:
                    logger.error(f'替换规则格式错误: {rule.replace_rule}')
            
            # 转发消息
            try:
                await client.send_message(
                    int(target_chat.telegram_chat_id),
                    message_text,
                    file=event.message.media
                )
                logger.info(f'[用户] 消息已转发到: {target_chat.name} ({target_chat.telegram_chat_id})')
            except Exception as e:
                logger.error(f'转发消息时出错: {str(e)}')
                logger.exception(e)  # 添加详细的错误堆栈 