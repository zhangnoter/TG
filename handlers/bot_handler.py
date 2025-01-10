from telethon import events, Button
from models import get_session, Chat, ForwardRule, ForwardMode, Keyword
import re
import os
import logging
import json
from telegram import InputMediaPhoto, InputMediaVideo, InputMediaDocument, InputMediaAudio
import tempfile
import asyncio

logger = logging.getLogger(__name__)

# 规则配置字段定义
RULE_SETTINGS = {
    'mode': {
        'display_name': '转发模式',
        'values': {
            ForwardMode.WHITELIST: '白名单',
            ForwardMode.BLACKLIST: '黑名单'
        },
        'toggle_action': 'toggle_mode',
        'toggle_func': lambda current: ForwardMode.BLACKLIST if current == ForwardMode.WHITELIST else ForwardMode.WHITELIST
    },
    'use_bot': {
        'display_name': '转发方式',
        'values': {
            True: '使用机器人',
            False: '使用用户账号'
        },
        'toggle_action': 'toggle_bot',
        'toggle_func': lambda current: not current
    },
    'is_replace': {
        'display_name': '替换模式',
        'values': {
            True: '替换',
            False: '不替换'
        },
        'toggle_action': 'toggle_replace',
        'toggle_func': lambda current: not current
    }
}

# 在文件顶部添加用户状态字典
USER_STATES = {}  # {user_id: {'current_rule_id': rule_id}}

def get_user_id():
    """获取用户ID，确保环境变量已加载"""
    user_id_str = os.getenv('USER_ID')
    if not user_id_str:
        logger.error('未设置 USER_ID 环境变量')
        raise ValueError('必须在 .env 文件中设置 USER_ID')
    return int(user_id_str)

def create_buttons(rule):
    """根据配置创建设置按钮"""
    buttons = []
    # 为每个配置字段创建按钮
    for field, config in RULE_SETTINGS.items():
        current_value = getattr(rule, field)
        display_value = config['values'][current_value]
        button_text = f"{config['display_name']}: {display_value}"
        # 简化回调数据格式
        callback_data = f"{config['toggle_action']}:{rule.id}"
        buttons.append([Button.inline(button_text, callback_data)])
    
    # 添加删除按钮
    buttons.append([Button.inline(
        '❌ 删除',
        f"delete:{rule.id}"  # 简化回调数据
    )])
    return buttons

def create_settings_text(rule):
    """创建设置信息文本"""
    text = f'管理转发规则\n目标聊天: {rule.target_chat.name}\n'
    return text

