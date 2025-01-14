from telethon import events, Button
from models.models import get_session, Chat, ForwardRule, Keyword, ReplaceRule
from handlers.message_handler import pre_handle
import re
import os
import logging
import asyncio
import importlib.util
import sys
from enums.enums import ForwardMode, PreviewMode, MessageMode
from sqlalchemy.exc import IntegrityError
from telethon.tl.types import ChannelParticipantsAdmins

logger = logging.getLogger(__name__)

# 在文件顶部添加
TEMP_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'temp')
# 确保 temp 目录存在
os.makedirs(TEMP_DIR, exist_ok=True)

def get_main_module():
    """获取 main 模块"""
    try:
        return sys.modules['__main__']
    except KeyError:
        # 如果找不到 main 模块，尝试手动导入
        spec = importlib.util.spec_from_file_location(
            "main",
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "main.py")
        )
        main = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(main)
        return main

async def get_db_ops():
    """获取 main.py 中的 db_ops 实例"""
    main = get_main_module()
    if main.db_ops is None:
        main.db_ops = await main.init_db_ops()
    return main.db_ops

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
    },
    'is_original_link': {
        'display_name': '原始链接',
        'values': {
            True: '附带',
            False: '不附带'
        },
        'toggle_action': 'toggle_original_link',
        'toggle_func': lambda current: not current
    },
    'is_ufb': {
        'display_name': 'UFB同步',
        'values': {
            True: '开启',
            False: '关闭'
        },
        'toggle_action': 'toggle_ufb',
        'toggle_func': lambda current: not current
    }
}



def get_user_id():
    """获取用户ID，确保环境变量已加载"""
    user_id_str = os.getenv('USER_ID')
    if not user_id_str:
        logger.error('未设置 USER_ID 环境变量')
        raise ValueError('必须在 .env 文件中设置 USER_ID')
    return int(user_id_str)

def get_max_media_size():
    """获取媒体文件大小上限"""
    max_media_size_str = os.getenv('MAX_MEDIA_SIZE')
    if not max_media_size_str:
        logger.error('未设置 MAX_MEDIA_SIZE 环境变量')
        raise ValueError('必须在 .env 文件中设置 MAX_MEDIA_SIZE')
    return float(max_media_size_str) * 1024 * 1024  # 转换为字节，支持小数

def create_buttons(rule):
    """根据配置创建设置按钮"""
    buttons = []
    
    # 始终显示的按钮
    basic_settings = ['mode', 'use_bot']
    
    # 为每个配置字段创建按钮
    for field, config in RULE_SETTINGS.items():
        # 如果是使用用户账号模式，只显示基本按钮
        if not rule.use_bot and field not in basic_settings:
            continue
            
        current_value = getattr(rule, field)
        display_value = config['values'][current_value]
        button_text = f"{config['display_name']}: {display_value}"
        callback_data = f"{config['toggle_action']}:{rule.id}"
        buttons.append([Button.inline(button_text, callback_data)])
    
    # 添加删除按钮
    buttons.append([Button.inline('❌ 删除当前规则', f"delete:{rule.id}")])
    # 添加返回按钮
    buttons.append([Button.inline('👈 返回', 'settings')])
    
    return buttons

def create_settings_text(rule):
    """创建设置信息文本"""
    text = f'管理转发规则\n目标聊天: {rule.target_chat.name}\n'
    return text

async def get_current_rule(session, event):
    """获取当前选中的规则"""
    try:
        # 获取当前聊天
        current_chat = await event.get_chat()
        current_chat_db = session.query(Chat).filter(
            Chat.telegram_chat_id == str(current_chat.id)
        ).first()
        
        if not current_chat_db or not current_chat_db.current_add_id:
            await event.reply('请先使用 /switch 选择一个源聊天')
            return None
        
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
            return None
        
        return rule, source_chat
    except Exception as e:
        logger.error(f'获取当前规则时出错: {str(e)}')
        await event.reply('获取当前规则时出错，请检查日志')
        return None

async def get_all_rules(session, event):
    """获取当前聊天的所有规则"""
    try:
        # 获取当前聊天
        current_chat = await event.get_chat()
        current_chat_db = session.query(Chat).filter(
            Chat.telegram_chat_id == str(current_chat.id)
        ).first()
        
        if not current_chat_db:
            await event.reply('当前聊天没有任何转发规则')
            return None
        
        # 查找所有以当前聊天为目标的规则
        rules = session.query(ForwardRule).filter(
            ForwardRule.target_chat_id == current_chat_db.id
        ).all()
        
        if not rules:
            await event.reply('当前聊天没有任何转发规则')
            return None
            
        return rules
    except Exception as e:
        logger.error(f'获取所有规则时出错: {str(e)}')
        await event.reply('获取规则时出错，请检查日志')
        return None

