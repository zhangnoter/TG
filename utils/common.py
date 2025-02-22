import importlib
import os
import sys
import logging
from models.models import Chat, ForwardRule
import re

logger = logging.getLogger(__name__)

async def get_main_module():
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
    main = await get_main_module()
    if main.db_ops is None:
        main.db_ops = await main.init_db_ops()
    return main.db_ops

async def get_user_id():
    """获取用户ID，确保环境变量已加载"""
    user_id_str = os.getenv('USER_ID')
    if not user_id_str:
        logger.error('未设置 USER_ID 环境变量')
        raise ValueError('必须在 .env 文件中设置 USER_ID')
    return int(user_id_str)


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


async def check_keywords(rule, message_text, is_whitelist=True):
    """
    检查消息是否匹配关键字规则

    Args:
        rule: 转发规则对象
        message_text: 要检查的消息文本
        is_whitelist: 是否为白名单模式，默认为True

    Returns:
        bool: 是否应该转发消息
    """
    should_forward = not is_whitelist  # 白名单模式默认不转发，黑名单模式默认转发

    for keyword in rule.keywords:
        logger.info(f'检查{"白名单" if is_whitelist else "黑名单"}关键字: {keyword.keyword} (正则: {keyword.is_regex})')
        matched = False

        if keyword.is_regex:
            # 正则表达式匹配
            try:
                if re.search(keyword.keyword, message_text):
                    matched = True
                    logger.info(f'正则匹配成功: {keyword.keyword}')
            except re.error:
                logger.error(f'正则表达式错误: {keyword.keyword}')
        else:
            # 普通关键字匹配（包含即可，不区分大小写）
            if keyword.keyword.lower() in message_text.lower():
                matched = True
                logger.info(f'关键字匹配成功: {keyword.keyword}')

        if matched:
            should_forward = is_whitelist  # 白名单模式匹配则转发，黑名单模式匹配则不转发
            break

    logger.info(f'关键字检查结果: {"转发" if should_forward else "不转发"}')
    return should_forward