async def handle_command(client, event):
    """处理机器人命令"""
    # 只处理来自管理员的消息
    user_id = event.sender_id
    if user_id != get_user_id():
        return
        
    # 处理命令逻辑
    message = event.message
    if not message.text:
        return
        
    if message.text.startswith('/'):
        parts = message.text.split()
        command = parts[0][1:]
        
        if command == 'bind':
            if len(parts) != 2:
                await event.reply('用法: /bind <目标聊天链接>\n例如: /bind https://t.me/channel_name')
                return
                
            target_link = parts[1]
            source_chat = await event.get_chat()
            
            try:
                # 从链接中提取目标聊天的用户名或ID
                if '/joinchat/' in target_link or 't.me/+' in target_link:
                    await event.reply('暂不支持私有链接，请使用公开链接')
                    return
                else:
                    # 公开链接，格式如 https://t.me/channel_name
                    channel_name = target_link.split('/')[-1]
                    try:
                        # 获取目标聊天的实体信息
                        target_chat = await client.get_entity(channel_name)
                    except ValueError:
                        await event.reply('无法获取目标聊天信息，请确保链接正确')
                        return
                
                # 保存到数据库
                session = get_session()
                try:
                    # 保存源聊天（链接指向的聊天）
                    source_chat_db = session.query(Chat).filter(
                        Chat.telegram_chat_id == str(target_chat.id)
                    ).first()
                    
                    if not source_chat_db:
                        source_chat_db = Chat(
                            telegram_chat_id=str(target_chat.id),
                            name=target_chat.title if hasattr(target_chat, 'title') else 'Private Chat'
                        )
                        session.add(source_chat_db)
                        session.flush()
                    
                    # 保存目标聊天（当前聊天）
                    target_chat_db = session.query(Chat).filter(
                        Chat.telegram_chat_id == str(source_chat.id)
                    ).first()
                    
                    if not target_chat_db:
                        target_chat_db = Chat(
                            telegram_chat_id=str(source_chat.id),
                            name=source_chat.title if hasattr(source_chat, 'title') else 'Private Chat'
                        )
                        session.add(target_chat_db)
                        session.flush()
                    
                    # 如果当前没有选中的源聊天，就设置为新绑定的聊天
                    if not target_chat_db.current_add_id:
                        target_chat_db.current_add_id = str(target_chat.id)
                    
                    # 创建转发规则
                    rule = ForwardRule(
                        source_chat_id=source_chat_db.id,
                        target_chat_id=target_chat_db.id,
                        mode=ForwardMode.BLACKLIST,
                        use_bot=False,
                        is_replace=False
                    )
                    session.add(rule)
                    session.commit()
                    
                    await event.reply(
                        f'已设置转发规则:\n'
                        f'源聊天: {source_chat_db.name} ({source_chat_db.telegram_chat_id})\n'
                        f'目标聊天: {target_chat_db.name} ({target_chat_db.telegram_chat_id})\n'
                        f'请使用 /add 或 /add_regex 添加关键字'
                    )
                    
                except Exception as e:
                    session.rollback()
                    logger.error(f'保存转发规则时出错: {str(e)}')
                    await event.reply('设置转发规则时出错，请检查日志')
                finally:
                    session.close()
                    
            except Exception as e:
                logger.error(f'设置转发规则时出错: {str(e)}')
                await event.reply('设置转发规则时出错，请检查日志')
                return

        elif command == 'settings':
            current_chat = await event.get_chat()
            current_chat_id = str(current_chat.id)
            # 添加日志
            logger.info(f'正在查找聊天ID: {current_chat_id} 的转发规则')
            
            session = get_session()
            try:
                # 添加日志，显示数据库中的所有聊天
                all_chats = session.query(Chat).all()
                logger.info('数据库中的所有聊天:')
                for chat in all_chats:
                    logger.info(f'ID: {chat.id}, telegram_chat_id: {chat.telegram_chat_id}, name: {chat.name}')
                
                current_chat_db = session.query(Chat).filter(
                    Chat.telegram_chat_id == current_chat_id
                ).first()
                
                if not current_chat_db:
                    logger.info(f'在数据库中找不到聊天ID: {current_chat_id}')
                    await event.reply('当前聊天没有任何转发规则')
                    return
                
                # 添加日志
                logger.info(f'找到聊天: {current_chat_db.name} (ID: {current_chat_db.id})')
                
                # 查找以当前聊天为目标的规则
                rules = session.query(ForwardRule).filter(
                    ForwardRule.target_chat_id == current_chat_db.id  # 改为 target_chat_id
                ).all()
                
                # 添加日志
                logger.info(f'找到 {len(rules)} 条转发规则')
                for rule in rules:
                    logger.info(f'规则ID: {rule.id}, 源聊天: {rule.source_chat.name}, 目标聊天: {rule.target_chat.name}')
                
                if not rules:
                    await event.reply('当前聊天没有任何转发规则')
                    return
                
                # 创建规则选择按钮
                buttons = []
                for rule in rules:
                    source_chat = rule.source_chat  # 显示源聊天
                    button_text = f'来自: {source_chat.name}'  # 改为"来自"
                    callback_data = f"rule_settings:{rule.id}"
                    buttons.append([Button.inline(button_text, callback_data)])
                
                await event.reply('请选择要管理的转发规则:', buttons=buttons)
                
            except Exception as e:
                logger.error(f'获取转发规则时出错: {str(e)}')
                await event.reply('获取转发规则时出错，请检查日志')
            finally:
                session.close()

        elif command == 'switch':
            # 显示可切换的规则列表
            current_chat = await event.get_chat()
            current_chat_id = str(current_chat.id)
            
            session = get_session()
            try:
                current_chat_db = session.query(Chat).filter(
                    Chat.telegram_chat_id == current_chat_id
                ).first()
                
                if not current_chat_db:
                    await event.reply('当前聊天没有任何转发规则')
                    return
                
                rules = session.query(ForwardRule).filter(
                    ForwardRule.target_chat_id == current_chat_db.id
                ).all()
                
                if not rules:
                    await event.reply('当前聊天没有任何转发规则')
                    return
                
                # 创建规则选择按钮
                buttons = []
                for rule in rules:
                    source_chat = rule.source_chat
                    # 标记当前选中的规则
                    current = current_chat_db.current_add_id == source_chat.telegram_chat_id
                    button_text = f'{"✓ " if current else ""}来自: {source_chat.name}'
                    callback_data = f"switch:{source_chat.telegram_chat_id}"
                    buttons.append([Button.inline(button_text, callback_data)])
                
                await event.reply('请选择要管理的转发规则:', buttons=buttons)
            finally:
                session.close()

        elif command in ['add', 'add_regex']:
            if len(parts) < 2:
                await event.reply(f'用法: /{command} <关键字1> [关键字2] [关键字3] ...')
                return
                
            keywords = parts[1:]  # 获取所有关键字
            session = get_session()
            try:
                # 获取当前聊天
                current_chat = await event.get_chat()
                current_chat_db = session.query(Chat).filter(
                    Chat.telegram_chat_id == str(current_chat.id)
                ).first()
                
                if not current_chat_db:
                    await event.reply('当前聊天没有任何转发规则')
                    return
                
                if not current_chat_db.current_add_id:
                    await event.reply('请先使用 /switch 选择一个源聊天')
                    return
                
                # 查找对应的规则
                source_chat = session.query(Chat).filter(
                    Chat.telegram_chat_id == current_chat_db.current_add_id
                ).first()
                
                if not source_chat:
                    await event.reply('源聊天不存在')
                    return
                
                rule = session.query(ForwardRule).filter(
                    ForwardRule.source_chat_id == source_chat.id,
                    ForwardRule.target_chat_id == current_chat_db.id
                ).first()
                
                if not rule:
                    await event.reply('转发规则不存在')
                    return
                
                # 添加所有关键字
                added_keywords = []
                for keyword in keywords:
                    new_keyword = Keyword(
                        rule_id=rule.id,
                        keyword=keyword,
                        is_regex=(command == 'add_regex')
                    )
                    session.add(new_keyword)
                    added_keywords.append(keyword)
                
                session.commit()
                
                # 构建回复消息
                keyword_type = "正则" if command == "add_regex" else "关键字"
                keywords_text = '\n'.join(f'- {k}' for k in added_keywords)
                await event.reply(
                    f'已添加{keyword_type}:\n{keywords_text}\n'
                    f'当前规则: 来自 {source_chat.name}'
                )
            finally:
                session.close()