async def handle_command(client, event):
    """处理机器人命令"""
    
    # 检查是否是频道消息
    if event.is_channel:
        # 获取频道管理员列表
        try:
            admins = await client.get_participants(event.chat_id, filter=ChannelParticipantsAdmins)
            admin_ids = [admin.id for admin in admins]
            user_id = get_user_id()
            if user_id not in admin_ids:
                logger.info(f'非管理员的频道消息，已忽略')
                return
        except Exception as e:
            logger.error(f'获取频道管理员列表失败: {str(e)}')
            return
    else:
        # 普通聊天消息，检查发送者ID
        user_id = event.sender_id
        if user_id != get_user_id():
            logger.info(f'非管理员的消息，已忽略')
            return
                
    logger.info(f'收到管理员命令: {event.message.text}')
    # 处理命令逻辑
    message = event.message
    if not message.text:
        return
            
    if not message.text.startswith('/'):
        return
                
    # 分割命令，处理可能带有机器人用户名的情况
    parts = message.text.split()
    command = parts[0].split('@')[0][1:]  # 移除开头的 '/' 并处理可能的 @username
    
    # 命令处理器字典
    command_handlers = {
        'bind': lambda: handle_bind_command(event, client, parts),
        'settings': lambda: handle_settings_command(event),
        'switch': lambda: handle_switch_command(event),
        'add': lambda: handle_add_command(event, command, parts),
        'add_regex': lambda: handle_add_command(event, command, parts),
        'replace': lambda: handle_replace_command(event, parts),
        'list_keyword': lambda: handle_list_keyword_command(event),
        'list_replace': lambda: handle_list_replace_command(event),
        'remove_keyword': lambda: handle_remove_command(event, command, parts),
        'remove_replace': lambda: handle_remove_command(event, command, parts),
        'clear_all': lambda: handle_clear_all_command(event),
        'start': lambda: handle_start_command(event),
        'help': lambda: handle_help_command(event),
        'export_keyword': lambda: handle_export_keyword_command(event, client),
        'export_replace': lambda: handle_export_replace_command(event, client),
        'add_all': lambda: handle_add_all_command(event, command, parts),
        'add_regex_all': lambda: handle_add_all_command(event, command, parts),
        'replace_all': lambda: handle_replace_all_command(event, parts),
        'import_keyword': lambda: handle_import_command(event, command),
        'import_regex_keyword': lambda: handle_import_command(event, command),
        'import_replace': lambda: handle_import_command(event, command),
        'ufb_bind': lambda: handle_ufb_bind_command(event, command),
        'ufb_unbind': lambda: handle_ufb_unbind_command(event, command),
        'ufb_item_change': lambda: handle_ufb_item_change_command(event, command)
    }
    
    # 执行对应的命令处理器
    handler = command_handlers.get(command)
    if handler:
        await handler()

async def handle_ufb_item_change_command(event, command):
    """处理 ufb_item_change 命令"""
    
    session = get_session()
    try:
        rule_info = await get_current_rule(session, event)
        if not rule_info:
            return
            
        rule, source_chat = rule_info
        
        # 创建4个按钮
        buttons = [
            [
                Button.inline("主页关键字", "ufb_item:main"),
                Button.inline("内容页关键字", "ufb_item:content")
            ],
            [
                Button.inline("主页用户名", "ufb_item:main_username"),
                Button.inline("内容页用户名", "ufb_item:content_username")
            ]
        ]
        
        # 发送带按钮的消息
        await event.reply("请选择要切换的UFB同步配置类型:", buttons=buttons)
        
    except Exception as e:
        session.rollback()
        logger.error(f'切换UFB配置类型时出错: {str(e)}')
        await event.reply('切换UFB配置类型时出错，请检查日志')
    finally:
        session.close()

async def handle_ufb_bind_command(event, command):
    """处理 ufb_bind 命令"""
    session = get_session()
    try:
        rule_info = await get_current_rule(session, event)
        if not rule_info:
            return
            
        rule, source_chat = rule_info
        
        # 从消息中获取域名和类型
        parts = event.message.text.split()
        if len(parts) < 2 or len(parts) > 3:
            await event.reply('用法: /ufb_bind <域名> [类型]\n类型可选: main, content, main_username, content_username\n例如: /ufb_bind example.com main')
            return
            
        domain = parts[1].strip().lower()
        item = 'main'  # 默认值
        
        if len(parts) == 3:
            item = parts[2].strip().lower()
            if item not in ['main', 'content', 'main_username', 'content_username']:
                await event.reply('类型必须是以下之一: main, content, main_username, content_username')
                return
        
        # 更新规则的 ufb_domain 和 ufb_item
        rule.ufb_domain = domain
        rule.ufb_item = item
        session.commit()
        
        await event.reply(f'已绑定 UFB 域名: {domain}\n类型: {item}\n规则: 来自 {source_chat.name}')
        
    except Exception as e:
        session.rollback()
        logger.error(f'绑定 UFB 域名时出错: {str(e)}')
        await event.reply('绑定 UFB 域名时出错，请检查日志')
    finally:
        session.close()

async def handle_ufb_unbind_command(event, command):
    """处理 ufb_unbind 命令"""
    session = get_session()
    try:
        rule_info = await get_current_rule(session, event)
        if not rule_info:
            return
            
        rule, source_chat = rule_info
        
        # 清除规则的 ufb_domain
        old_domain = rule.ufb_domain
        rule.ufb_domain = None
        session.commit()
        
        await event.reply(f'已解绑 UFB 域名: {old_domain or "无"}\n规则: 来自 {source_chat.name}')
        
    except Exception as e:
        session.rollback()
        logger.error(f'解绑 UFB 域名时出错: {str(e)}')
        await event.reply('解绑 UFB 域名时出错，请检查日志')
    finally:
        session.close()
        
