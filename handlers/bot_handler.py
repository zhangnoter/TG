from telethon import events, Button
from models.models import get_session, Chat, ForwardRule, Keyword, ReplaceRule
from handlers.message_handler import pre_handle, ai_handle
import re
import os
import logging
import asyncio
import importlib.util
import sys
from enums.enums import ForwardMode, PreviewMode, MessageMode
from sqlalchemy.exc import IntegrityError
from telethon.tl.types import ChannelParticipantsAdmins
import traceback
from dotenv import load_dotenv
import yaml
import pytz
import tempfile


logger = logging.getLogger(__name__)

TEMP_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'temp')
# 确保 temp 目录存在
os.makedirs(TEMP_DIR, exist_ok=True)

load_dotenv()


MODELS_PER_PAGE = int(os.getenv('AI_MODELS_PER_PAGE', 10))
KEYWORDS_PER_PAGE = int(os.getenv('KEYWORDS_PER_PAGE', 10))


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


def load_ai_models():
    """加载AI模型列表"""
    try:
        # 使用正确的路径
        models_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'ai_models.txt')
        with open(models_path, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logger.warning("ai_models.txt 不存在，使用默认模型列表")
        return ['gpt-3.5-turbo', 'gpt-4', 'gemini-2.0-flash']

AI_MODELS = load_ai_models()

# 添加模型选择按钮创建函数
def create_model_buttons(rule_id, page=0):
    """创建模型选择按钮，支持分页
    
    Args:
        rule_id: 规则ID
        page: 当前页码（从0开始）
    """
    buttons = []
    total_models = len(AI_MODELS)
    total_pages = (total_models + MODELS_PER_PAGE - 1) // MODELS_PER_PAGE
    
    # 计算当前页的模型范围
    start_idx = page * MODELS_PER_PAGE
    end_idx = min(start_idx + MODELS_PER_PAGE, total_models)
    
    # 添加模型按钮
    for model in AI_MODELS[start_idx:end_idx]:
        buttons.append([Button.inline(f"{model}", f"select_model:{rule_id}:{model}")])
    
    # 添加导航按钮
    nav_buttons = []
    if page > 0:  # 不是第一页，显示"上一页"
        nav_buttons.append(Button.inline("⬅️ 上一页", f"model_page:{rule_id}:{page-1}"))
    # 添加页码显示在中间
    nav_buttons.append(Button.inline(f"{page + 1}/{total_pages}", f"noop:{rule_id}"))
    if page < total_pages - 1:  # 不是最后一页，显示"下一页"
        nav_buttons.append(Button.inline("下一页 ➡️", f"model_page:{rule_id}:{page+1}"))
    if nav_buttons:
        buttons.append(nav_buttons)
    
    # 添加返回按钮
    buttons.append([Button.inline("返回", f"rule_settings:{rule_id}")])
    
    return buttons


# 加载时间和时区列表
def load_summary_times():
    """加载总结时间列表"""
    try:
        times_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'summary_times.txt')
        with open(times_path, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logger.warning("summary_times.txt 不存在，使用默认时间")
        return ["00:00"]

SUMMARY_TIMES = load_summary_times()
TIMES_PER_PAGE = int(os.getenv('TIMES_PER_PAGE', 10))

def create_summary_time_buttons(rule_id, page=0):
    """创建时间选择按钮"""
    buttons = []
    total_times = len(SUMMARY_TIMES)
    start_idx = page * TIMES_PER_PAGE
    end_idx = min(start_idx + TIMES_PER_PAGE, total_times)
    
    # 添加时间按钮
    for time in SUMMARY_TIMES[start_idx:end_idx]:
        buttons.append([Button.inline(
            time,
            f"select_time:{rule_id}:{time}"
        )])
    
    # 添加导航按钮
    nav_buttons = []
    if page > 0:
        nav_buttons.append(Button.inline(
            "⬅️ 上一页",
            f"time_page:{rule_id}:{page-1}"
        ))
    
    nav_buttons.append(Button.inline(
        f"{page + 1}/{(total_times + TIMES_PER_PAGE - 1) // TIMES_PER_PAGE}",
        "noop:0"
    ))
    
    if end_idx < total_times:
        nav_buttons.append(Button.inline(
            "下一页 ➡️",
            f"time_page:{rule_id}:{page+1}"
        ))
    
    buttons.append(nav_buttons)
    buttons.append([Button.inline("👈 返回", f"ai_settings:{rule_id}")])
    
    return buttons

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
            True: '开启',
            False: '关闭'
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
    'is_delete_original': {
        'display_name': '删除原始消息',
        'values': {
            True: '开启',
            False: '关闭'
        },
        'toggle_action': 'toggle_delete_original',
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
    },
    'is_original_sender': {
        'display_name': '原始发送者',
        'values': {
            True: '显示',
            False: '隐藏'
        },
        'toggle_action': 'toggle_original_sender',
        'toggle_func': lambda current: not current
    },
    'is_original_time': {
        'display_name': '发送时间',
        'values': {
            True: '显示',
            False: '隐藏'
        },
        'toggle_action': 'toggle_original_time',
        'toggle_func': lambda current: not current
    }
}