async def handle_callback(event):
    """处理按钮回调"""
    try:
        data = event.data.decode()
        action, rule_id = data.split(':')
        rule_id = int(rule_id)
        user_id = event.sender_id
        
        # 获取消息对象
        message = await event.get_message()
        
        if action == 'switch':
            session = get_session()
            try:
                # 获取当前聊天
                current_chat = await event.get_chat()
                current_chat_db = session.query(Chat).filter(
                    Chat.telegram_chat_id == str(current_chat.id)
                ).first()
                
                if not current_chat_db:
                    await event.answer('当前聊天不存在')
                    return
                
                # 更新当前选中的源聊天
                current_chat_db.current_add_id = rule_id  # 这里的 rule_id 实际上是源聊天的 telegram_chat_id
                session.commit()
                
                # 更新按钮显示
                message = await event.get_message()
                rules = session.query(ForwardRule).filter(
                    ForwardRule.target_chat_id == current_chat_db.id
                ).all()
                
                buttons = []
                for rule in rules:
                    source_chat = rule.source_chat
                    current = source_chat.telegram_chat_id == rule_id
                    button_text = f'{"✓ " if current else ""}来自: {source_chat.name}'
                    callback_data = f"switch:{source_chat.telegram_chat_id}"
                    buttons.append([Button.inline(button_text, callback_data)])
                
                await message.edit('请选择要管理的转发规则:', buttons=buttons)
                source_chat = session.query(Chat).filter(
                    Chat.telegram_chat_id == rule_id
                ).first()
                await event.answer(f'已切换到: {source_chat.name if source_chat else "未知聊天"}')
            finally:
                session.close()
                
        elif action == 'rule_settings':
            session = get_session()
            try:
                rule = session.query(ForwardRule).get(rule_id)
                if not rule:
                    await event.answer('规则不存在')
                    return
                
                await message.edit(
                    create_settings_text(rule),
                    buttons=create_buttons(rule)
                )
            finally:
                session.close()
                
        elif action in [config['toggle_action'] for config in RULE_SETTINGS.values()]:
            session = get_session()
            try:
                rule = session.query(ForwardRule).get(rule_id)
                if not rule:
                    await event.answer('规则不存在')
                    return
                
                # 根据配置切换字段值
                for field_name, config in RULE_SETTINGS.items():
                    if action == config['toggle_action']:
                        current_value = getattr(rule, field_name)
                        new_value = config['toggle_func'](current_value)
                        setattr(rule, field_name, new_value)
                        break
                
                session.commit()
                
                await message.edit(
                    create_settings_text(rule),
                    buttons=create_buttons(rule)
                )
                # 找到对应的配置显示名称
                display_name = next(
                    config['display_name'] 
                    for config in RULE_SETTINGS.values() 
                    if config['toggle_action'] == action
                )
                await event.answer(f'已更新{display_name}')
            finally:
                session.close()
                
        elif action == 'delete':
            session = get_session()
            try:
                rule = session.query(ForwardRule).get(rule_id)
                if not rule:
                    await event.answer('规则不存在')
                    return
                
                # 删除关键字
                session.query(Keyword).filter(
                    Keyword.rule_id == rule.id
                ).delete()
                
                # 删除规则
                session.delete(rule)
                session.commit()
                
                # 删除机器人的消息
                await message.delete()
                # 发送新的通知消息
                await event.respond('已删除转发链')
                await event.answer('已删除转发链')
            finally:
                session.close()
                
    except Exception as e:
        logger.error(f'处理按钮回调时出错: {str(e)}')
        await event.answer('处理请求时出错，请检查日志')

