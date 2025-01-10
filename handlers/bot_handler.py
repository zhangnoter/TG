from telethon import events, Button
from models import get_session, Chat, ForwardRule, ForwardMode, Keyword, ReplaceRule
import re
import os
import logging
import json
import tempfile
import asyncio
from enums.enums import ForwardMode, PreviewMode, MessageMode
from sqlalchemy.exc import IntegrityError

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
    },
    'message_mode': {
        'display_name': '消息模式',
        'values': {
            MessageMode.MARKDOWN: 'Markdown',
            MessageMode.HTML: 'HTML'
        },
        'toggle_action': 'toggle_message_mode',
        'toggle_func': lambda current: MessageMode.HTML if current == MessageMode.MARKDOWN else MessageMode.MARKDOWN
    },
    'is_preview': {
        'display_name': '预览模式',
        'values': {
            PreviewMode.ON: '开启',
            PreviewMode.OFF: '关闭',
            PreviewMode.FOLLOW: '跟随原消息'
        },
        'toggle_action': 'toggle_preview',
        'toggle_func': lambda current: {
            PreviewMode.ON: PreviewMode.OFF,
            PreviewMode.OFF: PreviewMode.FOLLOW,
            PreviewMode.FOLLOW: PreviewMode.ON
        }[current]
    }
}


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
                    
                except IntegrityError:
                    session.rollback()
                    await event.reply(
                        f'已存在相同的转发规则:\n'
                        f'源聊天: {source_chat_db.name}\n'
                        f'目标聊天: {target_chat_db.name}\n'
                        f'如需修改请使用 /settings 命令'
                    )
                    return
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

        elif command == 'replace':
            if len(parts) < 2:
                await event.reply('用法: /replace <匹配规则> [替换内容]\n例如:\n/replace 广告  # 删除匹配内容\n/replace 广告 [已替换]\n/replace .* 完全替换整个文本')
                return
                
            pattern = parts[1]
            # 如果没有提供替换内容，默认替换为空字符串
            content = ' '.join(parts[2:]) if len(parts) > 2 else ''
            
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
                
                # 添加替换规则
                new_replace_rule = ReplaceRule(
                    rule_id=rule.id,
                    pattern=pattern,
                    content=content  # 可能为空字符串
                )
                session.add(new_replace_rule)
                
                # 确保启用替换模式
                if not rule.is_replace:
                    rule.is_replace = True
                
                session.commit()
                
                # 检查是否是全文替换
                rule_type = "全文替换" if pattern == ".*" else "正则替换"
                action_type = "删除" if not content else "替换"
                
                await event.reply(
                    f'已添加{rule_type}规则:\n'
                    f'匹配: {pattern}\n'
                    f'动作: {action_type}\n'
                    f'{"替换为: " + content if content else "删除匹配内容"}\n'
                    f'当前规则: 来自 {source_chat.name}'
                )
                
            except Exception as e:
                session.rollback()
                logger.error(f'添加替换规则时出错: {str(e)}')
                await event.reply('添加替换规则时出错，请检查日志')
            finally:
                session.close()

        elif command == 'list_keyword':
            session = get_session()
            try:
                # 获取当前聊天
                current_chat = await event.get_chat()
                current_chat_db = session.query(Chat).filter(
                    Chat.telegram_chat_id == str(current_chat.id)
                ).first()
                
                if not current_chat_db or not current_chat_db.current_add_id:
                    await event.reply('请先使用 /switch 选择一个源聊天')
                    return
                
                # 查找对应的规则
                source_chat = session.query(Chat).filter(
                    Chat.telegram_chat_id == current_chat_db.current_add_id
                ).first()
                
                rule = session.query(ForwardRule).filter(
                    ForwardRule.source_chat_id == source_chat.id,
                    ForwardRule.target_chat_id == current_chat_db.id
                ).first()
                
                if not rule:
                    await event.reply('转发规则不存在')
                    return
                
                # 获取所有关键字
                keywords = session.query(Keyword).filter(
                    Keyword.rule_id == rule.id
                ).all()
                
                await show_list(
                    event,
                    'keyword',
                    keywords,
                    lambda i, kw: f'{i}. {kw.keyword}{" (正则)" if kw.is_regex else ""}',
                    f'关键字列表\n规则: 来自 {source_chat.name}'
                )
                
            finally:
                session.close()
                
        elif command == 'list_replace':
            session = get_session()
            try:
                # 获取当前聊天
                current_chat = await event.get_chat()
                current_chat_db = session.query(Chat).filter(
                    Chat.telegram_chat_id == str(current_chat.id)
                ).first()
                
                if not current_chat_db or not current_chat_db.current_add_id:
                    await event.reply('请先使用 /switch 选择一个源聊天')
                    return
                
                # 查找对应的规则
                source_chat = session.query(Chat).filter(
                    Chat.telegram_chat_id == current_chat_db.current_add_id
                ).first()
                
                rule = session.query(ForwardRule).filter(
                    ForwardRule.source_chat_id == source_chat.id,
                    ForwardRule.target_chat_id == current_chat_db.id
                ).first()
                
                if not rule:
                    await event.reply('转发规则不存在')
                    return
                
                # 获取所有替换规则
                replace_rules = session.query(ReplaceRule).filter(
                    ReplaceRule.rule_id == rule.id
                ).all()
                
                await show_list(
                    event,
                    'replace',
                    replace_rules,
                    lambda i, rr: f'{i}. 匹配: {rr.pattern} -> {"删除" if not rr.content else f"替换为: {rr.content}"}',
                    f'替换规则列表\n规则: 来自 {source_chat.name}'
                )
                
            finally:
                session.close()

        elif command in ['remove_keyword', 'remove_replace']:
            if len(parts) < 2:
                await event.reply(f'用法: /{command} <ID1> [ID2] [ID3] ...\n例如: /{command} 1 2 3')
                return
                
            # 解析要删除的ID列表
            try:
                ids_to_remove = [int(x) for x in parts[1:]]
            except ValueError:
                await event.reply('ID必须是数字')
                return
            
            session = get_session()
            try:
                # 获取当前聊天和规则
                current_chat = await event.get_chat()
                current_chat_db = session.query(Chat).filter(
                    Chat.telegram_chat_id == str(current_chat.id)
                ).first()
                
                if not current_chat_db or not current_chat_db.current_add_id:
                    await event.reply('请先使用 /switch 选择一个源聊天')
                    return
                
                # 查找对应的规则
                source_chat = session.query(Chat).filter(
                    Chat.telegram_chat_id == current_chat_db.current_add_id
                ).first()
                
                rule = session.query(ForwardRule).filter(
                    ForwardRule.source_chat_id == source_chat.id,
                    ForwardRule.target_chat_id == current_chat_db.id
                ).first()
                
                if not rule:
                    await event.reply('转发规则不存在')
                    return
                
                # 获取所有项目并创建ID映射
                if command == 'remove_keyword':
                    items = session.query(Keyword).filter(
                        Keyword.rule_id == rule.id
                    ).order_by(Keyword.id).all()
                    
                    item_type = "关键字"
                    Model = Keyword
                else:  # remove_replace
                    items = session.query(ReplaceRule).filter(
                        ReplaceRule.rule_id == rule.id
                    ).order_by(ReplaceRule.id).all()
                    
                    item_type = "替换规则"
                    Model = ReplaceRule
                
                if not items:
                    await event.reply(f'当前规则没有任何{item_type}')
                    return
                
                # 创建序号到ID的映射
                index_to_id = {i + 1: item.id for i, item in enumerate(items)}
                
                # 检查要删除的序号是否有效
                invalid_ids = [i for i in ids_to_remove if i not in index_to_id]
                if invalid_ids:
                    await event.reply(f'无效的序号: {", ".join(map(str, invalid_ids))}')
                    return
                
                # 执行删除
                actual_ids = [index_to_id[i] for i in ids_to_remove]
                deleted_count = session.query(Model).filter(
                    Model.id.in_(actual_ids)
                ).delete(synchronize_session=False)
                
                session.commit()
                
                # 重新获取列表并显示
                items = session.query(Model).filter(
                    Model.rule_id == rule.id
                ).order_by(Model.id).all()
                
                # 构建格式化函数
                if command == 'remove_keyword':
                    formatter = lambda i, kw: f'{i}. {kw.keyword}{" (正则)" if kw.is_regex else ""}'
                else:
                    formatter = lambda i, rr: f'{i}. 匹配: {rr.pattern} -> {"删除" if not rr.content else f"替换为: {rr.content}"}'
                
                # 显示更新后的列表
                await event.reply(f'已删除 {deleted_count} 个{item_type}')
                if items:  # 如果还有剩余项目，显示更新后的列表
                    await show_list(
                        event,
                        command.split('_')[1],  # 'keyword' 或 'replace'
                        items,
                        formatter,
                        f'{item_type}列表\n规则: 来自 {source_chat.name}'
                    )
                
            except Exception as e:
                session.rollback()
                logger.error(f'删除{item_type}时出错: {str(e)}')
                await event.reply(f'删除{item_type}时出错，请检查日志')
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
                
        elif action == 'page':
            command, page = rule_id.split(':')  # 这里的 rule_id 实际上是 "command:page"
            page = int(page)
            
            session = get_session()
            try:
                # 获取当前聊天和规则
                current_chat = await event.get_chat()
                current_chat_db = session.query(Chat).filter(
                    Chat.telegram_chat_id == str(current_chat.id)
                ).first()
                
                if not current_chat_db or not current_chat_db.current_add_id:
                    await event.answer('请先选择一个源聊天')
                    return
                
                source_chat = session.query(Chat).filter(
                    Chat.telegram_chat_id == current_chat_db.current_add_id
                ).first()
                
                rule = session.query(ForwardRule).filter(
                    ForwardRule.source_chat_id == source_chat.id,
                    ForwardRule.target_chat_id == current_chat_db.id
                ).first()
                
                if command == 'keyword':
                    # 获取关键字列表
                    keywords = session.query(Keyword).filter(
                        Keyword.rule_id == rule.id
                    ).all()
                    
                    await show_list(
                        event,
                        'keyword',
                        keywords,
                        lambda i, kw: f'{i}. {kw.keyword}{" (正则)" if kw.is_regex else ""}',
                        f'关键字列表\n规则: 来自 {source_chat.name}',
                        page
                    )
                    
                elif command == 'replace':
                    # 获取替换规则列表
                    replace_rules = session.query(ReplaceRule).filter(
                        ReplaceRule.rule_id == rule.id
                    ).all()
                    
                    await show_list(
                        event,
                        'replace',
                        replace_rules,
                        lambda i, rr: f'{i}. 匹配: {rr.pattern} -> {"删除" if not rr.content else f"替换为: {rr.content}"}',
                        f'替换规则列表\n规则: 来自 {source_chat.name}',
                        page
                    )
                    
                # 删除原消息
                message = await event.get_message()
                await message.delete()
                
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
            
            # 设置消息格式
            parse_mode = rule.message_mode.value  # 使用枚举的值（字符串）
            logger.info(f'使用消息格式: {parse_mode}')
            
            if event.message.grouped_id:
                # 处理媒体组
                logger.info(f'处理媒体组消息 组ID: {event.message.grouped_id}')
                
                # 等待更长时间让所有媒体消息到达
                await asyncio.sleep(1)  # 增加等待时间
                
                # 收集媒体组的所有消息
                messages = []
                async for message in event.client.iter_messages(
                    event.chat_id,
                    limit=20,  # 增加限制数量
                    min_id=event.message.id - 10,  # 从当前消息往前查找
                    max_id=event.message.id + 10   # 从当前消息往后查找
                ):
                    # 检查是否属于同一个媒体组
                    if message.grouped_id == event.message.grouped_id:
                        messages.append(message)
                        logger.info(f'找到媒体组消息: ID={message.id}, 类型={type(message.media).__name__ if message.media else "无媒体"}')

                # 按照ID排序确保顺序正确
                messages.sort(key=lambda x: x.id)
                logger.info(f'共找到 {len(messages)} 条媒体组消息')
                
                # 创建临时目录存储下载的媒体文件
                with tempfile.TemporaryDirectory() as temp_dir:
                    files = []
                    caption = None
                    
                    for msg in messages:
                        if msg.media:
                            # 下载媒体文件
                            file_path = await msg.download_media(temp_dir)
                            if file_path:  # 确保文件下载成功
                                files.append(file_path)
                                logger.info(f'已下载媒体文件: {file_path}')
                            
                            # 获取第一条消息的文本作为说明
                            if not caption and msg.text:
                                caption = msg.text
                                logger.info(f'使用文本作为说明: {caption}')
                    
                    # 使用 send_file 发送媒体组
                    if files:
                        logger.info(f'准备发送 {len(files)} 个媒体文件')
                        try:
                            await client.send_file(
                                target_chat_id,
                                files,
                                caption=caption,
                                parse_mode=parse_mode,  # 使用字符串值
                                reply_to=None
                            )
                            logger.info(f'[机器人] 媒体组消息已发送到: {target_chat.name} ({target_chat_id})')
                        except Exception as e:
                            logger.error(f'发送媒体组时出错: {str(e)}')
                            # 尝试逐个发送
                            for file in files:
                                try:
                                    await client.send_file(
                                        target_chat_id,
                                        file,
                                        parse_mode=parse_mode  # 使用字符串值
                                    )
                                except Exception as e:
                                    logger.error(f'发送单个媒体文件时出错: {str(e)}')
            else:
                # 处理单条消息
                # 检查是否是纯链接预览消息
                is_pure_link_preview = (
                    event.message.media and 
                    hasattr(event.message.media, 'webpage') and 
                    not any([
                        getattr(event.message.media, 'photo', None),
                        getattr(event.message.media, 'document', None),
                        getattr(event.message.media, 'video', None),
                        getattr(event.message.media, 'audio', None),
                        getattr(event.message.media, 'voice', None)
                    ])
                )
                
                # 检查是否有实际媒体
                has_media = (
                    event.message.media and
                    any([
                        getattr(event.message.media, 'photo', None),
                        getattr(event.message.media, 'document', None),
                        getattr(event.message.media, 'video', None),
                        getattr(event.message.media, 'audio', None),
                        getattr(event.message.media, 'voice', None)
                    ])
                )
                
                if has_media:
                    # 处理媒体消息
                    try:
                        with tempfile.TemporaryDirectory() as temp_dir:
                            file_path = await event.message.download_media(temp_dir)
                            if file_path:
                                await client.send_file(
                                    target_chat_id,
                                    file_path,
                                    caption=message_text,
                                    parse_mode=parse_mode,  # 使用字符串值
                                    link_preview={
                                        PreviewMode.ON: True,
                                        PreviewMode.OFF: False,
                                        PreviewMode.FOLLOW: event.message.media is not None
                                    }[rule.is_preview]
                                )
                                logger.info(f'[机器人] 媒体消息已发送到: {target_chat.name} ({target_chat_id})')
                    except Exception as e:
                        logger.error(f'发送媒体消息时出错: {str(e)}')
                else:
                    # 发送纯文本消息或纯链接预览消息
                    if message_text:
                        # 根据预览模式设置 link_preview
                        link_preview = {
                            PreviewMode.ON: True,
                            PreviewMode.OFF: False,
                            PreviewMode.FOLLOW: event.message.media is not None  # 跟随原消息
                        }[rule.is_preview]
                        
                        await client.send_message(
                            target_chat_id,
                            message_text,
                            parse_mode=parse_mode,  # 使用字符串值
                            link_preview=link_preview
                        )
                        logger.info(
                            f'[机器人] {"带预览的" if link_preview else "无预览的"}文本消息已发送到: '
                            f'{target_chat.name} ({target_chat_id})'
                        )
                
        except Exception as e:
            logger.error(f'发送消息时出错: {str(e)}')
            logger.exception(e) 