# 添加 AI 设置
AI_SETTINGS = {
    'is_ai': {
        'display_name': 'AI处理',
        'values': {
            True: '开启',
            False: '关闭'
        },
        'toggle_action': 'toggle_ai',
        'toggle_func': lambda current: not current
    },
    'ai_model': {
        'display_name': 'AI模型',
        'values': {
            None: '默认',
            '': '默认',
            **{model: model for model in AI_MODELS}
        },
        'toggle_action': 'change_model',
        'toggle_func': None
    },
    'ai_prompt': {
        'display_name': 'AI提示词',
        'values': {
            None: os.getenv('DEFAULT_AI_PROMPT'),
            '': os.getenv('DEFAULT_AI_PROMPT'),
        },
        'toggle_action': 'set_prompt',
        'toggle_func': None
    },
    'is_summary': {
        'display_name': 'AI总结',
        'values': {
            True: '开启',
            False: '关闭'
        },
        'toggle_action': 'toggle_summary',
        'toggle_func': lambda current: not current
    },
    'summary_time': {
        'display_name': '总结时间',
        'values': {
            None: '00:00',
            '': '00:00'
        },
        'toggle_action': 'set_summary_time',
        'toggle_func': None
    },
    'summary_prompt': {  # 新增配置项
        'display_name': 'AI总结提示词',
        'values': {
            None: os.getenv('DEFAULT_SUMMARY_PROMPT'),
            '': os.getenv('DEFAULT_SUMMARY_PROMPT'),
        },
        'toggle_action': 'set_summary_prompt',
        'toggle_func': None
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
    """创建规则设置按钮"""
    buttons = []
    
    # 获取当前聊天的当前选中规则
    session = get_session()
    try:
        target_chat = rule.target_chat
        current_add_id = target_chat.current_add_id
        source_chat = rule.source_chat
        
        # 添加规则切换按钮
        is_current = current_add_id == source_chat.telegram_chat_id
        buttons.append([
            Button.inline(
                f"{'✅ ' if is_current else ''}应用当前规则",
                f"toggle_current:{rule.id}"
            )
        ])
        
        # 转发模式和转发方式放在一行
        buttons.append([
            Button.inline(
                f"📥 转发模式: {RULE_SETTINGS['mode']['values'][rule.mode]}",
                f"toggle_mode:{rule.id}"
            ),
            Button.inline(
                f"🤖 转发方式: {RULE_SETTINGS['use_bot']['values'][rule.use_bot]}",
                f"toggle_bot:{rule.id}"
            )
        ])
        
        # 其他设置两两一行
        if rule.use_bot:  # 只在使用机器人时显示这些设置
            buttons.append([
                Button.inline(
                    f"🔄 替换模式: {RULE_SETTINGS['is_replace']['values'][rule.is_replace]}",
                    f"toggle_replace:{rule.id}"
                ),
                Button.inline(
                    f"📝 消息格式: {RULE_SETTINGS['message_mode']['values'][rule.message_mode]}",
                    f"toggle_message_mode:{rule.id}"
                )
            ])
            
            buttons.append([
                Button.inline(
                    f"👁 预览模式: {RULE_SETTINGS['is_preview']['values'][rule.is_preview]}",
                    f"toggle_preview:{rule.id}"
                ),
                Button.inline(
                    f"🔗 原始链接: {RULE_SETTINGS['is_original_link']['values'][rule.is_original_link]}",
                    f"toggle_original_link:{rule.id}"
                )
            ])
            
            buttons.append([
                Button.inline(
                    f"👤 原始发送者: {RULE_SETTINGS['is_original_sender']['values'][rule.is_original_sender]}",
                    f"toggle_original_sender:{rule.id}"
                ),
                Button.inline(
                    f"⏰ 发送时间: {RULE_SETTINGS['is_original_time']['values'][rule.is_original_time]}",
                    f"toggle_original_time:{rule.id}"
                )
            ])
            
            buttons.append([
                Button.inline(
                    f"🗑 删除原消息: {RULE_SETTINGS['is_delete_original']['values'][rule.is_delete_original]}",
                    f"toggle_delete_original:{rule.id}"
                ),
                Button.inline(
                    f"🔄 UFB同步: {RULE_SETTINGS['is_ufb']['values'][rule.is_ufb]}",
                    f"toggle_ufb:{rule.id}"
                )
            ])
            
            # AI设置单独一行
            buttons.append([
                Button.inline(
                    "🤖 AI设置",
                    f"ai_settings:{rule.id}"
                )
            ])
        
        # 删除规则和返回按钮
        buttons.append([
            Button.inline(
                "❌ 删除规则",
                f"delete:{rule.id}"
            )
        ])
        
        buttons.append([
            Button.inline(
                "👈 返回",
                "settings"
            )
        ])
        
    finally:
        session.close()
    
    return buttons

def create_ai_settings_buttons(rule):
    """创建 AI 设置按钮"""
    buttons = []
    
    # 添加 AI 设置按钮
    for field, config in AI_SETTINGS.items():
        current_value = getattr(rule, field)
        if field == 'ai_prompt':
            display_value = current_value[:20] + '...' if current_value and len(current_value) > 20 else (current_value or os.getenv('DEFAULT_AI_PROMPT'))
        else:
            display_value = config['values'].get(current_value, str(current_value))
        button_text = f"{config['display_name']}: {display_value}"
        callback_data = f"{config['toggle_action']}:{rule.id}"
        buttons.append([Button.inline(button_text, callback_data)])
    
    # 添加返回按钮
    buttons.append([Button.inline('👈 返回规则设置', f"rule_settings:{rule.id}")])
    
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
        logger.info(f'获取当前聊天: {current_chat.id}')
        
        current_chat_db = session.query(Chat).filter(
            Chat.telegram_chat_id == str(current_chat.id)
        ).first()
        
        if not current_chat_db or not current_chat_db.current_add_id:
            logger.info('未找到当前聊天或未选择源聊天')
            await event.reply('请先使用 /switch 选择一个源聊天')
            return None
        
        logger.info(f'当前选中的源聊天ID: {current_chat_db.current_add_id}')
        
        # 查找对应的规则
        source_chat = session.query(Chat).filter(
            Chat.telegram_chat_id == current_chat_db.current_add_id
        ).first()
        
        if source_chat:
            logger.info(f'找到源聊天: {source_chat.name}')
        else:
            logger.error('未找到源聊天')
            return None
        
        rule = session.query(ForwardRule).filter(
            ForwardRule.source_chat_id == source_chat.id,
            ForwardRule.target_chat_id == current_chat_db.id
        ).first()
        
        if not rule:
            logger.info('未找到对应的转发规则')
            await event.reply('转发规则不存在')
            return None
        
        logger.info(f'找到转发规则 ID: {rule.id}')
        return rule, source_chat
    except Exception as e:
        logger.error(f'获取当前规则时出错: {str(e)}')
        logger.exception(e)
        await event.reply('获取当前规则时出错，请检查日志')
        return None

async def get_all_rules(session, event):
    """获取当前聊天的所有规则"""
    try:
        # 获取当前聊天
        current_chat = await event.get_chat()
        logger.info(f'获取当前聊天: {current_chat.id}')
        
        current_chat_db = session.query(Chat).filter(
            Chat.telegram_chat_id == str(current_chat.id)
        ).first()
        
        if not current_chat_db:
            logger.info('未找到当前聊天')
            await event.reply('当前聊天没有任何转发规则')
            return None
        
        logger.info(f'找到当前聊天数据库记录 ID: {current_chat_db.id}')
        
        # 查找所有以当前聊天为目标的规则
        rules = session.query(ForwardRule).filter(
            ForwardRule.target_chat_id == current_chat_db.id
        ).all()
        
        if not rules:
            logger.info('未找到任何转发规则')
            await event.reply('当前聊天没有任何转发规则')
            return None
            
        logger.info(f'找到 {len(rules)} 条转发规则')
        return rules
    except Exception as e:
        logger.error(f'获取所有规则时出错: {str(e)}')
        logger.exception(e)
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
        'b': lambda: handle_bind_command(event, client, parts),
        'settings': lambda: handle_settings_command(event),
        's': lambda: handle_settings_command(event),
        'switch': lambda: handle_switch_command(event),
        'sw': lambda: handle_switch_command(event),
        'add': lambda: handle_add_command(event, command, parts),
        'a': lambda: handle_add_command(event, command, parts),
        'add_regex': lambda: handle_add_command(event, command, parts),
        'ar': lambda: handle_add_command(event, 'add_regex', parts),
        'replace': lambda: handle_replace_command(event, parts),
        'r': lambda: handle_replace_command(event, parts),
        'list_keyword': lambda: handle_list_keyword_command(event),
        'lk': lambda: handle_list_keyword_command(event),
        'list_replace': lambda: handle_list_replace_command(event),
        'lr': lambda: handle_list_replace_command(event),
        'remove_keyword': lambda: handle_remove_command(event, command, parts),
        'rk': lambda: handle_remove_command(event, 'remove_keyword', parts),
        'remove_replace': lambda: handle_remove_command(event, command, parts),
        'rr': lambda: handle_remove_command(event, 'remove_replace', parts),
        'clear_all': lambda: handle_clear_all_command(event),
        'ca': lambda: handle_clear_all_command(event),
        'start': lambda: handle_start_command(event),
        'help': lambda: handle_help_command(event),
        'h': lambda: handle_help_command(event),
        'export_keyword': lambda: handle_export_keyword_command(event, command),
        'ek': lambda: handle_export_keyword_command(event, command),
        'export_replace': lambda: handle_export_replace_command(event, client),
        'er': lambda: handle_export_replace_command(event, client),
        'add_all': lambda: handle_add_all_command(event, command, parts),
        'aa': lambda: handle_add_all_command(event, 'add_all', parts),
        'add_regex_all': lambda: handle_add_all_command(event, command, parts),
        'ara': lambda: handle_add_all_command(event, 'add_regex_all', parts),
        'replace_all': lambda: handle_replace_all_command(event, parts),
        'ra': lambda: handle_replace_all_command(event, parts),
        'import_keyword': lambda: handle_import_command(event, command),
        'ik': lambda: handle_import_command(event, 'import_keyword'),
        'import_regex_keyword': lambda: handle_import_command(event, command),
        'irk': lambda: handle_import_command(event, 'import_regex_keyword'),
        'import_replace': lambda: handle_import_command(event, command),
        'ir': lambda: handle_import_command(event, 'import_replace'),
        'ufb_bind': lambda: handle_ufb_bind_command(event, command),
        'ub': lambda: handle_ufb_bind_command(event, 'ufb_bind'),
        'ufb_unbind': lambda: handle_ufb_unbind_command(event, command),
        'uu': lambda: handle_ufb_unbind_command(event, 'ufb_unbind'),
        'ufb_item_change': lambda: handle_ufb_item_change_command(event, command),
        'uic': lambda: handle_ufb_item_change_command(event, 'ufb_item_change'),
    }
    
    # 执行对应的命令处理器
    handler = command_handlers.get(command)
    if handler:
        await handler()


async def handle_import_command(event, command):
    """处理导入命令"""
    try:
        # 检查是否有附件
        if not event.message.file:
            await event.reply(f'请将文件和 /{command} 命令一起发送')
            return
            
        # 获取当前规则
        session = get_session()
        try:
            rule_info = await get_current_rule(session, event)
            if not rule_info:
                return
                
            rule, source_chat = rule_info
            
            # 下载文件
            file_path = await event.message.download_media(TEMP_DIR)
            
            try:
                # 读取文件内容
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = [line.strip() for line in f if line.strip()]
                
                # 根据命令类型处理
                if command == 'import_replace':
                    success_count = 0
                    logger.info(f'开始导入替换规则,共 {len(lines)} 行')
                    for i, line in enumerate(lines, 1):
                        try:
                            # 按第一个制表符分割
                            parts = line.split('\t', 1)
                            pattern = parts[0].strip()
                            content = parts[1].strip() if len(parts) > 1 else ''
                            
                            logger.info(f'处理第 {i} 行: pattern="{pattern}", content="{content}"')
                            
                            # 创建替换规则
                            replace_rule = ReplaceRule(
                                rule_id=rule.id,
                                pattern=pattern,
                                content=content
                            )
                            session.add(replace_rule)
                            success_count += 1
                            logger.info(f'成功添加替换规则: pattern="{pattern}", content="{content}"')
                            
                            # 确保启用替换模式
                            if not rule.is_replace:
                                rule.is_replace = True
                                logger.info('已启用替换模式')
                                
                        except Exception as e:
                            logger.error(f'处理第 {i} 行替换规则时出错: {str(e)}\n{traceback.format_exc()}')
                            continue
                            
                    session.commit()
                    logger.info(f'导入完成,成功导入 {success_count} 条替换规则')
                    await event.reply(f'成功导入 {success_count} 条替换规则\n规则: 来自 {source_chat.name}')
                    
                else:
                    # 处理关键字导入
                    db_ops = await get_db_ops()
                    success_count, duplicate_count = await db_ops.add_keywords(
                        session,
                        rule.id,
                        lines,
                        is_regex=(command == 'import_regex_keyword')
                    )
                    
                    session.commit()
                    
                    keyword_type = "正则表达式" if command == "import_regex_keyword" else "关键字"
                    result_text = f'成功导入 {success_count} 个{keyword_type}'
                    if duplicate_count > 0:
                        result_text += f'\n跳过重复: {duplicate_count} 个'
                    result_text += f'\n规则: 来自 {source_chat.name}'
                    
                    await event.reply(result_text)
                    
            finally:
                # 删除临时文件
                if os.path.exists(file_path):
                    os.remove(file_path)
                    
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f'导入过程出错: {str(e)}')
        await event.reply('导入过程出错，请检查日志')

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
    message_text = event.message.text
    if len(message_text.split(None, 1)) < 2:
        await event.reply(f'用法: /{command} <关键字1> [关键字2] ...\n例如:\n/{command} keyword1 "key word 2" \'key word 3\'')
        return
        
    # 分离命令和参数部分
    _, args_text = message_text.split(None, 1)
    
    keywords = []
    if command == 'add':
        # 解析带引号的参数
        current_word = []
        in_quotes = False
        quote_char = None
        
        for char in args_text:
            if char in ['"', "'"]:  # 处理引号
                if not in_quotes:  # 开始引号
                    in_quotes = True
                    quote_char = char
                elif char == quote_char:  # 结束匹配的引号
                    in_quotes = False
                    quote_char = None
                    if current_word:  # 添加当前词
                        keywords.append(''.join(current_word))
                        current_word = []
            elif char.isspace() and not in_quotes:  # 非引号中的空格
                if current_word:  # 添加当前词
                    keywords.append(''.join(current_word))
                    current_word = []
            else:  # 普通字符
                current_word.append(char)
        
        # 处理最后一个词
        if current_word:
            keywords.append(''.join(current_word))
            
        # 过滤空字符串
        keywords = [k.strip() for k in keywords if k.strip()]
    else:
        # add_regex 命令保持原样
        keywords = parts[1:]
    
    if not keywords:
        await event.reply('请提供至少一个关键字')
        return
    
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