# 注册回调处理器
@events.register(events.CallbackQuery)
async def callback_handler(event):
    # 只处理来自管理员的回调
    if event.sender_id != get_user_id():
        return
    await handle_callback(event) 

async def process_forward_rule(client, event, chat_id, rule):
    """处理转发规则（机器人模式）"""
    should_forward = False
    message_text = event.message.text or ''
    
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
                    if re.search(keyword.keyword, message_text):
                        should_forward = True
                        logger.info('正则匹配成功')
                        break
                except re.error:
                    logger.error(f'正则表达式错误: {keyword.keyword}')
            else:
                # 普通关键字匹配（包含即可）
                if keyword.keyword in message_text:
                    should_forward = True
                    logger.info('关键字匹配成功')
                    break
    else:
        # 黑名单模式：不能匹配任何关键字
        should_forward = True
        for keyword in rule.keywords:
            logger.info(f'检查黑名单关键字: {keyword.keyword} (正则: {keyword.is_regex})')
            if keyword.is_regex:
                # 正则表达式匹配
                try:
                    if re.search(keyword.keyword, message_text):
                        should_forward = False
                        logger.info('正则匹配成功，不转发')
                        break
                except re.error:
                    logger.error(f'正则表达式错误: {keyword.keyword}')
            else:
                # 普通关键字匹配（包含即可）
                if keyword.keyword in message_text:
                    should_forward = False
                    logger.info('关键字匹配成功，不转发')
                    break
    
    logger.info(f'最终决定: {"转发" if should_forward else "不转发"}')
    
    if should_forward:
        target_chat = rule.target_chat
        target_chat_id = int(target_chat.telegram_chat_id)
        
        try:
            if event.message.grouped_id:
                # 处理媒体组
                logger.info(f'处理媒体组消息 组ID: {event.message.grouped_id}')
                
                # 等待一小段时间让所有媒体消息到达
                await asyncio.sleep(0.5)
                
                # 收集媒体组的所有消息
                messages = []
                async for message in event.client.iter_messages(
                    chat_id,
                    limit=10,
                    grouped_id=event.message.grouped_id
                ):
                    messages.append(message)
                messages.reverse()  # 保持正确顺序
                
                # 准备媒体组
                media_group = []
                caption_added = False
                
                # 创建临时目录存储下载的媒体文件
                with tempfile.TemporaryDirectory() as temp_dir:
                    for msg in messages:
                        if msg.media:
                            # 下载媒体文件
                            file_path = await msg.download_media(temp_dir)
                            
                            # 根据媒体类型创建适当的InputMedia对象
                            caption = None
                            if not caption_added and msg.text:
                                caption = msg.text
                                caption_added = True
                            
                            if msg.photo:
                                media = InputMediaPhoto(
                                    media=open(file_path, 'rb'),
                                    caption=caption
                                )
                            elif msg.video:
                                media = InputMediaVideo(
                                    media=open(file_path, 'rb'),
                                    caption=caption
                                )
                            elif msg.document:
                                media = InputMediaDocument(
                                    media=open(file_path, 'rb'),
                                    caption=caption
                                )
                            elif msg.audio:
                                media = InputMediaAudio(
                                    media=open(file_path, 'rb'),
                                    caption=caption
                                )
                            else:
                                continue
                            
                            media_group.append(media)
                    
                    # 发送媒体组
                    if media_group:
                        await client.send_media_group(
                            target_chat_id,
                            media=media_group
                        )
                        logger.info(f'[机器人] 媒体组消息已发送到: {target_chat.name} ({target_chat_id})')
                
                # 清理打开的文件
                for media in media_group:
                    media.media.close()
                
            else:
                # 处理单条消息
                if event.message.media:
                    # 下载并重新发送媒体
                    with tempfile.TemporaryDirectory() as temp_dir:
                        file_path = await event.message.download_media(temp_dir)
                        
                        # 如果启用了替换模式，处理文本
                        if rule.is_replace and rule.replace_rule and message_text:
                            try:
                                if rule.replace_rule == '.*':
                                    message_text = rule.replace_content or ''
                                else:
                                    message_text = re.sub(
                                        rule.replace_rule,
                                        rule.replace_content or '',
                                        message_text
                                    )
                            except re.error:
                                logger.error(f'替换规则格式错误: {rule.replace_rule}')
                        
                        # 发送媒体消息
                        await client.send_document(
                            target_chat_id,
                            document=open(file_path, 'rb'),
                            caption=message_text
                        )
                else:
                    # 发送纯文本消息
                    await client.send_message(
                        target_chat_id,
                        message_text
                    )
                
                logger.info(f'[机器人] 消息已发送到: {target_chat.name} ({target_chat_id})')
                
        except Exception as e:
            logger.error(f'发送消息时出错: {str(e)}')
            logger.exception(e) 