async def handle_add_command(event, command, parts):
    """处理 add 和 add_regex 命令"""
    if len(parts) < 2:
        await event.reply(f'用法: /{command} <关键字1> [关键字2] [关键字3] ...')
        return
        
    keywords = parts[1:]  # 获取所有关键字
    session = get_session()
    try:
        rule_info = await get_current_rule(session, event)
        if not rule_info:
            return
            
        rule, source_chat = rule_info
        
        # 使用 db_operations 添加关键字
        db_ops = await get_db_ops()
        success_count, duplicate_count = await db_ops.add_keywords(
            session,
            rule.id,
            keywords,
            is_regex=(command == 'add_regex')
        )
        
        session.commit()
        
        # 构建回复消息
        keyword_type = "正则" if command == "add_regex" else "关键字"
        keywords_text = '\n'.join(f'- {k}' for k in keywords)
        result_text = f'已添加 {success_count} 个{keyword_type}'
        if duplicate_count > 0:
            result_text += f'\n跳过重复: {duplicate_count} 个'
        result_text += f'\n关键字列表:\n{keywords_text}\n'
        result_text += f'当前规则: 来自 {source_chat.name}'
        
        await event.reply(result_text)
        
    except Exception as e:
        session.rollback()
        logger.error(f'添加关键字时出错: {str(e)}')
        await event.reply('添加关键字时出错，请检查日志')
    finally:
        session.close()

async def handle_callback(event):
    """处理按钮回调"""
    try:
        data = event.data.decode()
        
        # 特殊处理 'settings' 动作，因为它不需要 rule_id
        if data == 'settings':
            action = 'settings'
            rule_id = None
        else:
            # 其他动作需要分割获取 rule_id
            action, rule_id_str = data.split(':')
            # 对于 ufb_item action，直接使用字符串值
            if action == 'ufb_item':
                rule_id = rule_id_str
            else:
                # 其他 action 需要转换为整数
                rule_id = int(rule_id_str)
        
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
                
                # 如果已经选中了这个聊天，就不做任何操作
                if current_chat_db.current_add_id == rule_id:
                    await event.answer('已经选中该聊天')
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
                
                try:
                    await message.edit('请选择要管理的转发规则:', buttons=buttons)
                except Exception as e:
                    if 'message was not modified' not in str(e).lower():
                        raise  # 如果是其他错误就继续抛出
                
                source_chat = session.query(Chat).filter(
                    Chat.telegram_chat_id == rule_id
                ).first()
                await event.answer(f'已切换到: {source_chat.name if source_chat else "未知聊天"}')
            finally:
                session.close()
        elif action == 'settings':
            session = get_session()
            try:
                # 获取当前聊天
                current_chat = await event.get_chat()
                current_chat_db = session.query(Chat).filter(
                    Chat.telegram_chat_id == str(current_chat.id)
                ).first()
                
                if not current_chat_db:
                    await event.answer('当前聊天没有任何转发规则')
                    return
                
                rules = session.query(ForwardRule).filter(
                    ForwardRule.target_chat_id == current_chat_db.id
                ).all()
                
                if not rules:
                    await event.answer('当前聊天没有任何转发规则')
                    return
                
                # 创建规则选择按钮
                buttons = []
                for rule in rules:
                    source_chat = rule.source_chat
                    button_text = f'来自: {source_chat.name}'
                    callback_data = f"rule_settings:{rule.id}"
                    buttons.append([Button.inline(button_text, callback_data)])
                
                await message.edit('请选择要管理的转发规则:', buttons=buttons)
            finally:
                session.close()
        elif action == 'ufb_item':
            session = get_session()
            try:
                # 获取当前聊天
                current_chat = await event.get_chat()
                current_chat_db = session.query(Chat).filter(
                    Chat.telegram_chat_id == str(current_chat.id)
                ).first()
                
                if not current_chat_db or not current_chat_db.current_add_id:
                    await event.answer('请先选择一个源聊天')
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
                    await event.answer('转发规则不存在')
                    return
                
                # 更新 ufb_item
                rule.ufb_item = rule_id  # rule_id 是类型字符串
                session.commit()
                
                # 更新消息
                message = await event.get_message()
                await message.edit(f"已将UFB同步配置类型切换为: {rule_id}")
                await event.answer(f'已切换到: {rule_id}')
                
            except Exception as e:
                session.rollback()
                logger.error(f'更新UFB配置类型时出错: {str(e)}')
                await event.answer('更新配置时出错，请检查日志')
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
                        
                        # 如果切换了转发方式，立即更新按钮
                        if field_name == 'use_bot':
                            await message.edit(
                                create_settings_text(rule),
                                buttons=create_buttons(rule)
                            )
                            await event.answer(f'已切换到{"机器人" if new_value else "用户账号"}模式')
                            break
                        
                        break
                
                session.commit()
                
                # 如果不是切换转发方式，使用原来的更新逻辑
                if action != 'toggle_bot':
                    await message.edit(
                        create_settings_text(rule),
                        buttons=create_buttons(rule)
                    )
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
                
        elif action == 'help':
            if rule_id == 'bind':
                help_text = """
🔗 绑定新规则

使用方法：
/bind <目标聊天链接或名称>

例如：
/bind https://t.me/channel_name
/bind "频道 名称"

注意事项：
1. 可以使用完整链接或群组/频道名称
2. 如果名称中包含空格，需要用双引号包起来
3. 使用名称时，会匹配第一个包含该名称的群组/频道
4. 机器人必须是目标聊天的管理员
5. 每个聊天可以设置多个转发规则
"""
            elif rule_id == 'settings':
                help_text = """
⚙️ 管理设置

使用方法：
/settings - 显示所有转发规则的设置

"""
            elif rule_id == 'help':
                help_text = """
❓ 完整帮助

请使用 /help 命令查看所有可用命令的详细说明。
"""
            
            # 添加返回按钮
            buttons = [[Button.inline('👈 返回', 'start')]]
            await event.edit(help_text, buttons=buttons)
            
        elif action == 'start':
            # 返回开始界面
            await handle_command(event.client, event)

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