async def callback_switch(event, rule_id, session, message):
    """处理切换源聊天的回调"""
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

async def callback_settings(event, rule_id, session, message):
    """处理显示设置的回调"""
    # 获取当前聊天
    current_chat = await event.get_chat()
    current_chat_db = session.query(Chat).filter(
        Chat.telegram_chat_id == str(current_chat.id)
    ).first()
    
    if not current_chat_db:
        await event.answer('当前聊天不存在')
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

async def callback_delete(event, rule_id, session, message):
    """处理删除规则的回调"""
    rule = session.query(ForwardRule).get(rule_id)
    if not rule:
        await event.answer('规则不存在')
        return
    
    try:
        # 先删除替换规则
        session.query(ReplaceRule).filter(
            ReplaceRule.rule_id == rule.id
        ).delete()
        
        # 再删除关键字
        session.query(Keyword).filter(
            Keyword.rule_id == rule.id
        ).delete()
        
        # 最后删除规则
        session.delete(rule)
        session.commit()
        
        # 删除机器人的消息
        await message.delete()
        # 发送新的通知消息
        await event.respond('已删除转发链')
        await event.answer('已删除转发链')
        
    except Exception as e:
        session.rollback()
        logger.error(f'删除规则时出错: {str(e)}')
        await event.answer('删除规则失败，请检查日志')

