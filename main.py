from telethon import TelegramClient, types
from telethon.tl.types import BotCommand
from telethon.tl.functions.bots import SetBotCommandsRequest
from handlers.models import init_db
from dotenv import load_dotenv
from message_listener import setup_listeners
import os
import asyncio
import logging
from ufb.ufb_client import UFBClient
from handlers.db_operations import DBOperations

logger = logging.getLogger(__name__)

# 加载环境变量
load_dotenv()

# 从环境变量获取配置
api_id = os.getenv('API_ID')
api_hash = os.getenv('API_HASH')
bot_token = os.getenv('BOT_TOKEN')
phone_number = os.getenv('PHONE_NUMBER')

# 创建 DBOperations 实例
db_ops = None

async def init_db_ops():
    """初始化 DBOperations 实例"""
    global db_ops
    if db_ops is None:
        db_ops = await DBOperations.create()
    return db_ops

# 创建文件夹
os.makedirs('./sessions', exist_ok=True)
os.makedirs('./temp', exist_ok=True)
# 清空./temp文件夹
def clear_temp_dir():
    for file in os.listdir('./temp'):
        os.remove(os.path.join('./temp', file))

# 创建客户端
user_client = TelegramClient('./sessions/user', api_id, api_hash)
bot_client = TelegramClient('./sessions/bot', api_id, api_hash)

# 初始化数据库
engine = init_db()

# 设置消息监听器
setup_listeners(user_client, bot_client)

async def start_clients():
    # 初始化 DBOperations
    global db_ops
    db_ops = await DBOperations.create()
    
    try:
        # 启动用户客户端
        await user_client.start(phone=phone_number)
        me_user = await user_client.get_me()
        print(f'用户客户端已启动: {me_user.first_name} (@{me_user.username})')
        
        # 启动机器人客户端
        await bot_client.start(bot_token=bot_token)
        me_bot = await bot_client.get_me()
        print(f'机器人客户端已启动: {me_bot.first_name} (@{me_bot.username})')
        
        # 注册命令
        await register_bot_commands(bot_client)
        
        # 等待两个客户端都断开连接
        await asyncio.gather(
            user_client.run_until_disconnected(),
            bot_client.run_until_disconnected()
        )
    finally:
        # 关闭 DBOperations
        if db_ops and hasattr(db_ops, 'close'):
            await db_ops.close()

async def register_bot_commands(bot):
    """注册机器人命令"""
    commands = [
        BotCommand(
            command='bind',
            description='绑定源聊天'
        ),
        BotCommand(
            command='settings',
            description='管理转发规则'
        ),
        BotCommand(
            command='switch',
            description='切换当前需要设置的聊天规则'
        ),
        BotCommand(
            command='add',
            description='添加关键字'
        ),
        BotCommand(
            command='add_regex',
            description='添加正则关键字'
        ),
        BotCommand(
            command='list_keyword',
            description='列出所有关键字'
        ),
        BotCommand(
            command='remove_keyword',
            description='删除关键字'
        ),
        BotCommand(
            command='replace',
            description='添加替换规则'
        ),
        BotCommand(
            command='list_replace',
            description='列出所有替换规则'
        ),
        BotCommand(
            command='remove_replace',
            description='删除替换规则'
        ),
        BotCommand(
            command='clear_all',
            description='清空当前聊天的所有数据'
        ),
        BotCommand(
            command='add_all',
            description='添加普通关键字到所有规则'
        ),
        BotCommand(
            command='add_regex_all',
            description='添加正则表达式到所有规则'
        ),
        BotCommand(
            command='replace_all',
            description='添加替换规则到所有规则'
        ),
        BotCommand(
            command='help',
            description='查看帮助'
        ),
        BotCommand(
            command='start',
            description='开始使用'
        ),
        BotCommand(
            command='export_keyword',
            description='导出当前规则的关键字'
        ),
        BotCommand(
            command='export_replace',
            description='导出当前规则的替换规则'
        ),
        BotCommand(
            command='import_keyword',
            description='导入普通关键字'
        ),
        BotCommand(
            command='import_regex_keyword',
            description='导入正则表达式关键字'
        ),
        BotCommand(
            command='import_replace',
            description='导入替换规则'
        ),
        BotCommand(
            command='ufb_bind',
            description='绑定ufb域名'
        ),
        BotCommand(
            command='ufb_unbind',
            description='解绑ufb域名'
        ),
        BotCommand(
            command='ufb_item_change',
            description='切换ufb同步配置类型'
        )
    ]
    
    try:
        result = await bot(SetBotCommandsRequest(
            scope=types.BotCommandScopeDefault(),
            lang_code='',  # 空字符串表示默认语言
            commands=commands
        ))
        if result:
            logger.info('已成功注册机器人命令')
        else:
            logger.error('注册机器人命令失败')
    except Exception as e:
        logger.error(f'注册机器人命令时出错: {str(e)}')

if __name__ == '__main__':
    # 运行事件循环
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(start_clients())
    except KeyboardInterrupt:
        print("正在关闭客户端...")
    finally:
        loop.close()