def get_media_size(media):
    """获取媒体文件大小"""
    if not media:
        return 0
        
    try:
        # 对于所有类型的媒体，先尝试获取 document
        if hasattr(media, 'document') and media.document:
            return media.document.size
            
        # 对于照片，获取最大尺寸
        if hasattr(media, 'photo') and media.photo:
            # 获取最大尺寸的照片
            largest_photo = max(media.photo.sizes, key=lambda x: x.size if hasattr(x, 'size') else 0)
            return largest_photo.size if hasattr(largest_photo, 'size') else 0
            
        # 如果是其他类型，尝试直接获取 size 属性
        if hasattr(media, 'size'):
            return media.size
            
    except Exception as e:
        logger.error(f'获取媒体大小时出错: {str(e)}')
    
    return 0

async def process_forward_rule(client, event, chat_id, rule):
    """处理转发规则（机器人模式）"""
    should_forward = False
    message_text = event.message.text or ''
    MAX_MEDIA_SIZE = get_max_media_size()
    check_message_text = pre_handle(message_text)
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
            
            # 设置消息格式
            parse_mode = rule.message_mode.value  # 使用枚举的值（字符串）
            logger.info(f'使用消息格式: {parse_mode}')
            
            # 如果启用了原始链接，生成链接
            original_link = ''
            if rule.is_original_link:
                original_link = f"\n\n原始消息: https://t.me/c/{str(event.chat_id)[4:]}/{event.message.id}"
            
            if event.message.grouped_id:
                # 处理媒体组
                logger.info(f'处理媒体组消息 组ID: {event.message.grouped_id}')
                
                # 等待更长时间让所有媒体消息到达
                await asyncio.sleep(1)
                
                # 收集媒体组的所有消息
                messages = []
                skipped_media = []  # 记录被跳过的媒体消息
                caption = None  # 保存第一条消息的文本
                
                async for message in event.client.iter_messages(
                    event.chat_id,
                    limit=20,
                    min_id=event.message.id - 10,
                    max_id=event.message.id + 10
                ):
                    if message.grouped_id == event.message.grouped_id:
                        # 保存第一条消息的文本
                        if not caption and message.text:
                            caption = message.text
                            logger.info(f'获取到媒体组文本: {caption}')
                        
                        # 检查媒体大小
                        if message.media:
                            file_size = get_media_size(message.media)
                            if MAX_MEDIA_SIZE and file_size > MAX_MEDIA_SIZE:
                                skipped_media.append((message, file_size))
                                continue
                        messages.append(message)
                        logger.info(f'找到媒体组消息: ID={message.id}, 类型={type(message.media).__name__ if message.media else "无媒体"}')
                
                logger.info(f'共找到 {len(messages)} 条媒体组消息，{len(skipped_media)} 条超限')
                
                # 如果所有媒体都超限了，但有文本，就发送文本和提示
                if not messages and caption:
                    # 构建提示信息
                    skipped_info = "\n".join(f"- {size/1024/1024:.1f}MB" for _, size in skipped_media)
                    original_link = f"https://t.me/c/{str(event.chat_id)[4:]}/{event.message.id}"
                    text_to_send = f"{caption}\n\n⚠️ {len(skipped_media)} 个媒体文件超过大小限制 ({MAX_MEDIA_SIZE/1024/1024:.1f}MB):\n{skipped_info}\n原始消息: {original_link}"
                    
                    await client.send_message(
                        target_chat_id,
                        text_to_send,
                        parse_mode=parse_mode,
                        link_preview=True
                    )
                    logger.info(f'[机器人] 媒体组所有文件超限，已发送文本和提示')
                    return
                
                # 如果有可以发送的媒体，作为一个组发送
                try:
                    files = []
                    for message in messages:
                        if message.media:
                            file_path = await message.download_media(TEMP_DIR)
                            if file_path:
                                files.append(file_path)
                    
                    if files:
                        try:
                            # 添加原始链接
                            caption_text = caption + original_link if caption else original_link
                            
                            # 作为一个组发送所有文件
                            await client.send_file(
                                target_chat_id,
                                files,
                                caption=caption_text,
                                parse_mode=parse_mode,
                                link_preview={
                                    PreviewMode.ON: True,
                                    PreviewMode.OFF: False,
                                    PreviewMode.FOLLOW: event.message.media is not None
                                }[rule.is_preview]
                            )
                            logger.info(f'[机器人] 媒体组消息已发送到: {target_chat.name} ({target_chat_id})')
                        finally:
                            # 删除临时文件
                            for file_path in files:
                                try:
                                    os.remove(file_path)
                                except Exception as e:
                                    logger.error(f'删除临时文件失败: {str(e)}')
                except Exception as e:
                    logger.error(f'发送媒体组消息时出错: {str(e)}')
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
                    # 先检查媒体大小
                    file_size = get_media_size(event.message.media)
                    logger.info(f'媒体文件大小: {file_size/1024/1024:.2f}MB')
                    logger.info(f'媒体文件大小上限: {MAX_MEDIA_SIZE}')
                    logger.info(f'媒体文件大小: {file_size}')
                    
                    if MAX_MEDIA_SIZE and file_size > MAX_MEDIA_SIZE:
                        logger.info(f'媒体文件超过大小限制 ({MAX_MEDIA_SIZE/1024/1024:.2f}MB)')
                        # 如果超过大小限制，只发送文本和提示
                        original_link = f"https://t.me/c/{str(event.chat_id)[4:]}/{event.message.id}"
                        text_to_send = message_text or ''
                        text_to_send += f"\n\n⚠️ 媒体文件 ({file_size/1024/1024:.1f}MB) 超过大小限制 ({MAX_MEDIA_SIZE/1024/1024:.1f}MB){original_link}"
                        
                        await client.send_message(
                            target_chat_id,
                            text_to_send,
                            parse_mode=parse_mode,
                            link_preview=True
                        )
                        logger.info(f'[机器人] 媒体文件超过大小限制，仅转发文本')
                        return  # 重要：立即返回，不继续处理
                    
                    # 如果没有超过大小限制，继续处理...
                    try:
                        file_path = await event.message.download_media(TEMP_DIR)
                        if file_path:
                            try:
                                await client.send_file(
                                    target_chat_id,
                                    file_path,
                                    caption=(message_text + original_link) if message_text else original_link,
                                    parse_mode=parse_mode,
                                    link_preview={
                                        PreviewMode.ON: True,
                                        PreviewMode.OFF: False,
                                        PreviewMode.FOLLOW: event.message.media is not None
                                    }[rule.is_preview]
                                )
                                logger.info(f'[机器人] 媒体消息已发送到: {target_chat.name} ({target_chat_id})')
                            finally:
                                # 删除临时文件
                                try:
                                    os.remove(file_path)
                                except Exception as e:
                                    logger.error(f'删除临时文件失败: {str(e)}')
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
                            message_text + original_link,  # 添加原始链接
                            parse_mode=parse_mode,
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

