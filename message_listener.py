from telethon import events
from models.models import get_session, Chat, ForwardRule
import logging
from handlers import user_handler, bot_handler
from handlers.prompt_handlers import handle_prompt_setting
import asyncio
import os
from dotenv import load_dotenv
from telethon.tl.types import ChannelParticipantsAdmins
from managers.state_manager import state_manager
from telethon.tl import types
from filters.process import process_forward_rule
# 加载环境变量
load_dotenv()

# 获取调试模式设置
DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'

# 配置日志
if DEBUG:
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
else:
    # 禁用所有日志输出
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.CRITICAL  # 只显示严重错误
    )
    # 禁用特定模块的日志
    logging.getLogger('telethon').setLevel(logging.CRITICAL)
    logging.getLogger('message_listener').setLevel(logging.CRITICAL)
    logging.getLogger('handlers.bot_handler').setLevel(logging.CRITICAL)
    logging.getLogger('handlers.user_handler').setLevel(logging.CRITICAL)
logger = logging.getLogger(__name__)

# 添加一个缓存来存储已处理的媒体组
PROCESSED_GROUPS = set()



def setup_listeners(user_client, bot_client):
    """
    设置消息监听器
    
    Args:
        user_client: 用户客户端（用于监听消息和转发）
        bot_client: 机器人客户端（用于处理命令和转发）
    """
    # 用户客户端监听器
    @user_client.on(events.NewMessage)
    async def user_message_handler(event):
        await handle_user_message(event, user_client, bot_client)
    
    # 机器人客户端监听器
    @bot_client.on(events.NewMessage)
    async def bot_message_handler(event):
        await handle_bot_message(event, bot_client)
        
    # 注册机器人回调处理器
    bot_client.add_event_handler(bot_handler.callback_handler)

async def handle_user_message(event, user_client, bot_client):
    """处理用户客户端收到的消息"""
    chat = await event.get_chat()
    chat_id = abs(chat.id)

    # 检查是否频道消息
    if isinstance(event.chat, types.Channel) and state_manager.check_state():
        sender_id = os.getenv('USER_ID')
        # 频道ID需要加上100前缀
        chat_id = int(f"100{chat_id}")
    else:
        sender_id = event.sender_id

    # 检查用户状态
    current_state = state_manager.get_state(sender_id, chat_id)
    if current_state:
        logger.info(f"当前用户状态: {current_state}")
        # 处理提示词设置
        if await handle_prompt_setting(event, bot_client, sender_id, chat_id, current_state):
            return

    # 检查是否是媒体组消息
    if event.message.grouped_id:
        # 如果这个媒体组已经处理过，就跳过
        group_key = f"{chat_id}:{event.message.grouped_id}"
        if group_key in PROCESSED_GROUPS:
            return
        # 标记这个媒体组为已处理
        PROCESSED_GROUPS.add(group_key)
        # 设置一个合理的过期时间（比如5分钟后）
        asyncio.create_task(clear_group_cache(group_key))
    
    # 记录消息信息
    session = get_session()
    try:
        chat_exists = session.query(Chat).filter(
            Chat.telegram_chat_id == str(chat_id)  # 这里转换为字符串
        ).first()
        
        if chat_exists:
            if event.message.grouped_id:
                logger.info(f'[用户] 收到媒体组消息 来自聊天: {chat_exists.name} ({chat_id}) 组ID: {event.message.grouped_id}')
            else:
                logger.info(f'[用户] 收到新消息 来自聊天: {chat_exists.name} ({chat_id}) 内容: {event.message.text}')
    finally:
        session.close()
    
    # 检查数据库中是否有该聊天的转发规则
    session = get_session()
    try:
        # 查询源聊天
        source_chat = session.query(Chat).filter(
            Chat.telegram_chat_id == str(chat_id)
        ).first()
        
        if not source_chat:
            return
            
        # 添加日志：查询转发规则
        logger.info(f'找到源聊天: {source_chat.name} (ID: {source_chat.id})')
        
        # 查找以当前聊天为源的规则
        rules = session.query(ForwardRule).filter(
            ForwardRule.source_chat_id == source_chat.id
        ).all()
        
        if not rules:
            logger.info(f'聊天 {source_chat.name} 没有转发规则')
            return
            
        # 添加日志：处理规则
        logger.info(f'找到 {len(rules)} 条转发规则')


        
        # 处理每条转发规则
        for rule in rules:
            target_chat = rule.target_chat
            if not rule.enable_rule:
                logger.info(f'规则 {rule.id} 未启用')
                continue
            logger.info(f'处理转发规则 ID: {rule.id} (从 {source_chat.name} 转发到: {target_chat.name})')
            if rule.use_bot:
                # 直接使用过滤器模块中的process_forward_rule函数
                await process_forward_rule(bot_client, event, str(chat_id), rule)
            else:
                await user_handler.process_forward_rule(user_client, event, str(chat_id), rule)
        
    except Exception as e:
        logger.error(f'处理用户消息时发生错误: {str(e)}')
        logger.exception(e)  # 添加详细的错误堆栈
    finally:
        session.close()

async def handle_bot_message(event, bot_client):
    """处理机器人客户端收到的消息（命令）"""
    try:
        # 获取用户ID和聊天ID
        sender_id = event.sender_id
        chat_id = abs(event.chat_id)

        # 检查用户状态
        current_state = state_manager.get_state(sender_id, chat_id)
        
        # 处理提示词设置
        if await handle_prompt_setting(event, bot_client, sender_id, chat_id, current_state):
            return

        # 如果没有特殊状态，则处理常规命令
        await bot_handler.handle_command(bot_client, event)
    except Exception as e:
        logger.error(f'处理机器人命令时发生错误: {str(e)}')
        logger.exception(e)

async def clear_group_cache(group_key, delay=300):  # 5分钟后清除缓存
    """清除已处理的媒体组记录"""
    await asyncio.sleep(delay)
    PROCESSED_GROUPS.discard(group_key) 

async def is_admin(channel_id, user_id, client):
    """检查用户是否为频道管理员"""
    try:
        # 获取频道的管理员列表
        admins = await client.get_participants(channel_id, filter=ChannelParticipantsAdmins)
        # 检查用户是否在管理员列表中
        return any(admin.id == user_id for admin in admins)
    except Exception as e:
        logger.error(f"检查管理员权限时出错: {str(e)}")
        return False 