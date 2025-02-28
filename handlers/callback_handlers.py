import os
import traceback
from managers.state_manager import state_manager
import asyncio
from datetime import datetime, timedelta
from telethon.tl import types

from handlers.button_helpers import create_ai_settings_buttons, create_model_buttons, create_summary_time_buttons,create_delay_time_buttons
from handlers.list_handlers import show_list
from managers.settings_manager import create_settings_text, create_buttons, RULE_SETTINGS
from models.models import Chat, ForwardRule, ReplaceRule, Keyword,get_session
from telethon import events, Button
import logging
from utils.common import get_db_ops, get_main_module, get_ai_settings_text
from utils.common import is_admin

logger = logging.getLogger(__name__)







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
        button_text = f'{source_chat.name}'
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
        # 保存源频道ID以供后续检查
        source_chat_id = rule.source_chat_id

        # 先删除替换规则
        session.query(ReplaceRule).filter(
            ReplaceRule.rule_id == rule.id
        ).delete()

        # 再删除关键字
        session.query(Keyword).filter(
            Keyword.rule_id == rule.id
        ).delete()

        # 删除规则
        session.delete(rule)

        # 检查源频道是否还有其他规则引用
        remaining_rules = session.query(ForwardRule).filter(
            ForwardRule.source_chat_id == source_chat_id
        ).count()

        if remaining_rules == 0:
            # 如果没有其他规则引用这个源频道，删除源频道记录
            source_chat = session.query(Chat).filter(
                Chat.id == source_chat_id
            ).first()
            if source_chat:
                logger.info(f'删除未使用的源频道: {source_chat.name} (ID: {source_chat.telegram_chat_id})')
                session.delete(source_chat)

        session.commit()

        # 删除机器人的消息
        await message.delete()
        # 发送新的通知消息
        await event.respond('已删除转发链')
        await event.answer('已删除转发链')

    except Exception as e:
        session.rollback()
        logger.error(f'删除规则时出错: {str(e)}')
        logger.exception(e)
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

async def callback_rule_settings(event, rule_id, session, message):
    """处理规则设置的回调"""
    rule = session.query(ForwardRule).get(rule_id)
    if not rule:
        await event.answer('规则不存在')
        return

    await message.edit(
        await create_settings_text(rule),
        buttons=await create_buttons(rule)
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
        await create_settings_text(rule),
        buttons=await create_buttons(rule)
    )

    await event.answer(f'已切换到: {source_chat.name}')


async def cancel_state_after_timeout(user_id: int, chat_id: int, timeout_minutes: int = 5):
    """在指定时间后自动取消状态"""
    await asyncio.sleep(timeout_minutes * 60)
    current_state = state_manager.get_state(user_id, chat_id)
    if current_state:  # 只有当状态还存在时才清除
        logger.info(f"状态超时自动取消 - user_id: {user_id}, chat_id: {chat_id}")
        state_manager.clear_state(user_id, chat_id)

async def callback_set_summary_prompt(event, rule_id, session, message):
    """处理设置AI总结提示词的回调"""
    logger.info(f"开始处理设置AI总结提示词回调 - event: {event}, rule_id: {rule_id}")
    
    rule = session.query(ForwardRule).get(rule_id)
    if not rule:
        await event.answer('规则不存在')
        return

    # 检查是否频道消息
    if isinstance(event.chat, types.Channel):
        # 检查是否是管理员
        if not await is_admin(event.chat_id, event.sender_id, event.client):
            await event.answer('只有管理员可以修改设置')
            return
        user_id = os.getenv('USER_ID')
    else:
        user_id = event.sender_id

    chat_id = abs(event.chat_id)
    state = f"set_summary_prompt:{rule_id}"
    
    logger.info(f"准备设置状态 - user_id: {user_id}, chat_id: {chat_id}, state: {state}")
    try:
        state_manager.set_state(user_id, chat_id, state)
        # 启动超时取消任务
        asyncio.create_task(cancel_state_after_timeout(user_id, chat_id))
        logger.info("状态设置成功")
    except Exception as e:
        logger.error(f"设置状态时出错: {str(e)}")
        logger.exception(e)

    try:
        current_prompt = rule.summary_prompt or os.getenv('DEFAULT_SUMMARY_PROMPT', '未设置')
        await message.edit(
            f"请发送新的AI总结提示词\n"
            f"当前规则ID: `{rule_id}`\n"
            f"当前AI总结提示词：\n\n`{current_prompt}`\n\n"
            f"5分钟内未设置将自动取消",
            buttons=[[Button.inline("取消", f"cancel_set_summary:{rule_id}")]]
        )
        logger.info("消息编辑成功")
    except Exception as e:
        logger.error(f"编辑消息时出错: {str(e)}")
        logger.exception(e)