async def callback_page(event, rule_id, session, message):
    """处理翻页的回调"""
    logger.info(f'翻页回调数据: action=page, rule_id={rule_id}')
    
    try:
        # 解析页码和命令
        page_number, command = rule_id.split(':')
        page = int(page_number)
        
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
        
        # 标记回调已处理
        await event.answer()
        
    except Exception as e:
        logger.error(f'处理翻页时出错: {str(e)}')
        await event.answer('处理翻页时出错，请检查日志')

async def callback_help(event, rule_id, session, message):
    """处理帮助的回调"""
    help_texts = {
        'bind': """
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
""",
        'settings': """
⚙️ 管理设置

使用方法：
/settings - 显示所有转发规则的设置
""",
        'help': """
❓ 完整帮助

请使用 /help 命令查看所有可用命令的详细说明。
"""
    }
    
    help_text = help_texts.get(rule_id, help_texts['help'])
    # 添加返回按钮
    buttons = [[Button.inline('👈 返回', 'start')]]
    await event.edit(help_text, buttons=buttons)

async def callback_start(event, rule_id, session, message):
    """处理返回开始界面的回调"""
    await handle_command(event.client, event)

async def callback_rule_settings(event, rule_id, session, message):
    """处理规则设置的回调"""
    rule = session.query(ForwardRule).get(rule_id)
    if not rule:
        await event.answer('规则不存在')
        return
    
    await message.edit(
        create_settings_text(rule),
        buttons=create_buttons(rule)
    )

async def callback_toggle_current(event, rule_id, session, message):
    """处理切换当前规则的回调"""
    rule = session.query(ForwardRule).get(rule_id)
    if not rule:
        await event.answer('规则不存在')
        return
        
    target_chat = rule.target_chat
    source_chat = rule.source_chat
    
    # 更新当前选中的源聊天
    target_chat.current_add_id = source_chat.telegram_chat_id
    session.commit()
    
    # 更新按钮显示
    await message.edit(
        create_settings_text(rule),
        buttons=create_buttons(rule)
    )
    
    await event.answer(f'已切换到: {source_chat.name}')

async def callback_set_summary_prompt(event, rule_id, session, message):
    """处理设置AI总结提示词的回调"""
    rule = session.query(ForwardRule).get(rule_id)
    if not rule:
        await event.answer('规则不存在')
        return
        
    # 发送提示消息
    await message.edit(
        "请发送新的AI总结提示词，或发送 /cancel 取消",
        buttons=[[Button.inline("取消", f"ai_settings:{rule_id}")]]
    )
    
    # 设置用户状态
    user_id = event.sender_id
    chat_id = event.chat_id
    db_ops = await get_db_ops()
    await db_ops.set_user_state(user_id, chat_id, f"set_summary_prompt:{rule_id}")

