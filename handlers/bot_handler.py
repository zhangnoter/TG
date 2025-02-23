from telethon import events, Button
from handlers.callback_handlers import handle_callback
from handlers.message_handler import pre_handle, ai_handle
from handlers.command_handlers import *
import logging
import asyncio
from enums.enums import ForwardMode, PreviewMode, MessageMode
from telethon.tl.types import ChannelParticipantsAdmins
from dotenv import load_dotenv
import pytz
from utils.common import *
from utils.media import *
from datetime import datetime, timedelta


logger = logging.getLogger(__name__)

# 确保 temp 目录存在
os.makedirs(TEMP_DIR, exist_ok=True)

load_dotenv()

# 添加缓存字典
_admin_cache = {}
_CACHE_DURATION = timedelta(minutes=30)  # 缓存30分钟

async def get_channel_admins(client, chat_id):
    """获取频道管理员列表，带缓存机制"""
    current_time = datetime.now()
    
    # 检查缓存是否存在且未过期
    if chat_id in _admin_cache:
        cache_data = _admin_cache[chat_id]
        if current_time - cache_data['timestamp'] < _CACHE_DURATION:
            return cache_data['admin_ids']
    
    # 缓存不存在或已过期，重新获取管理员列表
    try:
        admins = await client.get_participants(chat_id, filter=ChannelParticipantsAdmins)
        admin_ids = [admin.id for admin in admins]
        
        # 更新缓存
        _admin_cache[chat_id] = {
            'admin_ids': admin_ids,
            'timestamp': current_time
        }
        return admin_ids
    except Exception as e:
        logger.error(f'获取频道管理员列表失败: {str(e)}')
        return None

async def handle_command(client, event):
    """处理机器人命令"""

    # 检查是否是频道消息
    if event.is_channel:
        # 获取频道管理员列表（使用缓存）
        admin_ids = await get_channel_admins(client, event.chat_id)
        if admin_ids is None:
            return
            
        user_id = await get_user_id()
        if user_id not in admin_ids:
            logger.info(f'非管理员的频道消息，已忽略')
            return
    else:
        # 普通聊天消息，检查发送者ID
        user_id = event.sender_id
        if user_id != await get_user_id():
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
        'help': lambda: handle_help_command(event,'help'),
        'h': lambda: handle_help_command(event,'help'),
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
        'clear_all_keywords': lambda: handle_clear_all_keywords_command(event, command),
        'cak': lambda: handle_clear_all_keywords_command(event, 'clear_all_keywords'),
        'clear_all_keywords_regex': lambda: handle_clear_all_keywords_regex_command(event, command),
        'cakr': lambda: handle_clear_all_keywords_regex_command(event, 'clear_all_keywords_regex'),
        'clear_all_replace': lambda: handle_clear_all_replace_command(event, command),
        'car': lambda: handle_clear_all_replace_command(event, 'clear_all_replace'),
        'copy_keywords': lambda: handle_copy_keywords_command(event, command),
        'ck': lambda: handle_copy_keywords_command(event, 'copy_keywords'),
        'copy_keywords_regex': lambda: handle_copy_keywords_regex_command(event, command),
        'ckr': lambda: handle_copy_keywords_regex_command(event, 'copy_keywords_regex'),
        'copy_replace': lambda: handle_copy_replace_command(event, command),
        'cr': lambda: handle_copy_replace_command(event, 'copy_replace'),
    }

    # 执行对应的命令处理器
    handler = command_handlers.get(command)
    if handler:
        await handler()



# 注册回调处理器
@events.register(events.CallbackQuery)
async def callback_handler(event):
    """回调处理器入口"""
    # 只处理来自管理员的回调
    if event.sender_id != await get_user_id():
        return
    await handle_callback(event)

async def process_edit_message(client, event, chat_id, rule):
    """处理编辑消息"""
    # if rule.is_edit_mode and not rule.is_delete_original:
    #     logger.info(f'进入编辑模式')
    #     try:
    #         # 如果启用了替换模式，处理文本
    #         if rule.is_replace and message_text:
    #             try:
    #                 # 应用所有替换规则
    #                 for replace_rule in rule.replace_rules:
    #                     if replace_rule.pattern == '.*':
    #                         message_text = replace_rule.content or ''
    #                         break  # 如果是全文替换，就不继续处理其他规则
    #                     else:
    #                         try:
    #                             message_text = re.sub(
    #                                 replace_rule.pattern,
    #                                 replace_rule.content or '',
    #                                 message_text
    #                             )
    #                         except re.error:
    #                             logger.error(f'替换规则格式错误: {replace_rule.pattern}')
    #             except Exception as e:
    #                 logger.error(f'应用替换规则时出错: {str(e)}')

    pass



                    

