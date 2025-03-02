from sqlalchemy.exc import IntegrityError
from telethon import Button

from enums.enums import AddMode
from models.models import get_session, Keyword, ReplaceRule
from utils.common import *
from utils.media import *
from handlers.list_handlers import *
from utils.constants import TEMP_DIR
import traceback

logger = logging.getLogger(__name__)

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
        main = await get_main_module()
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
            button_text = f'{source_chat.name}'
            callback_data = f"rule_settings:{rule.id}"
            buttons.append([Button.inline(button_text, callback_data)])

        await event.reply('请选择要管理的转发规则:', buttons=buttons)

    except Exception as e:
        logger.error(f'获取转发规则时出错: {str(e)}')
        await event.reply('获取转发规则时出错，请检查日志')
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
            is_regex=(command == 'add_regex'),
            is_blacklist=(rule.add_mode == AddMode.BLACKLIST)
        )

        session.commit()

        # 构建回复消息
        keyword_type = "正则" if command == "add_regex" else "关键字"
        keywords_text = '\n'.join(f'- {k}' for k in keywords)
        result_text = f'已添加 {success_count} 个{keyword_type}'
        if duplicate_count > 0:
            result_text += f'\n跳过重复: {duplicate_count} 个'
        result_text += f'\n关键字列表:\n{keywords_text}\n'
        result_text += f'当前规则: 来自 {source_chat.name}\n'
        mode_text = '白名单' if rule.add_mode == AddMode.WHITELIST else '黑名单'
        result_text += f'当前关键字添加模式: {mode_text}'

        await event.reply(result_text)

    except Exception as e:
        session.rollback()
        logger.error(f'添加关键字时出错: {str(e)}')
        await event.reply('添加关键字时出错，请检查日志')
    finally:
        session.close()