async def handle_replace_command(event, parts):
    """处理 replace 命令"""
    if len(parts) < 2:
        await event.reply('用法: /replace <匹配规则> [替换内容]\n例如:\n/replace 广告  # 删除匹配内容\n/replace 广告 [已替换]\n/replace .* 完全替换整个文本')
        return
        
    pattern = parts[1]
    # 如果没有提供替换内容，默认替换为空字符串
    content = ' '.join(parts[2:]) if len(parts) > 2 else ''
    
    session = get_session()
    try:
        rule_info = await get_current_rule(session, event)
        if not rule_info:
            return
            
        rule, source_chat = rule_info
        
        # 使用 add_replace_rules 添加替换规则
        db_ops = await get_db_ops()
        # 分别传递 patterns 和 contents 参数
        success_count, duplicate_count = await db_ops.add_replace_rules(
            session,
            rule.id,
            [pattern],  # patterns 参数
            [content]   # contents 参数
        )
        
        # 确保启用替换模式
        if success_count > 0 and not rule.is_replace:
            rule.is_replace = True
            
        session.commit()
        
        # 检查是否是全文替换
        rule_type = "全文替换" if pattern == ".*" else "正则替换"
        action_type = "删除" if not content else "替换"
        
        # 构建回复消息
        result_text = f'已添加{rule_type}规则:\n'
        if success_count > 0:
            result_text += f'匹配: {pattern}\n'
            result_text += f'动作: {action_type}\n'
            result_text += f'{"替换为: " + content if content else "删除匹配内容"}\n'
        if duplicate_count > 0:
            result_text += f'跳过重复规则: {duplicate_count} 个\n'
        result_text += f'当前规则: 来自 {source_chat.name}'
        
        await event.reply(result_text)
        
    except Exception as e:
        session.rollback()
        logger.error(f'添加替换规则时出错: {str(e)}')
        await event.reply('添加替换规则时出错，请检查日志')
    finally:
        session.close()

async def handle_list_keyword_command(event):
    """处理 list_keyword 命令"""
    session = get_session()
    try:
        rule_info = await get_current_rule(session, event)
        if not rule_info:
            return
            
        rule, source_chat = rule_info
        
        # 使用 get_keywords 获取所有关键字
        db_ops = await get_db_ops()
        keywords = await db_ops.get_keywords(session, rule.id)
        
        await show_list(
            event,
            'keyword',
            keywords,
            lambda i, kw: f'{i}. {kw.keyword}{" (正则)" if kw.is_regex else ""}',
            f'关键字列表\n规则: 来自 {source_chat.name}'
        )
        
    finally:
        session.close()

