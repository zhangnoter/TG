from telethon import TelegramClient
from models import init_db
from dotenv import load_dotenv
from message_listener import setup_listeners
import os
import asyncio

# 加载环境变量
load_dotenv()

# 从环境变量获取配置
api_id = os.getenv('API_ID')
api_hash = os.getenv('API_HASH')
bot_token = os.getenv('BOT_TOKEN')
phone_number = os.getenv('PHONE_NUMBER')

# 创建客户端
user_client = TelegramClient('user', api_id, api_hash)
bot_client = TelegramClient('bot', api_id, api_hash)

# 初始化数据库
engine = init_db()

# 设置消息监听器
setup_listeners(user_client, bot_client)

async def start_clients():
    # 启动用户客户端
    await user_client.start(phone=phone_number)
    me_user = await user_client.get_me()
    print(f'用户客户端已启动: {me_user.first_name} (@{me_user.username})')
    
    # 启动机器人客户端
    await bot_client.start(bot_token=bot_token)
    me_bot = await bot_client.get_me()
    print(f'机器人客户端已启动: {me_bot.first_name} (@{me_bot.username})')
    
    # 等待两个客户端都断开连接
    await asyncio.gather(
        user_client.run_until_disconnected(),
        bot_client.run_until_disconnected()
    )

if __name__ == '__main__':
    # 运行事件循环
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(start_clients())
    except KeyboardInterrupt:
        print("正在关闭客户端...")
    finally:
        loop.close()