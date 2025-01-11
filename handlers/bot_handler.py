from telethon import events, Button
from handlers.models import get_session, Chat, ForwardRule, Keyword, ReplaceRule
import re
import os
import logging
import asyncio
from enums.enums import ForwardMode, PreviewMode, MessageMode
from sqlalchemy.exc import IntegrityError
from telethon.tl.types import ChannelParticipantsAdmins

logger = logging.getLogger(__name__)

# 在文件顶部添加
TEMP_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'temp')
# 确保 temp 目录存在
os.makedirs(TEMP_DIR, exist_ok=True)

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
    buttons.append([Button.inline(
        '❌ 删除',
        f"delete:{rule.id}"
    )])
    
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
        
    if message.text.startswith('/'):
        # 分割命令，处理可能带有机器人用户名的情况
        parts = message.text.split()
        command = parts[0].split('@')[0][1:]  # 移除开头的 '/' 并处理可能的 @username
        
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
                rule_info = await get_current_rule(session, event)
                if not rule_info:
                    return
                    
                rule, source_chat = rule_info
                
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
                rule_info = await get_current_rule(session, event)
                if not rule_info:
                    return
                    
                rule, source_chat = rule_info
                
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
                rule_info = await get_current_rule(session, event)
                if not rule_info:
                    return
                    
                rule, source_chat = rule_info
                
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
                rule_info = await get_current_rule(session, event)
                if not rule_info:
                    return
                    
                rule, source_chat = rule_info
                
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
                rule_info = await get_current_rule(session, event)
                if not rule_info:
                    return
                    
                rule, source_chat = rule_info
                
                # 根据命令类型选择要删除的对象
                if command == 'remove_keyword':
                    items = session.query(Keyword).filter(
                        Keyword.rule_id == rule.id
                    ).all()
                    item_type = '关键字'
                else:  # remove_replace
                    items = session.query(ReplaceRule).filter(
                        ReplaceRule.rule_id == rule.id
                    ).all()
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
                deleted_count = 0
                for id_to_remove in ids_to_remove:
                    if 1 <= id_to_remove <= max_id:
                        item = items[id_to_remove - 1]
                        session.delete(item)
                        deleted_count += 1
                
                session.commit()
                
                await event.reply(f'已删除 {deleted_count} 个{item_type}')
                
                # 重新获取列表并显示
                if command == 'remove_keyword':
                    items = session.query(Keyword).filter(
                        Keyword.rule_id == rule.id
                    ).all()
                    formatter = lambda i, kw: f'{i}. {kw.keyword}{" (正则)" if kw.is_regex else ""}'
                else:  # remove_replace
                    items = session.query(ReplaceRule).filter(
                        ReplaceRule.rule_id == rule.id
                    ).all()
                    formatter = lambda i, rr: f'{i}. 匹配: {rr.pattern} -> {"删除" if not rr.content else f"替换为: {rr.content}"}'
                
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

        elif command == 'clear_all':
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

        elif command == 'start':
            welcome_text = """
👋 欢迎使用 Telegram 消息转发机器人！

📖 查看完整命令列表请使用 /help

"""
            await event.reply(welcome_text)
            return

        elif command == 'help':
            help_text = """
📋 命令使用说明：

🔗 绑定转发
/bind <目标聊天链接> - 绑定一个新的转发规则
例如：/bind https://t.me/channel_name

📝 关键字管理
/add <关键字1> [关键字2] ... - 添加普通关键字到当前规则
/add_regex <正则1> [正则2] ... - 添加正则表达式关键字到当前规则
/add_all <关键字1> [关键字2] ... - 添加普通关键字到所有规则
/add_regex_all <正则1> [正则2] ... - 添加正则表达式关键字到所有规则
/export_keyword - 导出当前规则的关键字到文件
例如：
  /add 新闻 体育    (转发包含"新闻"或"体育"的消息)
  /add_regex ^.*新闻.*$ ^.*体育.*$
  /add_all 新闻 体育    (为所有规则添加关键字)

🔄 替换规则
/replace <匹配模式> <替换内容> - 添加替换规则到当前规则
/replace_all <匹配模式> <替换内容> - 添加替换规则到所有规则
/export_replace - 导出当前规则的替换规则到文件
例如：
  /replace 机密 ***    (将"机密"替换为"***")
  /replace_all 广告    (为所有规则添加删除广告的规则)

🔀 切换规则
/switch - 切换当前操作的转发规则

📊 查看列表
/list_keyword - 查看当前规则的关键字列表
/list_replace - 查看当前规则的替换规则列表

⚙️ 设置管理
/settings - 显示选用的转发规则的设置

🗑 清除数据
/clear_all - 清空所有数据
"""
            await event.reply(help_text)

        elif command == 'export_keyword':
            session = get_session()
            try:
                rule_info = await get_current_rule(session, event)
                if not rule_info:
                    return
                    
                rule, source_chat = rule_info
                
                # 获取所有关键字
                keywords = session.query(Keyword).filter(
                    Keyword.rule_id == rule.id
                ).all()
                
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

        elif command == 'export_replace':
            session = get_session()
            try:
                rule_info = await get_current_rule(session, event)
                if not rule_info:
                    return
                    
                rule, source_chat = rule_info
                
                # 获取所有替换规则
                replace_rules = session.query(ReplaceRule).filter(
                    ReplaceRule.rule_id == rule.id
                ).all()
                
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

        elif command in ['add_all', 'add_regex_all']:
            if len(parts) < 2:
                await event.reply(f'用法: /{command} <关键字1> [关键字2] [关键字3] ...')
                return
                
            keywords = parts[1:]  # 获取所有关键字
            session = get_session()
            try:
                rules = await get_all_rules(session, event)
                if not rules:
                    return
                
                # 为每个规则添加关键字
                success_count = 0
                duplicate_count = 0
                for rule in rules:
                    for keyword in keywords:
                        try:
                            new_keyword = Keyword(
                                rule_id=rule.id,
                                keyword=keyword,
                                is_regex=(command == 'add_regex_all')
                            )
                            session.add(new_keyword)
                            success_count += 1
                        except IntegrityError:
                            session.rollback()
                            duplicate_count += 1
                            continue
                
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

        elif command == 'replace_all':
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
                
                # 为每个规则添加替换规则
                success_count = 0
                duplicate_count = 0
                for rule in rules:
                    try:
                        new_replace_rule = ReplaceRule(
                            rule_id=rule.id,
                            pattern=pattern,
                            content=content
                        )
                        session.add(new_replace_rule)
                        
                        # 确保启用替换模式
                        if not rule.is_replace:
                            rule.is_replace = True
                            
                        success_count += 1
                    except IntegrityError:
                        session.rollback()
                        duplicate_count += 1
                        continue
                
                session.commit()
                
                # 构建回复消息
                action_type = "删除" if not content else "替换"
                result_text = f'已为 {success_count} 个规则添加替换规则:\n'
                if duplicate_count > 0:
                    result_text += f'跳过 {duplicate_count} 个重复的替换规则\n'
                result_text += f'匹配模式: {pattern}\n'
                result_text += f'动作: {action_type}\n'
                if content:
                    result_text += f'替换为: {content}'
                
                await event.reply(result_text)
                
            except Exception as e:
                session.rollback()
                logger.error(f'批量添加替换规则时出错: {str(e)}')
                await event.reply('添加替换规则时出错，请检查日志')
            finally:
                session.close()

        elif command in ['import_keyword', 'import_regex_keyword', 'import_replace']:
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
                    
                    success_count = 0
                    duplicate_count = 0
                    
                    if command in ['import_keyword', 'import_regex_keyword']:
                        # 导入关键字
                        is_regex = (command == 'import_regex_keyword')
                        for keyword in lines:
                            try:
                                new_keyword = Keyword(
                                    rule_id=rule.id,
                                    keyword=keyword,
                                    is_regex=is_regex
                                )
                                session.add(new_keyword)
                                session.flush()
                                success_count += 1
                            except IntegrityError:
                                session.rollback()
                                duplicate_count += 1
                                continue
                    else:
                        # 导入替换规则
                        for line in lines:
                            try:
                                parts = line.split('\t', 1)
                                if len(parts) == 2:
                                    pattern, content = parts
                                else:
                                    pattern = parts[0]
                                    content = ''
                                
                                new_rule = ReplaceRule(
                                    rule_id=rule.id,
                                    pattern=pattern,
                                    content=content
                                )
                                session.add(new_rule)
                                session.flush()
                                success_count += 1
                            except IntegrityError:
                                session.rollback()
                                duplicate_count += 1
                                continue
                    
                    # 如果是替换规则，确保启用替换模式
                    if command == 'import_replace' and success_count > 0:
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
                logger.error(f'导入过程出错: {str(e)}')
                await event.reply('导入过程出错，请检查日志')
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
/bind <目标聊天链接>

例如：
/bind https://t.me/channel_name

注意事项：
1. 目标聊天必须是公开聊天
2. 机器人必须是目标聊天的管理员
3. 每个聊天可以设置多个转发规则
"""
            elif rule_id == 'settings':
                help_text = """
⚙️ 管理设置

使用方法：
/settings - 显示所有转发规则的设置

可配置项：
• 转发模式 (白名单/黑名单)
• 转发方式 (机器人/用户账号)
• 替换模式 (开启/关闭)
• 消息格式 (Markdown/HTML)
• 预览模式 (开启/关闭/跟随原消息)
• 原始链接 (附带/不附带)
"""
            elif rule_id == 'help':
                help_text = """
❓ 完整帮助

请使用 /help 命令查看所有可用命令的详细说明。

包括：
• 绑定转发
• 关键字管理
• 替换规则
• 查看列表
• 设置管理
• 其他功能
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