async def handle_list_replace_command(event):
    """处理 list_replace 命令"""
    session = get_session()
    try:
        rule_info = await get_current_rule(session, event)
        if not rule_info:
            return
            
        rule, source_chat = rule_info
        
        # 使用 get_replace_rules 获取所有替换规则
        db_ops = await get_db_ops()
        replace_rules = await db_ops.get_replace_rules(session, rule.id)
        
        await show_list(
            event,
            'replace',
            replace_rules,
            lambda i, rr: f'{i}. 匹配: {rr.pattern} -> {"删除" if not rr.content else f"替换为: {rr.content}"}',
            f'替换规则列表\n规则: 来自 {source_chat.name}'
        )
        
    finally:
        session.close()

async def handle_switch_command(event):
    """处理 switch 命令"""
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

async def handle_settings_command(event):
    """处理 settings 命令"""
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

async def handle_bind_command(event, client, parts):
    """处理 bind 命令"""
    # 重新解析命令，支持带引号的名称
    message_text = event.message.text
    if len(message_text.split(None, 1)) != 2:
        await event.reply('用法: /bind <目标聊天链接或名称>\n例如:\n/bind https://t.me/channel_name\n/bind "频道 名称"')
        return
    
    # 分离命令和参数
    _, target = message_text.split(None, 1)
    target = target.strip()
    
    # 检查是否是带引号的名称
    if target.startswith('"') and target.endswith('"'):
        target = target[1:-1]  # 移除引号
        is_link = False
    else:
        is_link = target.startswith(('https://', 't.me/'))
    
    source_chat = await event.get_chat()
    
    try:
        # 获取 main 模块中的用户客户端
        main = get_main_module()
        user_client = main.user_client
        
        # 使用用户客户端获取目标聊天的实体信息
        try:
            if is_link:
                # 如果是链接，直接获取实体
                target_chat = await user_client.get_entity(target)
            else:
                # 如果是名称，获取对话列表并查找匹配的第一个
                async for dialog in user_client.iter_dialogs():
                    if dialog.name and target.lower() in dialog.name.lower():
                        target_chat = dialog.entity
                        break
                else:
                    await event.reply('未找到匹配的群组/频道，请确保名称正确且账号已加入该群组/频道')
                    return
        except ValueError:
            await event.reply('无法获取目标聊天信息，请确保链接/名称正确且账号已加入该群组/频道')
            return
        except Exception as e:
            logger.error(f'获取目标聊天信息时出错: {str(e)}')
            await event.reply('获取目标聊天信息时出错，请检查日志')
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
                target_chat_id=target_chat_db.id
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

async def handle_remove_command(event, command, parts):
    """处理 remove_keyword 和 remove_replace 命令"""
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
        rule_info = await get_current_rule(session, event)
        if not rule_info:
            return
            
        rule, source_chat = rule_info
        
        db_ops = await get_db_ops()
        # 根据命令类型选择要删除的对象
        if command == 'remove_keyword':
            # 获取当前所有关键字
            items = await db_ops.get_keywords(session, rule.id)
            item_type = '关键字'
        else:  # remove_replace
            # 获取当前所有替换规则
            items = await db_ops.get_replace_rules(session, rule.id)
            item_type = '替换规则'
        
        # 检查ID是否有效
        if not items:
            await event.reply(f'当前规则没有任何{item_type}')
            return
        
        max_id = len(items)
        invalid_ids = [id for id in ids_to_remove if id < 1 or id > max_id]
        if invalid_ids:
            await event.reply(f'无效的ID: {", ".join(map(str, invalid_ids))}')
            return
        
        # 删除选中的项目
        if command == 'remove_keyword':
            await db_ops.delete_keywords(session, rule.id, ids_to_remove)
            # 重新获取更新后的列表
            remaining_items = await db_ops.get_keywords(session, rule.id)
        else:  # remove_replace
            await db_ops.delete_replace_rules(session, rule.id, ids_to_remove)
            # 重新获取更新后的列表
            remaining_items = await db_ops.get_replace_rules(session, rule.id)
        
        session.commit()
        
        await event.reply(f'已删除 {len(ids_to_remove)} 个{item_type}')
        
        # 显示更新后的列表
        if remaining_items:
            if command == 'remove_keyword':
                formatter = lambda i, kw: f'{i}. {kw.keyword}{" (正则)" if kw.is_regex else ""}'
            else:  # remove_replace
                formatter = lambda i, rr: f'{i}. 匹配: {rr.pattern} -> {"删除" if not rr.content else f"替换为: {rr.content}"}'
            
            await show_list(
                event,
                command.split('_')[1],  # 'keyword' 或 'replace'
                remaining_items,
                formatter,
                f'{item_type}列表\n规则: 来自 {source_chat.name}'
            )
        
    except Exception as e:
        session.rollback()
        logger.error(f'删除{item_type}时出错: {str(e)}')
        await event.reply(f'删除{item_type}时出错，请检查日志')
    finally:
        session.close()

async def handle_clear_all_command(event):
    """处理 clear_all 命令"""
    session = get_session()
    try:
        # 删除所有替换规则
        replace_count = session.query(ReplaceRule).delete(synchronize_session=False)
        
        # 删除所有关键字
        keyword_count = session.query(Keyword).delete(synchronize_session=False)
        
        # 删除所有转发规则
        rule_count = session.query(ForwardRule).delete(synchronize_session=False)
        
        # 删除所有聊天
        chat_count = session.query(Chat).delete(synchronize_session=False)
        
        session.commit()
        
        await event.reply(
            '已清空所有数据:\n'
            f'- {chat_count} 个聊天\n'
            f'- {rule_count} 条转发规则\n'
            f'- {keyword_count} 个关键字\n'
            f'- {replace_count} 条替换规则'
        )
        
    except Exception as e:
        session.rollback()
        logger.error(f'清空数据时出错: {str(e)}')
        await event.reply('清空数据时出错，请检查日志')
    finally:
        session.close()