async def callback_set_ai_prompt(event, rule_id, session, message):
    """处理设置AI提示词的回调"""
    logger.info(f"开始处理设置AI提示词回调 - event: {event}, rule_id: {rule_id}")

    rule = session.query(ForwardRule).get(rule_id)
    if not rule:
        await event.answer('规则不存在')
        return

    # 检查是否频道消息
    if isinstance(event.chat, types.Channel):
        # 检查是否是管理员
        if not await is_admin(event.chat_id, event.sender_id, event.client):
            await event.answer('只有管理员可以修改设置')
            return
        user_id = os.getenv('USER_ID')
    else:
        user_id = event.sender_id

    chat_id = abs(event.chat_id)
    state = f"set_ai_prompt:{rule_id}"

    logger.info(f"准备设置状态 - user_id: {user_id}, chat_id: {chat_id}, state: {state}")
    try:
        state_manager.set_state(user_id, chat_id, state)
        # 启动超时取消任务
        asyncio.create_task(cancel_state_after_timeout(user_id, chat_id))
        logger.info("状态设置成功")
    except Exception as e:
        logger.error(f"设置状态时出错: {str(e)}")
        logger.exception(e)

    try:
        current_prompt = rule.ai_prompt or os.getenv('DEFAULT_AI_PROMPT', '未设置')
        await message.edit(
            f"请发送新的AI提示词\n"
            f"当前规则ID: `{rule_id}`\n"
            f"当前AI提示词：\n\n`{current_prompt}`\n\n"
            f"5分钟内未设置将自动取消",
            buttons=[[Button.inline("取消", f"cancel_set_prompt:{rule_id}")]]
        )
        logger.info("消息编辑成功")
    except Exception as e:
        logger.error(f"编辑消息时出错: {str(e)}")
        logger.exception(e)

async def callback_toggle_top_summary(event, rule_id, session, message):
    """处理切换顶置总结消息的回调"""
    logger.info(f"处理切换顶置总结消息回调 - rule_id: {rule_id}")
    
    rule = session.query(ForwardRule).get(rule_id)
    if not rule:
        await event.answer('规则不存在')
        return

    # 切换状态
    rule.is_top_summary = not rule.is_top_summary
    session.commit()
    logger.info(f"已更新规则 {rule_id} 的顶置总结状态为: {rule.is_top_summary}")

    # 更新按钮
    await message.edit(
        buttons=await create_ai_settings_buttons(rule)
    )
    
    # 显示提示
    await event.answer(f"已{'开启' if rule.is_top_summary else '关闭'}顶置总结消息")