async def handle_replace_command(event, parts):
    """处理 replace 命令"""
    message_text = event.message.text
    if len(message_text.split(None, 1)) < 2:
        await event.reply('用法: /replace <匹配规则> [替换内容]\n例如:\n/replace 广告  # 删除匹配内容\n/replace 广告 [已替换]\n/replace "广告 文本" [已替换]\n/replace \'广告 文本\' [已替换]')
        return

    # 分离命令和参数部分
    _, args_text = message_text.split(None, 1)
    
    # 解析带引号的参数
    pattern = None
    content = ''
    
    # 检查第一个参数是否带引号
    if args_text.startswith('"') or args_text.startswith("'"):
        quote_char = args_text[0]
        end_quote_pos = args_text.find(quote_char, 1)
        
        if end_quote_pos > 0:
            # 提取引号内的内容作为匹配规则
            pattern = args_text[1:end_quote_pos]
            # 剩余部分作为替换内容（如果有）
            if len(args_text) > end_quote_pos + 1:
                content = args_text[end_quote_pos + 1:].strip()
        else:
            # 引号未闭合，使用整个参数作为模式
            pattern = args_text
    else:
        # 没有引号的情况，使用第一个空格前的内容作为匹配规则
        args_parts = args_text.split(None, 1)
        pattern = args_parts[0]
        if len(args_parts) > 1:
            content = args_parts[1]

    if not pattern:
        await event.reply('请提供有效的匹配规则')
        return

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
        rule_mode = "blacklist" if rule.add_mode == AddMode.BLACKLIST else "whitelist"
        keywords = await db_ops.get_keywords(session, rule.id, rule_mode)

        await show_list(
            event,
            'keyword',
            keywords,
            lambda i, kw: f'{i}. {kw.keyword}{" (正则)" if kw.is_regex else ""}',
            f'关键字列表\n当前模式: {"黑名单" if rule.add_mode == AddMode.BLACKLIST else "白名单"}\n规则: 来自 {source_chat.name}'
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

async def handle_remove_command(event, command, parts):
    """处理 remove_keyword 和 remove_replace 命令"""
    message_text = event.message.text
    
    # 如果是替换规则，保持原来的 ID 删除方式
    if command == 'remove_replace':
        if len(parts) < 2:
            await event.reply(f'用法: /{command} <ID1> [ID2] [ID3] ...\n例如: /{command} 1 2 3')
            return
            
        try:
            ids_to_remove = [int(x) for x in parts[1:]]
        except ValueError:
            await event.reply('ID必须是数字')
            return
    else:  # remove_keyword
        if len(message_text.split(None, 1)) < 2:
            await event.reply(f'用法: /{command} <关键字1> [关键字2] ...\n例如:\n/{command} keyword1 "key word 2" \'key word 3\'')
            return
            
        # 分离命令和参数部分
        _, args_text = message_text.split(None, 1)
        
        # 解析带引号的参数
        keywords_to_remove = []
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
                        keywords_to_remove.append(''.join(current_word))
                        current_word = []
            elif char.isspace() and not in_quotes:  # 非引号中的空格
                if current_word:  # 添加当前词
                    keywords_to_remove.append(''.join(current_word))
                    current_word = []
            else:  # 普通字符
                current_word.append(char)

        # 处理最后一个词
        if current_word:
            keywords_to_remove.append(''.join(current_word))

        # 过滤空字符串
        keywords_to_remove = [k.strip() for k in keywords_to_remove if k.strip()]
        
        if not keywords_to_remove:
            await event.reply('请提供至少一个关键字')
            return

    # 在 try 块外定义 item_type
    item_type = '关键字' if command == 'remove_keyword' else '替换规则'

    session = get_session()
    try:
        rule_info = await get_current_rule(session, event)
        if not rule_info:
            return

        rule, source_chat = rule_info
        rule_mode = "blacklist" if rule.add_mode == AddMode.BLACKLIST else "whitelist"
        mode_name = "黑名单" if rule.add_mode == AddMode.BLACKLIST else "白名单"

        db_ops = await get_db_ops()
        if command == 'remove_keyword':
            # 获取当前模式下的关键字
            items = await db_ops.get_keywords(session, rule.id, rule_mode)
            
            if not items:
                await event.reply(f'当前规则在{mode_name}模式下没有任何关键字')
                return
                
            # 删除匹配的关键字
            removed_count = 0
            for keyword in keywords_to_remove:
                for item in items:
                    if item.keyword == keyword:
                        session.delete(item)
                        removed_count += 1
                        break
            
            session.commit()
            
            # 重新获取更新后的列表
            remaining_items = await db_ops.get_keywords(session, rule.id, rule_mode)
            
            # 显示删除结果
            if removed_count > 0:
                await event.reply(f"已从{mode_name}中删除 {removed_count} 个关键字")
            else:
                await event.reply(f"在{mode_name}中未找到匹配的关键字")

        else:  # remove_replace
            # 处理替换规则的删除（保持原有逻辑）
            items = await db_ops.get_replace_rules(session, rule.id)
            if not items:
                await event.reply(f'当前规则没有任何{item_type}')
                return

            max_id = len(items)
            invalid_ids = [id for id in ids_to_remove if id < 1 or id > max_id]
            if invalid_ids:
                await event.reply(f'无效的ID: {", ".join(map(str, invalid_ids))}')
                return

            await db_ops.delete_replace_rules(session, rule.id, ids_to_remove)
            session.commit()
            
            remaining_items = await db_ops.get_replace_rules(session, rule.id)
            await event.reply(f'已删除 {len(ids_to_remove)} 个替换规则')


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

async def handle_help_command(event, command):
    """处理帮助命令"""
    help_text = (
        "🤖 **命令列表**\n\n"

        "**基础命令**\n"
        "/start - 开始使用\n"
        "/help(/h) - 显示此帮助信息\n\n"

        "**绑定和设置**\n"
        "/bind(/b) <目标聊天链接或名称> - 绑定源聊天\n"
        "/settings(/s) - 管理转发规则\n"

        "**关键字管理**\n"
        "/add(/a) <关键字> - 添加普通关键字\n"
        "/add_regex(/ar) <正则表达式> - 添加正则表达式\n"
        "/add_all(/aa) <关键字> - 添加普通关键字到所有规则\n"
        "/add_regex_all(/ara) <正则表达式> - 添加正则表达式到所有规则\n"
        "/list_keyword(/lk) - 列出所有关键字\n"
        "/remove_keyword(/rk) <关键词1> [关键词2] [关键词3] ... - 删除关键字\n"
        "/clear_all_keywords(/cak) - 清除当前规则的所有关键字\n"
        "/clear_all_keywords_regex(/cakr) - 清除当前规则的所有正则关键字\n"
        "/copy_keywords(/ck) <规则ID> - 复制指定规则的关键字到当前规则\n"
        "/copy_keywords_regex(/ckr) <规则ID> - 复制指定规则的正则关键字到当前规则\n\n"

        "**替换规则管理**\n"
        "/replace(/r) <模式> [替换内容] - 添加替换规则\n"
        "/replace_all(/ra) <模式> [替换内容] - 添加替换规则到所有规则\n"
        "/list_replace(/lr) - 列出所有替换规则\n"
        "/remove_replace(/rr) <序号> - 删除替换规则\n"
        "/clear_all_replace(/car) - 清除当前规则的所有替换规则\n"
        "/copy_replace(/cr) <规则ID> - 复制指定规则的替换规则到当前规则\n\n"

        "**导入导出**\n"
        "/export_keyword(/ek) - 导出当前规则的关键字\n"
        "/export_replace(/er) - 导出当前规则的替换规则\n"
        "/import_keyword(/ik) <同时发送文件> - 导入普通关键字\n"
        "/import_regex_keyword(/irk) <同时发送文件> - 导入正则关键字\n"
        "/import_replace(/ir) <同时发送文件> - 导入替换规则\n\n"

        "**UFB相关**\n"
        "/ufb_bind(/ub) <域名> - 绑定UFB域名\n"
        "/ufb_unbind(/uu) - 解绑UFB域名\n"
        "/ufb_item_change(/uic) - 切换UFB同步配置类型\n\n"

        "💡 **提示**\n"
        "• 括号内为命令的简写形式\n"
        "• 尖括号 <> 表示必填参数\n"
        "• 方括号 [] 表示可选参数\n"
        "• 导入命令需要同时发送文件"
    )

    await event.reply(help_text, parse_mode='markdown')

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
                regex_keywords.append(f"{keyword.keyword} {1 if keyword.is_blacklist else 0}")
            else:
                normal_keywords.append(f"{keyword.keyword} {1 if keyword.is_blacklist else 0}")

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
                    success_count = 0
                    duplicate_count = 0
                    is_regex = (command == 'import_regex_keyword')
                    for i, line in enumerate(lines, 1):
                        try:
                            # 按空格分割，提取关键字和标志
                            parts = line.split()
                            if len(parts) < 2:
                                raise ValueError("行格式无效，至少需要关键字和标志")
                            flag_str = parts[-1]  # 最后一个部分为标志
                            if flag_str not in ('0', '1'):
                                raise ValueError("标志值必须为 0 或 1")
                            is_blacklist = (flag_str == '1')  # 转换为布尔值
                            keyword = ' '.join(parts[:-1])  # 前面的部分组合为关键字
                            if not keyword:
                                raise ValueError("关键字为空")
                            # 检查是否已存在相同的关键字
                            existing = session.query(Keyword).filter_by(
                                rule_id=rule.id,
                                keyword=keyword,
                                is_regex=is_regex
                            ).first()

                            if existing:
                                duplicate_count += 1
                                continue

                            # 创建新的 Keyword 对象
                            new_keyword = Keyword(
                                rule_id=rule.id,
                                keyword=keyword,
                                is_regex=is_regex,
                                is_blacklist=is_blacklist
                            )
                            session.add(new_keyword)
                            success_count += 1

                        except Exception as e:
                            logger.error(f'处理第 {i} 行时出错: {line}\n{str(e)}')
                            continue

                    session.commit()
                    keyword_type = "正则表达式" if is_regex else "关键字"
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

async def handle_clear_all_keywords_command(event, command):
    """处理清除所有关键字命令"""
    session = get_session()
    try:
        rule_info = await get_current_rule(session, event)
        if not rule_info:
            return

        rule, source_chat = rule_info

        # 获取当前规则的关键字数量
        keyword_count = len(rule.keywords)

        if keyword_count == 0:
            await event.reply("当前规则没有任何关键字")
            return

        # 删除所有关键字
        for keyword in rule.keywords:
            session.delete(keyword)

        session.commit()

        # 发送成功消息
        await event.reply(
            f"✅ 已清除规则 `{rule.id}` 的所有关键字\n"
            f"源聊天: {source_chat.name}\n"
            f"共删除: {keyword_count} 个关键字",
            parse_mode='markdown'
        )

    except Exception as e:
        session.rollback()
        logger.error(f'清除关键字时出错: {str(e)}')
        await event.reply('清除关键字时出错，请检查日志')
    finally:
        session.close()

async def handle_clear_all_keywords_regex_command(event, command):
    """处理清除所有正则关键字命令"""
    session = get_session()
    try:
        rule_info = await get_current_rule(session, event)
        if not rule_info:
            return

        rule, source_chat = rule_info

        # 获取当前规则的正则关键字数量
        regex_keywords = [kw for kw in rule.keywords if kw.is_regex]
        keyword_count = len(regex_keywords)

        if keyword_count == 0:
            await event.reply("当前规则没有任何正则关键字")
            return

        # 删除所有正则关键字
        for keyword in regex_keywords:
            session.delete(keyword)

        session.commit()

        # 发送成功消息
        await event.reply(
            f"✅ 已清除规则 `{rule.id}` 的所有正则关键字\n"
            f"源聊天: {source_chat.name}\n"
            f"共删除: {keyword_count} 个正则关键字",
            parse_mode='markdown'
        )

    except Exception as e:
        session.rollback()
        logger.error(f'清除正则关键字时出错: {str(e)}')
        await event.reply('清除正则关键字时出错，请检查日志')
    finally:
        session.close()

async def handle_clear_all_replace_command(event, command):
    """处理清除所有替换规则命令"""
    session = get_session()
    try:
        rule_info = await get_current_rule(session, event)
        if not rule_info:
            return

        rule, source_chat = rule_info

        # 获取当前规则的替换规则数量
        replace_count = len(rule.replace_rules)

        if replace_count == 0:
            await event.reply("当前规则没有任何替换规则")
            return

        # 删除所有替换规则
        for replace_rule in rule.replace_rules:
            session.delete(replace_rule)

        # 如果没有替换规则了，关闭替换模式
        rule.is_replace = False

        session.commit()

        # 发送成功消息
        await event.reply(
            f"✅ 已清除规则 `{rule.id}` 的所有替换规则\n"
            f"源聊天: {source_chat.name}\n"
            f"共删除: {replace_count} 个替换规则\n"
            "已自动关闭替换模式",
            parse_mode='markdown'
        )

    except Exception as e:
        session.rollback()
        logger.error(f'清除替换规则时出错: {str(e)}')
        await event.reply('清除替换规则时出错，请检查日志')
    finally:
        session.close()

async def handle_copy_keywords_command(event, command):
    """处理复制关键字命令"""
    parts = event.message.text.split()
    if len(parts) != 2:
        await event.reply('用法: /copy_keywords <规则ID>')
        return

    try:
        source_rule_id = int(parts[1])
    except ValueError:
        await event.reply('规则ID必须是数字')
        return

    session = get_session()
    try:
        # 获取当前规则
        rule_info = await get_current_rule(session, event)
        if not rule_info:
            return
        target_rule, source_chat = rule_info

        # 获取源规则
        source_rule = session.query(ForwardRule).get(source_rule_id)
        if not source_rule:
            await event.reply(f'找不到规则ID: {source_rule_id}')
            return

        # 复制关键字
        success_count = 0
        skip_count = 0

        for keyword in source_rule.keywords:
            if not keyword.is_regex:  # 只复制普通关键字
                # 检查是否已存在
                exists = any(k.keyword == keyword.keyword and not k.is_regex
                             for k in target_rule.keywords)
                if not exists:
                    new_keyword = Keyword(
                        rule_id=target_rule.id,
                        keyword=keyword.keyword,
                        is_regex=False,
                        is_blacklist=keyword.is_blacklist
                    )
                    session.add(new_keyword)
                    success_count += 1
                else:
                    skip_count += 1

        session.commit()

        # 发送结果消息
        await event.reply(
            f"✅ 已从规则 `{source_rule_id}` 复制关键字到规则 `{target_rule.id}`\n"
            f"成功复制: {success_count} 个\n"
            f"跳过重复: {skip_count} 个",
            parse_mode='markdown'
        )

    except Exception as e:
        session.rollback()
        logger.error(f'复制关键字时出错: {str(e)}')
        await event.reply('复制关键字时出错，请检查日志')
    finally:
        session.close()

async def handle_copy_keywords_regex_command(event, command):
    """处理复制正则关键字命令"""
    parts = event.message.text.split()
    if len(parts) != 2:
        await event.reply('用法: /copy_keywords_regex <规则ID>')
        return

    try:
        source_rule_id = int(parts[1])
    except ValueError:
        await event.reply('规则ID必须是数字')
        return

    session = get_session()
    try:
        # 获取当前规则
        rule_info = await get_current_rule(session, event)
        if not rule_info:
            return
        target_rule, source_chat = rule_info

        # 获取源规则
        source_rule = session.query(ForwardRule).get(source_rule_id)
        if not source_rule:
            await event.reply(f'找不到规则ID: {source_rule_id}')
            return

        # 复制正则关键字
        success_count = 0
        skip_count = 0

        for keyword in source_rule.keywords:
            if keyword.is_regex:  # 只复制正则关键字
                # 检查是否已存在
                exists = any(k.keyword == keyword.keyword and k.is_regex
                             for k in target_rule.keywords)
                if not exists:
                    new_keyword = Keyword(
                        rule_id=target_rule.id,
                        keyword=keyword.keyword,
                        is_regex=True,
                        is_blacklist=keyword.is_blacklist
                    )
                    session.add(new_keyword)
                    success_count += 1
                else:
                    skip_count += 1

        session.commit()

        # 发送结果消息
        await event.reply(
            f"✅ 已从规则 `{source_rule_id}` 复制正则关键字到规则 `{target_rule.id}`\n"
            f"成功复制: {success_count} 个\n"
            f"跳过重复: {skip_count} 个",
            parse_mode='markdown'
        )

    except Exception as e:
        session.rollback()
        logger.error(f'复制正则关键字时出错: {str(e)}')
        await event.reply('复制正则关键字时出错，请检查日志')
    finally:
        session.close()

async def handle_copy_replace_command(event, command):
    """处理复制替换规则命令"""
    parts = event.message.text.split()
    if len(parts) != 2:
        await event.reply('用法: /copy_replace <规则ID>')
        return

    try:
        source_rule_id = int(parts[1])
    except ValueError:
        await event.reply('规则ID必须是数字')
        return

    session = get_session()
    try:
        # 获取当前规则
        rule_info = await get_current_rule(session, event)
        if not rule_info:
            return
        target_rule, source_chat = rule_info

        # 获取源规则
        source_rule = session.query(ForwardRule).get(source_rule_id)
        if not source_rule:
            await event.reply(f'找不到规则ID: {source_rule_id}')
            return

        # 复制替换规则
        success_count = 0
        skip_count = 0

        for replace_rule in source_rule.replace_rules:
            # 检查是否已存在
            exists = any(r.pattern == replace_rule.pattern
                         for r in target_rule.replace_rules)
            if not exists:
                new_rule = ReplaceRule(
                    rule_id=target_rule.id,
                    pattern=replace_rule.pattern,
                    content=replace_rule.content
                )
                session.add(new_rule)
                success_count += 1
            else:
                skip_count += 1

        session.commit()

        # 发送结果消息
        await event.reply(
            f"✅ 已从规则 `{source_rule_id}` 复制替换规则到规则 `{target_rule.id}`\n"
            f"成功复制: {success_count} 个\n"
            f"跳过重复: {skip_count} 个\n",
            parse_mode='markdown'
        )

    except Exception as e:
        session.rollback()
        logger.error(f'复制替换规则时出错: {str(e)}')
        await event.reply('复制替换规则时出错，请检查日志')
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