async def handle_start_command(event):
    """处理 start 命令"""
    welcome_text = """
👋 欢迎使用 Telegram 消息转发机器人！

📖 查看完整命令列表请使用 /help

"""
    await event.reply(welcome_text)

async def handle_help_command(event):
    """处理 help 命令"""
    help_text = """
绑定转发 
/bind <目标聊天链接或名称> - 名称用引号包裹

关键字管理
/add <关键字1> [关键字2] ... - 添加普通关键字到当前规则
/add_regex <正则1> [正则2] ... - 添加正则表达式关键字到当前规则
/add_all <关键字1> [关键字2] ... - 添加普通关键字到所有规则
/add_regex_all <正则1> [正则2] ... - 添加正则表达式关键字到所有规则
/import_keyword <同时发送文件> - 指令和文件一起发送，一行一个关键字
/import_regex_keyword <同时发送文件> - 指令和文件一起发送，一行一个正则表达式
/export_keyword - 导出当前规则的关键字到文件

替换规则
/replace <匹配模式> <替换内容/替换表达式> - 添加替换规则到当前规则
/replace_all <匹配模式> <替换内容/替换表达式> - 添加替换规则到所有规则
/import_replace <同时发送文件> - 指令和文件一起发送，一行一个替换规则
/export_replace - 导出当前规则的替换规则到文件
注意：不填替换内容则删除匹配内容

切换规则
/switch - 切换当前操作的转发规则

查看列表
/list_keyword - 查看当前规则的关键字列表
/list_replace - 查看当前规则的替换规则列表

设置管理
/settings - 显示选用的转发规则的设置

UFB
/ufb_bind <域名> - 绑定指定的域名
/ufb_unbind - 解除域名绑定
/ufb_item_change - 指定绑定域名下的项目

清除数据
/clear_all - 清空所有数据
"""
    await event.reply(help_text) 

async def handle_export_keyword_command(event, client):
    """处理 export_keyword 命令"""
    session = get_session()
    try:
        rule_info = await get_current_rule(session, event)
        if not rule_info:
            return
            
        rule, source_chat = rule_info
        
        # 获取所有关键字
        db_ops = await get_db_ops()
        keywords = await db_ops.get_keywords(session, rule.id)
        
        # 分离普通关键字和正则关键字
        normal_keywords = [kw.keyword for kw in keywords if not kw.is_regex]
        regex_keywords = [kw.keyword for kw in keywords if kw.is_regex]
        
        # 创建并写入文件
        normal_file = os.path.join(TEMP_DIR, 'keywords.txt')
        regex_file = os.path.join(TEMP_DIR, 'regex_keywords.txt')
        
        with open(normal_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(normal_keywords))
        
        with open(regex_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(regex_keywords))
        
        try:
            # 发送文件
            await client.send_file(
                event.chat_id,
                [normal_file, regex_file],
                caption=f'已导出关键字列表\n规则: 来自 {source_chat.name}'
            )
        finally:
            # 删除临时文件
            os.remove(normal_file)
            os.remove(regex_file)
        
    except Exception as e:
        logger.error(f'导出关键字时出错: {str(e)}')
        await event.reply('导出关键字时出错，请检查日志')
    finally:
        session.close()

async def handle_export_replace_command(event, client):
    """处理 export_replace 命令"""
    session = get_session()
    try:
        rule_info = await get_current_rule(session, event)
        if not rule_info:
            return
            
        rule, source_chat = rule_info
        
        # 获取所有替换规则
        db_ops = await get_db_ops()
        replace_rules = await db_ops.get_replace_rules(session, rule.id)
        
        # 创建并写入文件
        replace_file = os.path.join(TEMP_DIR, 'replace_rules.txt')
        
        with open(replace_file, 'w', encoding='utf-8') as f:
            for rule in replace_rules:
                line = f"{rule.pattern}\t{rule.content if rule.content else ''}"
                f.write(line + '\n')
        
        try:
            # 发送文件
            await client.send_file(
                event.chat_id,
                replace_file,
                caption=f'已导出替换规则列表\n规则: 来自 {source_chat.name}'
            )
        finally:
            # 删除临时文件
            os.remove(replace_file)
        
    except Exception as e:
        logger.error(f'导出替换规则时出错: {str(e)}')
        await event.reply('导出替换规则时出错，请检查日志')
    finally:
        session.close() 