# 回调处理器字典
CALLBACK_HANDLERS = {
    'toggle_current': callback_toggle_current,  # 添加新的处理器
    'switch': callback_switch,
    'settings': callback_settings,
    'delete': callback_delete,
    'page': callback_page,
    'help': callback_help,
    'start': callback_start,
    'rule_settings': callback_rule_settings,  # 添加规则设置处理器
    'set_summary_prompt': callback_set_summary_prompt,
}

async def handle_callback(event):
    """处理按钮回调"""
    try:
        data = event.data.decode()
        logger.info(f'收到回调数据: {data}')
        
        if data.startswith('select_model:'):
            # 处理模型选择
            _, rule_id, model = data.split(':')
            session = get_session()
            try:
                rule = session.query(ForwardRule).get(int(rule_id))
                if rule:
                    rule.ai_model = model
                    session.commit()
                    logger.info(f"已更新规则 {rule_id} 的AI模型为: {model}")
                    
                    # 返回到 AI 设置页面
                    await event.edit("AI 设置：", buttons=create_ai_settings_buttons(rule))
            finally:
                session.close()
            return
            
        if data.startswith('ai_settings:'):
            # 显示 AI 设置页面
            rule_id = data.split(':')[1]
            session = get_session()
            try:
                rule = session.query(ForwardRule).get(int(rule_id))
                if rule:
                    await event.edit("AI 设置：", buttons=create_ai_settings_buttons(rule))
            finally:
                session.close()
            return
            
        # 处理 AI 设置中的切换操作
        if data.startswith(('toggle_ai:', 'set_prompt:', 'change_model:', 'set_summary_prompt:')):
            rule_id = data.split(':')[1]
            session = get_session()
            try:
                rule = session.query(ForwardRule).get(int(rule_id))
                if not rule:
                    await event.answer('规则不存在')
                    return
                    
                if data.startswith('set_summary_prompt:'):
                    # 存储当前正在设置总结提示词的规则 ID
                    event.client.setting_prompt_for_rule = int(rule_id)
                    
                    await event.edit(
                        "请发送新的AI总结提示词\n\n"
                        "提示：\n"
                        "1. 可以使用 {Messages} 表示需要总结的所有消息\n"
                        "2. 例如：'请总结以下内容：{Messages}'\n"
                        "3. 当前提示词：" + (rule.summary_prompt or os.getenv('DEFAULT_SUMMARY_PROMPT') or "未设置") + "\n\n"
                        "当前规则ID: " + rule_id + " \n\n"
                        "输入 /cancel 取消设置",
                        buttons=None
                    )
                    return
                    
                if data.startswith('toggle_ai:'):
                    rule.is_ai = not rule.is_ai
                    session.commit()
                    await event.edit("AI 设置：", buttons=create_ai_settings_buttons(rule))
                    return
                elif data.startswith('set_prompt:'):
                    # 存储当前正在设置提示词的规则 ID
                    event.client.setting_prompt_for_rule = int(rule_id)
                    
                    await event.edit(
                        "请输入新的 AI 提示词\n\n"
                        "提示：\n"
                        "1. 可以使用 {Message} 表示原始消息\n"
                        "2. 例如：'请将以下内容翻译成英文：{Message}'\n"
                        "3. 当前提示词：" + (rule.ai_prompt or "未设置") + "\n\n"
                        "当前规则ID: " + rule_id + " \n\n"
                        "输入 /cancel 取消设置",
                        buttons=None
                    )
                    return
                elif data.startswith('change_model:'):
                    await event.edit("请选择AI模型：", buttons=create_model_buttons(rule_id, page=0))
                    return
            finally:
                session.close()
            return
            
        if data.startswith('model_page:'):
            # 处理翻页
            _, rule_id, page = data.split(':')
            page = int(page)
            await event.edit("请选择AI模型：", buttons=create_model_buttons(rule_id, page=page))
            return
            
        if data.startswith('noop:'):
            # 用于页码按钮，不做任何操作
            await event.answer("当前页码")
            return
            
        if data.startswith('select_model:'):
            # 处理模型选择
            _, rule_id, model = data.split(':')
            session = get_session()
            try:
                rule = session.query(ForwardRule).get(int(rule_id))
                if rule:
                    rule.ai_model = model
                    session.commit()
                    logger.info(f"已更新规则 {rule_id} 的AI模型为: {model}")
                    
                    # 返回设置页面
                    text = create_settings_text(rule)
                    buttons = create_buttons(rule)
                    await event.edit(text, buttons=buttons)
            finally:
                session.close()
            return
        if data.startswith('toggle_summary:'):
            rule_id = data.split(':')[1]
            session = get_session()
            try:
                rule = session.query(ForwardRule).get(int(rule_id))
                if rule:
                    rule.is_summary = not rule.is_summary
                    session.commit()
                    
                    # 更新调度任务
                    main = get_main_module()
                    if hasattr(main, 'scheduler') and main.scheduler:
                        await main.scheduler.schedule_rule(rule)
                    else:
                        logger.warning("调度器未初始化")
                    
                    await event.edit("AI 设置：", buttons=create_ai_settings_buttons(rule))
            finally:
                session.close()
            return
            
        if data.startswith('set_summary_time:'):
            rule_id = data.split(':')[1]
            await event.edit("请选择总结时间：", buttons=create_summary_time_buttons(rule_id, page=0))
            return
            
        if data.startswith('select_time:'):
            parts = data.split(':', 2)  # 最多分割2次
            if len(parts) == 3:
                _, rule_id, time = parts
                logger.info(f"设置规则 {rule_id} 的总结时间为: {time}")
                
                session = get_session()
                try:
                    rule = session.query(ForwardRule).get(int(rule_id))
                    if rule:
                        # 记录旧时间
                        old_time = rule.summary_time
                        
                        # 更新时间
                        rule.summary_time = time
                        session.commit()
                        logger.info(f"数据库更新成功: {old_time} -> {time}")
                        
                        # 如果总结功能已开启，重新调度任务
                        if rule.is_summary:
                            logger.info("规则已启用总结功能，开始更新调度任务")
                            main = get_main_module()
                            if hasattr(main, 'scheduler') and main.scheduler:
                                await main.scheduler.schedule_rule(rule)
                                logger.info(f"调度任务更新成功，新时间: {time}")
                            else:
                                logger.warning("调度器未初始化")
                        else:
                            logger.info("规则未启用总结功能，跳过调度任务更新")
                        
                        await event.edit("AI 设置：", buttons=create_ai_settings_buttons(rule))
                        logger.info("界面更新完成")
                except Exception as e:
                    logger.error(f"设置总结时间时出错: {str(e)}")
                    logger.error(f"错误详情: {traceback.format_exc()}")
                finally:
                    session.close()
            return
            
        if data.startswith('time_page:'):
            _, rule_id, page = data.split(':')
            page = int(page)
            await event.edit("请选择总结时间：", buttons=create_summary_time_buttons(rule_id, page=page))
            return
            
        # 解析回调数据
        parts = data.split(':')
        action = parts[0]
        rule_id = ':'.join(parts[1:]) if len(parts) > 1 else None
        logger.info(f'解析回调数据: action={action}, rule_id={rule_id}')
        
        # 获取消息对象
        message = await event.get_message()
        
        # 使用会话
        session = get_session()
        try:
            # 处理设置提示词的特殊情况
            if action == 'set_prompt':
                rule = session.query(ForwardRule).get(int(rule_id))
                if not rule:
                    await event.answer('规则不存在')
                    return
                    
                # 存储当前正在设置提示词的规则 ID
                event.client.setting_prompt_for_rule = int(rule_id)
                
                await event.edit(
                    "请输入新的 AI 提示词\n\n"
                    "提示：\n"
                    "1. 可以使用 {Message} 表示原始消息\n"
                    "2. 例如：'请将以下内容翻译成英文：{Message}'\n"
                    "3. 当前提示词：" + (rule.ai_prompt or "未设置") + "\n\n"
                    "当前规则ID: " + rule_id +" \n\n"                                                  
                    "输入 /cancel 取消设置",
                    buttons=None
                )
                return
            
            # 获取对应的处理器
            handler = CALLBACK_HANDLERS.get(action)
            if handler:
                await handler(event, rule_id, session, message)
            else:
                # 处理规则设置的切换
                for field_name, config in RULE_SETTINGS.items():
                    if action == config['toggle_action']:
                        rule = session.query(ForwardRule).get(int(rule_id))
                        if not rule:
                            await event.answer('规则不存在')
                            return
                            
                        current_value = getattr(rule, field_name)
                        new_value = config['toggle_func'](current_value)
                        setattr(rule, field_name, new_value)
                        
                        try:
                            session.commit()
                            logger.info(f'更新规则 {rule.id} 的 {field_name} 从 {current_value} 到 {new_value}')
                            
                            # 如果切换了转发方式，立即更新按钮
                            try:
                                await message.edit(
                                    create_settings_text(rule),
                                    buttons=create_buttons(rule)
                                )
                            except Exception as e:
                                if 'message was not modified' not in str(e).lower():
                                    raise
                            
                            display_name = config['display_name']
                            if field_name == 'use_bot':
                                await event.answer(f'已切换到{"机器人" if new_value else "用户账号"}模式')
                            else:
                                await event.answer(f'已更新{display_name}')
                        except Exception as e:
                            session.rollback()
                            logger.error(f'更新规则设置时出错: {str(e)}')
                            await event.answer('更新设置失败，请检查日志')
                        break
        finally:
            session.close()
            
    except Exception as e:
        if 'message was not modified' not in str(e).lower():
            logger.error(f'处理按钮回调时出错: {str(e)}')
            logger.error(f'错误堆栈: {traceback.format_exc()}')
            await event.answer('处理请求时出错，请检查日志')