async def process_forward_rule(client, event, chat_id, rule):
    """处理转发规则（机器人模式）"""
    message_text = event.message.text or ''
    original_message_text = message_text
    MAX_MEDIA_SIZE = await get_max_media_size()
    # check_message_text = await pre_handle(message_text)

    # 添加日志
    logger.info(f'处理规则 ID: {rule.id}')
    logger.info(f'消息内容: {message_text}')
    logger.info(f'规则模式: {rule.forward_mode.value}')

    # 使用提取的方法进行关键字检查
    should_forward = await check_keywords(
        rule,
        message_text
    )

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
                if original_message_text:
                    message_text = await ai_handle(message_text, rule)
                if rule.is_keyword_after_ai:
                    # 对AI处理后的文本再次进行关键字检查
                    should_forward = await check_keywords(
                        rule,
                        message_text
                    )
                    if not should_forward:
                        logger.info('AI处理后的文本未通过关键字检查，取消转发')
                        return


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
                            file_size = await get_media_size(message.media)
                            if MAX_MEDIA_SIZE and file_size > MAX_MEDIA_SIZE:
                                skipped_media.append((message, file_size))
                                continue
                        messages.append(message)
                        logger.info(f'找到媒体组消息: ID={message.id}, 类型={type(message.media).__name__ if message.media else "无媒体"}')

                logger.info(f'共找到 {len(messages)} 条媒体组消息，{len(skipped_media)} 条超限')

                if original_message_text:
                    caption = await ai_handle(caption, rule)
                if rule.is_keyword_after_ai:
                    # 对AI处理后的文本再次进行关键字检查
                    should_forward = await check_keywords(
                        rule,
                        caption
                    )
                    if not should_forward:
                        logger.info('AI处理后的文本未通过关键字检查，取消转发')
                        return
                        

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
                    # 转发成功后，如果启用了删除原消息
                    if rule.is_delete_original:
                        try:
                            # 获取 main.py 中的用户客户端
                            main = await get_main_module()
                            user_client = main.user_client  # 获取用户客户端
                            message = await user_client.get_messages(event.chat_id, ids=event.message.id)
                            await message.delete()
                            logger.info(f'已删除原始消息 ID: {event.message.id}')
                        except Exception as e:
                            logger.error(f'删除原始消息时出错: {str(e)}')
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
                    file_size = await get_media_size(event.message.media)
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
                        # 转发成功后，如果启用了删除原消息
                        if rule.is_delete_original:
                            try:
                                # 获取 main.py 中的用户客户端
                                main = await get_main_module()
                                user_client = main.user_client  # 获取用户客户端
                                message = await user_client.get_messages(event.chat_id, ids=event.message.id)
                                await message.delete()
                                logger.info(f'已删除原始消息 ID: {event.message.id}')
                            except Exception as e:
                                logger.error(f'删除原始消息时出错: {str(e)}')
                        return


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
                                # 转发成功后，如果启用了删除原消息
                                # 之后可单独提取出一个方法
                                if rule.is_delete_original and event.message.grouped_id:
                                    try:
                                        # 获取 main.py 中的用户客户端
                                        main = await get_main_module()
                                        user_client = main.user_client  # 获取用户客户端

                                        # 使用用户客户端获取并删除媒体组消息
                                        async for message in user_client.iter_messages(
                                                event.chat_id,
                                                min_id=event.message.id - 10,
                                                max_id=event.message.id + 10,
                                                reverse=True
                                        ):
                                            if message.grouped_id == event.message.grouped_id:
                                                await message.delete()
                                                logger.info(f'已删除媒体组消息 ID: {message.id}')
                                    except Exception as e:
                                        logger.error(f'删除媒体组消息时出错: {str(e)}')
                                elif rule.is_delete_original:
                                    # 单条消息的删除逻辑保持不变
                                    try:
                                        await event.message.delete()
                                        logger.info(f'已删除原始消息 ID: {event.message.id}')
                                    except Exception as e:
                                        logger.error(f'删除原始消息时出错: {str(e)}')
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
            if rule.is_delete_original and event.message.grouped_id:
                try:
                    # 获取 main.py 中的用户客户端
                    main = await get_main_module()
                    user_client = main.user_client  # 获取用户客户端
                    
                    # 使用用户客户端获取并删除媒体组消息
                    async for message in user_client.iter_messages(
                            event.chat_id,
                            min_id=event.message.id - 10,
                            max_id=event.message.id + 10,
                            reverse=True
                    ):
                        if message.grouped_id == event.message.grouped_id:
                            await message.delete()
                            logger.info(f'已删除媒体组消息 ID: {message.id}')
                except Exception as e:
                    logger.error(f'删除媒体组消息时出错: {str(e)}')
            elif rule.is_delete_original:
                # 单条消息的删除逻辑保持不变
                try:
                    await event.message.delete()
                    logger.info(f'已删除原始消息 ID: {event.message.id}')
                except Exception as e:
                    logger.error(f'删除原始消息时出错: {str(e)}')

        except Exception as e:
            logger.error(f'转发消息时出错: {str(e)}')


async def send_welcome_message(client):
    """发送欢迎消息"""
    main = await get_main_module()
    user_id = await get_user_id()
    welcome_text = (
        "** 🎉 欢迎使用 TelegramForwarder ! **\n\n"
        "更新日志请查看：https://github.com/Heavrnl/TelegramForwarder/releases\n\n"
        "如果您觉得这个项目对您有帮助，欢迎通过以下方式支持我:\n\n"
        "⭐ **给项目点个小小的 Star:** [TelegramForwarder](https://github.com/Heavrnl/TelegramForwarder)\n"
        "☕ **请我喝杯咖啡:** [Ko-fi](https://ko-fi.com/0heavrnl)\n\n"
        "感谢您的支持!"
    )

    # 发送新消息
    await client.send_message(
        user_id,
        welcome_text,
        parse_mode='markdown',
        link_preview=True
    )
    logger.info("已发送欢迎消息")