async def handle_add_all_command(event, command, parts):
    """处理 add_all 和 add_regex_all 命令"""
    if len(parts) < 2:
        await event.reply(f'用法: /{command} <关键字1> [关键字2] [关键字3] ...')
        return
        
    keywords = parts[1:]  # 获取所有关键字
    session = get_session()
    try:
        rules = await get_all_rules(session, event)
        if not rules:
            return
        
        db_ops = await get_db_ops()
        # 为每个规则添加关键字
        success_count = 0
        duplicate_count = 0
        for rule in rules:
            # 使用 add_keywords 添加关键字
            s_count, d_count = await db_ops.add_keywords(
                session,
                rule.id,
                keywords,
                is_regex=(command == 'add_regex_all')
            )
            success_count += s_count
            duplicate_count += d_count
        
        session.commit()
        
        # 构建回复消息
        keyword_type = "正则表达式" if command == "add_regex_all" else "关键字"
        keywords_text = '\n'.join(f'- {k}' for k in keywords)
        result_text = f'已添加 {success_count} 个{keyword_type}\n'
        if duplicate_count > 0:
            result_text += f'跳过重复: {duplicate_count} 个'
        result_text += f'关键字列表:\n{keywords_text}'
        
        await event.reply(result_text)
        
    except Exception as e:
        session.rollback()
        logger.error(f'批量添加关键字时出错: {str(e)}')
        await event.reply('添加关键字时出错，请检查日志')
    finally:
        session.close() 

async def handle_replace_all_command(event, parts):
    """处理 replace_all 命令"""
    if len(parts) < 2:
        await event.reply('用法: /replace_all <匹配规则> [替换内容]\n例如:\n/replace_all 广告  # 删除匹配内容\n/replace_all 广告 [已替换]')
        return
        
    pattern = parts[1]
    content = ' '.join(parts[2:]) if len(parts) > 2 else ''
    
    session = get_session()
    try:
        rules = await get_all_rules(session, event)
        if not rules:
            return
        
        db_ops = await get_db_ops()
        # 为每个规则添加替换规则
        total_success = 0
        total_duplicate = 0
        
        for rule in rules:
            # 使用 add_replace_rules 添加替换规则
            success_count, duplicate_count = await db_ops.add_replace_rules(
                session,
                rule.id,
                [(pattern, content)]  # 传入一个元组列表，每个元组包含 pattern 和 content
            )
            
            # 累计成功和重复的数量
            total_success += success_count
            total_duplicate += duplicate_count
            
            # 确保启用替换模式
            if success_count > 0 and not rule.is_replace:
                rule.is_replace = True
        
        session.commit()
        
        # 构建回复消息
        action_type = "删除" if not content else "替换"
        result_text = f'已为 {len(rules)} 个规则添加替换规则:\n'
        if total_success > 0:
            result_text += f'成功添加: {total_success} 个\n'
            result_text += f'匹配模式: {pattern}\n'
            result_text += f'动作: {action_type}\n'
            if content:
                result_text += f'替换为: {content}\n'
        if total_duplicate > 0:
            result_text += f'跳过重复规则: {total_duplicate} 个'
        
        await event.reply(result_text)
        
    except Exception as e:
        session.rollback()
        logger.error(f'批量添加替换规则时出错: {str(e)}')
        await event.reply('添加替换规则时出错，请检查日志')
    finally:
        session.close() 

async def handle_import_command(event, command):
    """处理导入命令（import_keyword, import_regex_keyword, import_replace）"""
    session = get_session()
    try:
        rule_info = await get_current_rule(session, event)
        if not rule_info:
            return
            
        rule, source_chat = rule_info
        
        # 检查是否有附带文件
        if not event.message.file:
            if command == 'import_keyword':
                await event.reply('请在命令中附带包含关键字的文本文件（每行一个关键字）')
            elif command == 'import_regex_keyword':
                await event.reply('请在命令中附带包含正则表达式的文本文件（每行一个正则表达式）')
            else:  # import_replace
                await event.reply('请在命令中附带包含替换规则的文本文件（每行一个规则，使用制表符分隔匹配模式和替换内容）')
            return
        
        # 下载文件
        file_path = os.path.join(TEMP_DIR, 'import_temp.txt')
        await event.message.download_media(file_path)
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]
            
            if command in ['import_keyword', 'import_regex_keyword']:
                # 导入关键字
                db_ops = await get_db_ops()
                success_count, duplicate_count = await db_ops.add_keywords(
                    session,
                    rule.id,
                    lines,
                    is_regex=(command == 'import_regex_keyword')
                )
            else:
                # 导入替换规则
                replace_rules = []
                for line in lines:
                    parts = line.split('\t', 1)
                    if len(parts) == 2:
                        pattern, content = parts
                    else:
                        pattern = parts[0]
                        content = ''
                    replace_rules.append((pattern, content))
                
                db_ops = await get_db_ops()
                success_count, duplicate_count = await db_ops.add_replace_rules(
                    session,
                    rule.id,
                    replace_rules
                )
                
                # 如果成功导入了替换规则，确保启用替换模式
                if success_count > 0 and not rule.is_replace:
                    rule.is_replace = True
            
            session.commit()
            
            # 构建回复消息
            rule_type = {
                'import_keyword': '关键字',
                'import_regex_keyword': '正则表达式',
                'import_replace': '替换规则'
            }[command]
            
            result_text = f'导入完成\n成功导入: {success_count} 个{rule_type}\n'
            if duplicate_count > 0:
                result_text += f'跳过重复: {duplicate_count} 个'
            
            await event.reply(result_text)
            
        finally:
            # 清理临时文件
            try:
                os.remove(file_path)
            except:
                pass
                
    except Exception as e:
        session.rollback()
        logger.error(f'导入过程出错: {str(e)}')
        await event.reply('导入过程出错，请检查日志')
    finally:
        session.close() 