async def create_list_buttons(total_pages, current_page, command):
    """创建分页按钮"""
    buttons = []
    row = []
    
    # 上一页按钮
    if current_page > 1:
        row.append(Button.inline(
            '⬅️ 上一页',
            f'page:{command}:{current_page-1}'
        ))
    
    # 页码显示
    row.append(Button.inline(
        f'{current_page}/{total_pages}',
        'noop:0'  # 空操作
    ))
    
    # 下一页按钮
    if current_page < total_pages:
        row.append(Button.inline(
            '下一页 ➡️',
            f'page:{command}:{current_page+1}'
        ))
    
    buttons.append(row)
    return buttons

async def show_list(event, command, items, formatter, title, page=1):
    """显示分页列表"""
    PAGE_SIZE = 50
    total_items = len(items)
    total_pages = (total_items + PAGE_SIZE - 1) // PAGE_SIZE
    
    if not items:
        return await event.reply(f'没有找到任何{title}')
    
    # 获取当前页的项目
    start = (page - 1) * PAGE_SIZE
    end = min(start + PAGE_SIZE, total_items)
    current_items = items[start:end]
    
    # 格式化列表项
    item_list = [formatter(i + start + 1, item) for i, item in enumerate(current_items)]
    
    # 创建分页按钮
    buttons = await create_list_buttons(total_pages, page, command)
    
    # 发送消息
    text = f'{title}:\n{chr(10).join(item_list)}'
    if len(text) > 4096:  # Telegram消息长度限制
        text = text[:4093] + '...'
    
    return await event.reply(text, buttons=buttons) 