async def handle_callback(event):
    """处理按钮回调"""
    try:
        data = event.data.decode()
        logger.info(f'收到回调数据: {data}')

        # 处理取消设置提示词
        if data.startswith(('cancel_set_prompt:', 'cancel_set_summary:')):
            rule_id = data.split(':')[1]
            session = get_session()
            try:
                rule = session.query(ForwardRule).get(int(rule_id))
                if rule:
                    # 清除状态
                    state_manager.clear_state(event.sender_id, abs(event.chat_id))
                    # 返回到 AI 设置页面
                    await event.edit(await get_ai_settings_text(rule), buttons=await create_ai_settings_buttons(rule))
                    await event.answer("已取消设置")
            finally:
                session.close()
            return

        if data.startswith('set_summary_prompt:'):
            # 直接处理设置总结提示词的回调
            rule_id = data.split(':')[1]
            logger.info(f"处理设置AI总结提示词回调 - rule_id: {rule_id}")
            session = get_session()
            try:
                await callback_set_summary_prompt(event, rule_id, session, await event.get_message())
            finally:
                session.close()
            return

        if data.startswith('set_ai_prompt:'):
            # 直接处理设置AI提示词的回调
            rule_id = data.split(':')[1]
            logger.info(f"处理设置AI提示词回调 - rule_id: {rule_id}")
            session = get_session()
            try:
                await callback_set_ai_prompt(event, rule_id, session, await event.get_message())
            finally:
                session.close()
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

                    # 返回到 AI 设置页面
                    await event.edit(await get_ai_settings_text(rule), buttons=await create_ai_settings_buttons(rule))
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
                    await event.edit(await get_ai_settings_text(rule), buttons=await create_ai_settings_buttons(rule))
            finally:
                session.close()
            return

        # 处理 AI 设置中的切换操作
        if data.startswith(
                ('toggle_ai:',  'change_model:',  'toggle_keyword_after_ai:')):
            rule_id = data.split(':')[1]
            session = get_session()
            try:
                rule = session.query(ForwardRule).get(int(rule_id))
                if not rule:
                    await event.answer('规则不存在')
                    return

                if data.startswith('toggle_keyword_after_ai:'):
                    rule.is_keyword_after_ai = not rule.is_keyword_after_ai
                    session.commit()
                    await event.edit(await get_ai_settings_text(rule), buttons=await create_ai_settings_buttons(rule))
                    await event.answer(f'AI处理后关键字过滤已{"开启" if rule.is_keyword_after_ai else "关闭"}')
                    return

                if data.startswith('toggle_ai:'):
                    rule.is_ai = not rule.is_ai
                    session.commit()
                    await event.edit(await get_ai_settings_text(rule), buttons=await create_ai_settings_buttons(rule))
                    return
                elif data.startswith('change_model:'):
                    await event.edit("请选择AI模型：", buttons=await create_model_buttons(rule_id, page=0))
                    return
            finally:
                session.close()
            return

        if data.startswith('model_page:'):
            # 处理翻页
            _, rule_id, page = data.split(':')
            page = int(page)
            await event.edit("请选择AI模型：", buttons=await create_model_buttons(rule_id, page=page))
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
                    text =await create_settings_text(rule)
                    buttons =await create_buttons(rule)
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
                    main = await get_main_module()
                    if hasattr(main, 'scheduler') and main.scheduler:
                        await main.scheduler.schedule_rule(rule)
                    else:
                        logger.warning("调度器未初始化")

                    await event.edit(await get_ai_settings_text(rule), buttons=await create_ai_settings_buttons(rule))
            finally:
                session.close()
            return

        if data.startswith('set_summary_time:'):
            rule_id = data.split(':')[1]
            await event.edit("请选择总结时间：", buttons=await create_summary_time_buttons(rule_id, page=0))
            return
        
        if data.startswith('set_delay_time:'):
            rule_id = data.split(':')[1]
            await event.edit("请选择延迟时间：", buttons=await create_delay_time_buttons(rule_id, page=0))
            return
        
        if data.startswith('select_delay_time:'):
            parts = data.split(':', 2)  # 最多分割2次
            if len(parts) == 3:
                _, rule_id, time = parts
                logger.info(f"设置规则 {rule_id} 的延迟时间为: {time}")

                session = get_session()
                try:
                    rule = session.query(ForwardRule).get(int(rule_id))
                    if rule:
                        # 记录旧时间
                        old_time = rule.delay_seconds

                        # 更新时间
                        rule.delay_seconds = int(time)
                        session.commit()
                        logger.info(f"数据库更新成功: {old_time} -> {time}")

                        # 获取消息对象
                        message = await event.get_message()

                        await message.edit(
                            await create_settings_text(rule),
                            buttons=await create_buttons(rule)
                        )
                        logger.info("界面更新完成")
                except Exception as e:
                    logger.error(f"设置延迟时间时出错: {str(e)}")
                    logger.error(f"错误详情: {traceback.format_exc()}")
                finally:
                    session.close()
            return

        if data.startswith('delay_time_page:'):
            _, rule_id, page = data.split(':')
            page = int(page)
            await event.edit("请选择延迟时间：", buttons=await create_summary_time_buttons(rule_id, page=page))
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
                            main = await get_main_module()
                            if hasattr(main, 'scheduler') and main.scheduler:
                                await main.scheduler.schedule_rule(rule)
                                logger.info(f"调度任务更新成功，新时间: {time}")
                            else:
                                logger.warning("调度器未初始化")
                        else:
                            logger.info("规则未启用总结功能，跳过调度任务更新")

                        await event.edit(await get_ai_settings_text(rule), buttons=await create_ai_settings_buttons(rule))
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
            await event.edit("请选择总结时间：", buttons=await create_summary_time_buttons(rule_id, page=page))
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
                                    await create_settings_text(rule),
                                    buttons=await create_buttons(rule)
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


# 回调处理器字典
CALLBACK_HANDLERS = {
    'toggle_current': callback_toggle_current,
    'switch': callback_switch,
    'settings': callback_settings,
    'delete': callback_delete,
    'page': callback_page,
    'help': callback_help,
    'rule_settings': callback_rule_settings,
    'set_summary_prompt': callback_set_summary_prompt,
    'set_ai_prompt': callback_set_ai_prompt,
    'toggle_top_summary': callback_toggle_top_summary,
    
}