# 注册回调处理器
@events.register(events.CallbackQuery)
async def callback_handler(event):
    """回调处理器入口"""
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


async def create_list_buttons(total_pages, current_page, command):
    """创建分页按钮"""
    buttons = []
    row = []
    
    # 上一页按钮
    if current_page > 1:
        row.append(Button.inline(
            '⬅️ 上一页',
            f'page:{current_page-1}:{command}'  
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
            f'page:{current_page+1}:{command}'  
        ))
    
    buttons.append(row)
    return buttons

async def show_list(event, command, items, formatter, title, page=1):
    """显示分页列表"""

    # KEYWORDS_PER_PAGE
    PAGE_SIZE = KEYWORDS_PER_PAGE
    total_items = len(items)
    total_pages = (total_items + PAGE_SIZE - 1) // PAGE_SIZE
    
    if not items:
        try:
            return await event.edit(f'没有找到任何{title}')
        except:
            return await event.reply(f'没有找到任何{title}')
    
    # 获取当前页的项目
    start = (page - 1) * PAGE_SIZE
    end = min(start + PAGE_SIZE, total_items)
    current_items = items[start:end]
    
    # 格式化列表项
    item_list = [formatter(i + start + 1, item) for i, item in enumerate(current_items)]
    
    # 创建分页按钮
    buttons = await create_list_buttons(total_pages, page, command)
    
    # 构建消息文本
    text = f'{title}:\n{chr(10).join(item_list)}'
    if len(text) > 4096:  # Telegram消息长度限制
        text = text[:4093] + '...'
    
    try:
        return await event.edit(text, buttons=buttons)
    except:
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

            # 检查是否在绑定自己
            if str(target_chat.id) == str(source_chat.id):
                await event.reply('⚠️ 不能将频道/群组绑定到自己')
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
/bind(/b) <目标聊天链接或名称> - 名称用引号包裹

关键字管理
/add(/a) <关键字1> [关键字2] ... - 添加普通关键字到当前规则
/add_regex(/ar) <正则1> [正则2] ... - 添加正则表达式关键字到当前规则
/add_all(/aa) <关键字1> [关键字2] ... - 添加普通关键字到所有规则
/add_regex_all(/ara) <正则1> [正则2] ... - 添加正则表达式关键字到所有规则
/import_keyword(/ik) <同时发送文件> - 指令和文件一起发送，一行一个关键字
/import_regex_keyword(/irk) <同时发送文件> - 指令和文件一起发送，一行一个正则表达式
/export_keyword(/ek) - 导出当前规则的关键字到文件

替换规则
/replace(/r) <匹配模式> <替换内容/替换表达式> - 添加替换规则到当前规则
/replace_all(/ra) <匹配模式> <替换内容/替换表达式> - 添加替换规则到所有规则
/import_replace(/ir) <同时发送文件> - 指令和文件一起发送，一行一个替换规则
/export_replace(/er) - 导出当前规则的替换规则到文件
注意：不填替换内容则删除匹配内容

切换规则
- 在settings中切换当前操作的转发规则

查看列表
/list_keyword(/lk) - 查看当前规则的关键字列表
/list_replace(/lr) - 查看当前规则的替换规则列表

设置管理
/settings(/s) - 显示选用的转发规则的设置

UFB
/ufb_bind(/ub) <域名> - 绑定指定的域名
/ufb_unbind(/ub) - 解除域名绑定
/ufb_item_change(/uc) - 指定绑定域名下的项目

清除数据
/clear_all(/ca) - 清空所有数据
"""
    await event.reply(help_text) 

async def handle_export_keyword_command(event, command):
    """处理 export_keyword 命令"""
    session = get_session()
    try:
        rule_info = await get_current_rule(session, event)
        if not rule_info:
            return
            
        rule, source_chat = rule_info
        
        # 获取所有关键字
        normal_keywords = []
        regex_keywords = []
        
        # 直接从规则对象获取关键字
        for keyword in rule.keywords:
            if keyword.is_regex:
                regex_keywords.append(keyword.keyword)
            else:
                normal_keywords.append(keyword.keyword)
        
        # 创建临时文件
        normal_file = os.path.join(TEMP_DIR, 'keywords.txt')
        regex_file = os.path.join(TEMP_DIR, 'regex_keywords.txt')
        
        # 写入普通关键字，确保每行一个
        with open(normal_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(normal_keywords))
            
        # 写入正则关键字，确保每行一个
        with open(regex_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(regex_keywords))
        
        # 如果两个文件都是空的
        if not normal_keywords and not regex_keywords:
            await event.reply("当前规则没有任何关键字")
            return
            
        try:
            # 先发送文件
            files = []
            if normal_keywords:
                files.append(normal_file)
            if regex_keywords:
                files.append(regex_file)
                
            await event.client.send_file(
                event.chat_id,
                files
            )
            
            # 然后单独发送说明文字
            await event.respond(f"规则: {source_chat.name}")
            
        finally:
            # 删除临时文件
            if os.path.exists(normal_file):
                os.remove(normal_file)
            if os.path.exists(regex_file):
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
        replace_rules = []
        for rule in rule.replace_rules:
            replace_rules.append((rule.pattern, rule.content))
        
        # 如果没有替换规则
        if not replace_rules:
            await event.reply("当前规则没有任何替换规则")
            return
            
        # 创建并写入文件
        replace_file = os.path.join(TEMP_DIR, 'replace_rules.txt')
        
        # 写入替换规则，每行一个规则，用制表符分隔
        with open(replace_file, 'w', encoding='utf-8') as f:
            for pattern, content in replace_rules:
                line = f"{pattern}\t{content if content else ''}"
                f.write(line + '\n')
        
        try:
            # 先发送文件
            await event.client.send_file(
                event.chat_id,
                replace_file
            )
            
            # 然后单独发送说明文字
            await event.respond(f"规则: {source_chat.name}")
            
        finally:
            # 删除临时文件
            if os.path.exists(replace_file):
                os.remove(replace_file)
                
    except Exception as e:
        logger.error(f'导出替换规则时出错: {str(e)}')
        await event.reply('导出替换规则时出错，请检查日志')
    finally:
        session.close()

async def handle_add_all_command(event, command, parts):
    """处理 add_all 和 add_regex_all 命令"""
    message_text = event.message.text
    if len(message_text.split(None, 1)) < 2:
        await event.reply(f'用法: /{command} <关键字1> [关键字2] ...\n例如:\n/{command} keyword1 "key word 2" \'key word 3\'')
        return
        
    # 分离命令和参数部分
    _, args_text = message_text.split(None, 1)
    
    keywords = []
    if command == 'add_all':
        # 解析带引号的参数
        current_word = []
        in_quotes = False
        quote_char = None
        
        for char in args_text:
            if char in ['"', "'"]:  # 处理引号
                if not in_quotes:  # 开始引号
                    in_quotes = True
                    quote_char = char
                elif char == quote_char:  # 结束匹配的引号
                    in_quotes = False
                    quote_char = None
                    if current_word:  # 添加当前词
                        keywords.append(''.join(current_word))
                        current_word = []
            elif char.isspace() and not in_quotes:  # 非引号中的空格
                if current_word:  # 添加当前词
                    keywords.append(''.join(current_word))
                    current_word = []
            else:  # 普通字符
                current_word.append(char)
        
        # 处理最后一个词
        if current_word:
            keywords.append(''.join(current_word))
            
        # 过滤空字符串
        keywords = [k.strip() for k in keywords if k.strip()]
    else:
        # add_regex_all 命令保持原样
        keywords = parts[1:]
    
    if not keywords:
        await event.reply('请提供至少一个关键字')
        return
        
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
            result_text += f'跳过重复: {duplicate_count} 个\n'
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
        
async def process_forward_rule(client, event, chat_id, rule):
    """处理转发规则（机器人模式）"""
    should_forward = False
    message_text = event.message.text or ''
    MAX_MEDIA_SIZE = get_max_media_size()
    check_message_text = pre_handle(message_text)
    
    logger.info(f"处理后的消息文本: {check_message_text}")
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
            
            if not event.message.grouped_id:
                # 使用AI处理消息
                message_text = await ai_handle(message_text, rule)
                
            
            # 如果启用了原始链接，生成链接
            original_link = ''
            if rule.is_original_link:
                original_link = f"\n\n原始消息: https://t.me/c/{str(event.chat_id)[4:]}/{event.message.id}"
            
                        # 获取发送者信息
            sender_info = ""
            if rule.is_original_sender and event.sender:
                sender_name = (
                    event.sender.title if hasattr(event.sender, 'title')
                    else f"{event.sender.first_name or ''} {event.sender.last_name or ''}".strip()
                )
                sender_info = f"{sender_name}\n\n"
            
            # 获取发送时间
            time_info = ""
            if rule.is_original_time:
                try:
                    # 创建时区对象
                    timezone = pytz.timezone(os.getenv('DEFAULT_TIMEZONE', 'Asia/Shanghai'))
                    local_time = event.message.date.astimezone(timezone)
                    time_info = f"\n\n{local_time.strftime('%Y-%m-%d %H:%M:%S')}"
                except Exception as e:
                    logger.error(f'处理时间信息时出错: {str(e)}')
                    time_info = ""  # 如果出错，不添加时间信息
            
         
            
            # 获取原消息的按钮
            buttons = event.message.buttons if hasattr(event.message, 'buttons') else None
            
            if event.message.grouped_id:
                # 处理媒体组
                logger.info(f'处理媒体组消息 组ID: {event.message.grouped_id}')
                
                # 等待更长时间让所有媒体消息到达
                await asyncio.sleep(1)
                
                # 收集媒体组的所有消息
                messages = []
                skipped_media = []  # 记录被跳过的媒体消息
                caption = None  # 保存第一条消息的文本
                first_buttons = None  # 保存第一条消息的按钮
                
                async for message in event.client.iter_messages(
                    event.chat_id,
                    limit=20,
                    min_id=event.message.id - 10,
                    max_id=event.message.id + 10
                ):
                    if message.grouped_id == event.message.grouped_id:
                        # 保存第一条消息的文本和按钮
                        if not caption:
                            caption = message.text
                            first_buttons = message.buttons if hasattr(message, 'buttons') else None
                            logger.info(f'获取到媒体组文本: {caption}')
                            
                            # 应用替换规则
                            if rule.is_replace and caption:
                                try:
                                    for replace_rule in rule.replace_rules:
                                        if replace_rule.pattern == '.*':
                                            caption = replace_rule.content or ''
                                            break 
                                        else:
                                            try:
                                                caption = re.sub(
                                                    replace_rule.pattern,
                                                    replace_rule.content or '',
                                                    caption
                                                )
                                            except re.error:
                                                logger.error(f'替换规则格式错误: {replace_rule.pattern}')
                                except Exception as e:
                                    logger.error(f'应用替换规则时出错: {str(e)}')
                                logger.info(f'替换后的媒体组文本: {caption}')
                        
                        # 检查媒体大小
                        if message.media:
                            file_size = get_media_size(message.media)
                            if MAX_MEDIA_SIZE and file_size > MAX_MEDIA_SIZE:
                                skipped_media.append((message, file_size))
                                continue
                        messages.append(message)
                        logger.info(f'找到媒体组消息: ID={message.id}, 类型={type(message.media).__name__ if message.media else "无媒体"}')
                
                logger.info(f'共找到 {len(messages)} 条媒体组消息，{len(skipped_media)} 条超限')
                
                caption = await ai_handle(caption, rule)

                # 如果所有媒体都超限了，但有文本，就发送文本和提示
                if not messages and caption:
                    # 构建提示信息
                    skipped_info = "\n".join(f"- {size/1024/1024:.1f}MB" for _, size in skipped_media)
                    original_link = f"\n\n原始消息: https://t.me/c/{str(event.chat_id)[4:]}/{event.message.id}"
                    text_to_send = f"{caption}\n\n⚠️ {len(skipped_media)} 个媒体文件超过大小限制 ({MAX_MEDIA_SIZE/1024/1024:.1f}MB):\n{skipped_info}\n原始消息: {original_link}"
                    text_to_send = sender_info + text_to_send + time_info
                    if rule.is_original_link:
                        text_to_send += original_link
                    await client.send_message(
                        target_chat_id,
                        text_to_send,
                        parse_mode=parse_mode,
                        link_preview=True,
                        buttons=first_buttons 
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
                            caption_text = sender_info + caption + time_info 
                            if rule.is_original_link:
                                caption_text += original_link
                            
                            # 作为一个组发送所有文件
                            await client.send_file(
                                target_chat_id,
                                files,
                                caption=caption_text,
                                parse_mode=parse_mode,
                                buttons=first_buttons, 
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
                            link_preview=True,
                            buttons=buttons
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
                                    caption=(sender_info + message_text + time_info + original_link) if message_text else original_link,
                                    parse_mode=parse_mode,
                                    buttons=buttons, 
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
                        
                        # 组合消息文本
                        if message_text:
                            message_text = sender_info + message_text + time_info
                        if rule.is_original_link:
                            message_text += original_link

                        await client.send_message(
                            target_chat_id,
                            message_text,
                            parse_mode=parse_mode,
                            link_preview=link_preview,
                            buttons=buttons 
                        )
                        logger.info(
                            f'[机器人] {"带预览的" if link_preview else "无预览的"}文本消息已发送到: '
                            f'{target_chat.name} ({target_chat_id})'
                        )
                
            # 转发成功后，如果启用了删除原消息
            if rule.is_delete_original:
                try:
                    await event.message.delete()
                    logger.info(f'已删除原始消息 ID: {event.message.id}')
                except Exception as e:
                    logger.error(f'删除原始消息时出错: {str(e)}')
                    

            
            
        except Exception as e:
            logger.error(f'转发消息时出错: {str(e)}')

async def send_welcome_message(client):
    """发送欢迎消息"""
    try:
        user_id = get_user_id()
        welcome_text = (
            "** 🎉 欢迎使用 TelegramForwarder ! **\n\n"
            "更新日志请查看：https://github.com/Heavrnl/TelegramForwarder/releases\n\n"
            "如果您觉得这个项目对您有帮助，欢迎通过以下方式支持我:\n\n" 
            "⭐ **给项目点个小小的 Star:** [TelegramForwarder](https://github.com/Heavrnl/TelegramForwarder)\n"
            "☕ **请我喝杯咖啡:** [Ko-fi](https://ko-fi.com/0heavrnl)\n\n"
            "感谢您的支持!"
        )
        
        await client.send_message(
            user_id,
            welcome_text,
            parse_mode='markdown',
            link_preview=True
        )
        logger.info("已发送欢迎消息")
    except Exception as e:
        logger.error(f"发送欢迎消息失败: {str(e)}")






