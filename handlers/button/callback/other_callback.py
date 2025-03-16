import traceback
import aiohttp

from handlers.button.button_helpers import create_media_size_buttons,create_media_settings_buttons,create_media_types_buttons,create_media_extensions_buttons
from models.models import ForwardRule, MediaTypes, MediaExtensions, RuleSync, Keyword, ReplaceRule
from enums.enums import AddMode
import logging
from utils.common import get_media_settings_text, get_db_ops
from models.models import get_session
from models.db_operations import DBOperations
from handlers.button.button_helpers import create_other_settings_buttons
from telethon import Button
from sqlalchemy import inspect
from utils.constants import RSS_HOST, RSS_PORT,RULES_PER_PAGE
from utils.common import check_and_clean_chats
from utils.auto_delete import reply_and_delete, send_message_and_delete, respond_and_delete

logger = logging.getLogger(__name__)



async def callback_other_settings(event, rule_id, session, message, data):
    await event.edit("其他设置：", buttons=await create_other_settings_buttons(rule_id=rule_id))
    return

async def callback_copy_rule(event, rule_id, session, message, data):
    """复制规则设置
    
    显示可选择的规则列表，供用户选择要复制到的目标规则。
    选择后将当前规则的设置复制到目标规则。
    """
    try:
        # 检查是否包含page参数
        parts = data.split(':')
        page = 0
        if len(parts) > 2:
            page = int(parts[2])
        
        # 创建规则选择按钮
        buttons = await create_copy_rule_buttons(rule_id, page)
        await event.edit("请选择要将当前规则复制到的目标规则：", buttons=buttons)
    except Exception as e:
        logger.error(f"显示复制规则选择界面时出错: {str(e)}")
        logger.error(f"错误详情: {traceback.format_exc()}")
        await event.answer("显示复制规则界面失败")
    
    return

async def create_copy_rule_buttons(rule_id, page=0):
    """创建复制规则按钮列表
    
    Args:
        rule_id: 当前规则ID
        page: 当前页码
        
    Returns:
        按钮列表
    """
    # 设置分页参数
    RULES_PER_PAGE = 5  # 每页显示的规则数量
    
    buttons = []
    session = get_session()
    
    try:
        # 获取当前规则
        source_rule_id = int(rule_id)
        current_rule = session.query(ForwardRule).get(source_rule_id)
        if not current_rule:
            buttons.append([Button.inline('❌ 规则不存在', 'noop')])
            buttons.append([Button.inline('关闭', 'close_settings')])
            return buttons
        
        # 获取所有规则（除了当前规则）
        all_rules = session.query(ForwardRule).filter(
            ForwardRule.id != source_rule_id
        ).all()
        
        # 计算分页
        total_rules = len(all_rules)
        total_pages = (total_rules + RULES_PER_PAGE - 1) // RULES_PER_PAGE
        
        if total_rules == 0:
            buttons.append([
                Button.inline('👈 返回', f"other_settings:{source_rule_id}"),
                Button.inline('❌ 关闭', 'close_settings')
            ])
            return buttons
        
        # 获取当前页的规则
        start_idx = page * RULES_PER_PAGE
        end_idx = min(start_idx + RULES_PER_PAGE, total_rules)
        current_page_rules = all_rules[start_idx:end_idx]
        
        # 创建规则按钮
        for rule in current_page_rules:
            # 获取源聊天和目标聊天名称
            source_chat = rule.source_chat
            target_chat = rule.target_chat
            
            # 创建按钮文本
            button_text = f"{rule.id} {source_chat.name}->{target_chat.name}"
            
            # 创建回调数据：perform_copy_rule:源规则ID:目标规则ID
            callback_data = f"perform_copy_rule:{source_rule_id}:{rule.id}"
            
            buttons.append([Button.inline(button_text, callback_data)])
        
        # 添加分页按钮
        page_buttons = []
        
        if total_pages > 1:
            # 上一页按钮
            if page > 0:
                page_buttons.append(Button.inline("⬅️", f"copy_rule:{source_rule_id}:{page-1}"))
            else:
                page_buttons.append(Button.inline("⬅️", f"noop"))
            
            # 页码指示
            page_buttons.append(Button.inline(f"{page+1}/{total_pages}", f"noop"))
            
            # 下一页按钮
            if page < total_pages - 1:
                page_buttons.append(Button.inline("➡️", f"copy_rule:{source_rule_id}:{page+1}"))
            else:
                page_buttons.append(Button.inline("➡️", f"noop"))
        
        if page_buttons:
            buttons.append(page_buttons)
        
        buttons.append([
            Button.inline('👈 返回', f"other_settings:{source_rule_id}"),
            Button.inline('❌ 关闭', 'close_settings')
        ])
    
    finally:
        session.close()
    
    return buttons

async def callback_perform_copy_rule(event, rule_id_data, session, message, data):
    """执行复制规则操作
    
    Args:
        rule_id_data: 格式为 "源规则ID:目标规则ID"
    """
    try:
        # 解析规则ID
        parts = rule_id_data.split(':')
        if len(parts) != 2:
            await event.answer("数据格式错误")
            return
            
        source_rule_id = int(parts[0])
        target_rule_id = int(parts[1])
        
        # 获取源规则和目标规则
        source_rule = session.query(ForwardRule).get(source_rule_id)
        target_rule = session.query(ForwardRule).get(target_rule_id)
        
        if not source_rule or not target_rule:
            await event.answer("源规则或目标规则不存在")
            return
            
        if source_rule.id == target_rule.id:
            await event.answer('不能复制规则到自身')
            return
        
        # 记录复制的各个部分成功数量
        keywords_normal_success = 0
        keywords_normal_skip = 0
        keywords_regex_success = 0
        keywords_regex_skip = 0
        replace_rules_success = 0
        replace_rules_skip = 0
        media_extensions_success = 0
        media_extensions_skip = 0
        rule_syncs_success = 0
        rule_syncs_skip = 0
        
        # 复制普通关键字
        for keyword in source_rule.keywords:
            if not keyword.is_regex:  # 普通关键字
                # 检查是否已存在
                exists = any(not k.is_regex and k.keyword == keyword.keyword and k.is_blacklist == keyword.is_blacklist
                           for k in target_rule.keywords)
                if not exists:
                    new_keyword = Keyword(
                        rule_id=target_rule.id,
                        keyword=keyword.keyword,
                        is_regex=False,
                        is_blacklist=keyword.is_blacklist
                    )
                    session.add(new_keyword)
                    keywords_normal_success += 1
                else:
                    keywords_normal_skip += 1

        # 复制正则关键字
        for keyword in source_rule.keywords:
            if keyword.is_regex:  # 正则关键字
                # 检查是否已存在
                exists = any(k.is_regex and k.keyword == keyword.keyword and k.is_blacklist == keyword.is_blacklist
                           for k in target_rule.keywords)
                if not exists:
                    new_keyword = Keyword(
                        rule_id=target_rule.id,
                        keyword=keyword.keyword,
                        is_regex=True,
                        is_blacklist=keyword.is_blacklist
                    )
                    session.add(new_keyword)
                    keywords_regex_success += 1
                else:
                    keywords_regex_skip += 1

        # 复制替换规则
        for replace_rule in source_rule.replace_rules:
            # 检查是否已存在
            exists = any(r.pattern == replace_rule.pattern and r.content == replace_rule.content
                         for r in target_rule.replace_rules)
            if not exists:
                new_rule = ReplaceRule(
                    rule_id=target_rule.id,
                    pattern=replace_rule.pattern,
                    content=replace_rule.content
                )
                session.add(new_rule)
                replace_rules_success += 1
            else:
                replace_rules_skip += 1

        # 复制媒体扩展名设置
        if hasattr(source_rule, 'media_extensions') and source_rule.media_extensions:
            for extension in source_rule.media_extensions:
                # 检查是否已存在
                exists = any(e.extension == extension.extension for e in target_rule.media_extensions)
                if not exists:
                    new_extension = MediaExtensions(
                        rule_id=target_rule.id,
                        extension=extension.extension
                    )
                    session.add(new_extension)
                    media_extensions_success += 1
                else:
                    media_extensions_skip += 1

        # 复制媒体类型设置
        if hasattr(source_rule, 'media_types') and source_rule.media_types:
            target_media_types = session.query(MediaTypes).filter_by(rule_id=target_rule.id).first()

            if not target_media_types:
                # 如果目标规则没有媒体类型设置，创建新的
                target_media_types = MediaTypes(rule_id=target_rule.id)

                # 使用inspect自动复制所有字段（除了id和rule_id）
                media_inspector = inspect(MediaTypes)
                for column in media_inspector.columns:
                    column_name = column.key
                    if column_name not in ['id', 'rule_id']:
                        setattr(target_media_types, column_name, getattr(source_rule.media_types, column_name))

                session.add(target_media_types)
            else:
                # 如果已有设置，更新现有设置
                # 使用inspect自动复制所有字段（除了id和rule_id）
                media_inspector = inspect(MediaTypes)
                for column in media_inspector.columns:
                    column_name = column.key
                    if column_name not in ['id', 'rule_id']:
                        setattr(target_media_types, column_name, getattr(source_rule.media_types, column_name))

        # 复制规则同步表数据
        # 检查源规则是否有同步关系
        if hasattr(source_rule, 'rule_syncs') and source_rule.rule_syncs:
            for sync in source_rule.rule_syncs:
                # 检查是否已存在
                exists = any(s.sync_rule_id == sync.sync_rule_id for s in target_rule.rule_syncs)
                if not exists:
                    # 确保不会创建自引用的同步关系
                    if sync.sync_rule_id != target_rule.id:
                        new_sync = RuleSync(
                            rule_id=target_rule.id,
                            sync_rule_id=sync.sync_rule_id
                        )
                        session.add(new_sync)
                        rule_syncs_success += 1
                        
                        # 启用目标规则的同步功能
                        if rule_syncs_success > 0:
                            target_rule.enable_sync = True
                else:
                    rule_syncs_skip += 1
        
        # 复制规则设置
        # 保存目标规则的原始关联
        original_source_chat_id = target_rule.source_chat_id
        original_target_chat_id = target_rule.target_chat_id
        
        # 获取ForwardRule模型的所有字段
        inspector = inspect(ForwardRule)
        for column in inspector.columns:
            column_name = column.key
            if column_name not in ['id', 'source_chat_id', 'target_chat_id', 'source_chat', 'target_chat',
                                  'keywords', 'replace_rules', 'media_types']:
                # 获取源规则的值并设置到目标规则
                value = getattr(source_rule, column_name)
                setattr(target_rule, column_name, value)
                
        # 恢复目标规则的原始关联
        target_rule.source_chat_id = original_source_chat_id
        target_rule.target_chat_id = original_target_chat_id
        
        # 保存更改
        session.commit()
        
        # 构建消息内容
        result_message = (
            f"✅ 已从规则 `{source_rule_id}` 复制到规则 `{target_rule.id}`\n\n"
            f"普通关键字: 成功复制 {keywords_normal_success} 个, 跳过重复 {keywords_normal_skip} 个\n"
            f"正则关键字: 成功复制 {keywords_regex_success} 个, 跳过重复 {keywords_regex_skip} 个\n"
            f"替换规则: 成功复制 {replace_rules_success} 个, 跳过重复 {replace_rules_skip} 个\n"
            f"媒体扩展名: 成功复制 {media_extensions_success} 个, 跳过重复 {media_extensions_skip} 个\n"
            f"同步规则: 成功复制 {rule_syncs_success} 个, 跳过重复 {rule_syncs_skip} 个\n"
            f"媒体类型设置和其他规则设置已复制\n"
        )
        
        # 创建返回设置按钮
        buttons = [[
            Button.inline('👈 返回设置', f"other_settings:{source_rule.id}"),
            Button.inline('❌ 关闭', 'close_settings')
        ]]
        
        # 删除原消息
        await message.delete()
        
        # 发送新消息
        await send_message_and_delete(
            event.client,
            event.chat_id,
            result_message,
            buttons=buttons,
            parse_mode='markdown'
        )
        
        await event.answer(f"已从规则 {source_rule_id} 复制所有设置到规则 {target_rule_id}")
        
    except Exception as e:
        logger.error(f"复制规则时出错: {str(e)}")
        logger.error(f"错误详情: {traceback.format_exc()}")
        await event.answer(f"复制规则失败: {str(e)}")
    return

async def callback_copy_keyword(event, rule_id, session, message, data):
    """复制关键字
    
    显示可选择的规则列表，供用户选择要复制关键字到的目标规则。
    选择后将当前规则的关键字复制到目标规则。
    """
    try:
        # 调用通用的规则选择函数
        await show_rule_selection(
            event, rule_id, data, "请选择要将当前规则的关键字复制到的目标规则：", "perform_copy_keyword"
        )
    except Exception as e:
        logger.error(f"显示复制关键字选择界面时出错: {str(e)}")
        logger.error(f"错误详情: {traceback.format_exc()}")
        await event.answer("显示复制关键字界面失败")
    return

async def callback_copy_replace(event, rule_id, session, message, data):
    """复制替换规则
    
    显示可选择的规则列表，供用户选择要复制替换规则到的目标规则。
    选择后将当前规则的替换规则复制到目标规则。
    """
    try:
        # 调用通用的规则选择函数
        await show_rule_selection(
            event, rule_id, data, "请选择要将当前规则的替换规则复制到的目标规则：", "perform_copy_replace"
        )
    except Exception as e:
        logger.error(f"显示复制替换规则选择界面时出错: {str(e)}")
        logger.error(f"错误详情: {traceback.format_exc()}")
        await event.answer("显示复制替换规则界面失败")
    return

async def callback_perform_copy_keyword(event, rule_id_data, session, message, data):
    """执行复制关键字操作
    
    Args:
        rule_id_data: 格式为 "源规则ID:目标规则ID"
    """
    try:
        # 解析规则ID
        source_rule_id, target_rule_id = await parse_rule_ids(event, rule_id_data)
        if source_rule_id is None or target_rule_id is None:
            return
            
        # 获取源规则和目标规则
        source_rule, target_rule = await get_rules(event, session, source_rule_id, target_rule_id)
        if not source_rule or not target_rule:
            return
        
        # 记录复制的各个部分成功数量
        keywords_normal_success = 0
        keywords_normal_skip = 0
        keywords_regex_success = 0
        keywords_regex_skip = 0
        
        # 复制普通关键字
        for keyword in source_rule.keywords:
            if not keyword.is_regex:  # 普通关键字
                # 检查是否已存在
                exists = any(not k.is_regex and k.keyword == keyword.keyword and k.is_blacklist == keyword.is_blacklist
                           for k in target_rule.keywords)
                if not exists:
                    new_keyword = Keyword(
                        rule_id=target_rule.id,
                        keyword=keyword.keyword,
                        is_regex=False,
                        is_blacklist=keyword.is_blacklist
                    )
                    session.add(new_keyword)
                    keywords_normal_success += 1
                else:
                    keywords_normal_skip += 1

        # 复制正则关键字
        for keyword in source_rule.keywords:
            if keyword.is_regex:  # 正则关键字
                # 检查是否已存在
                exists = any(k.is_regex and k.keyword == keyword.keyword and k.is_blacklist == keyword.is_blacklist
                           for k in target_rule.keywords)
                if not exists:
                    new_keyword = Keyword(
                        rule_id=target_rule.id,
                        keyword=keyword.keyword,
                        is_regex=True,
                        is_blacklist=keyword.is_blacklist
                    )
                    session.add(new_keyword)
                    keywords_regex_success += 1
                else:
                    keywords_regex_skip += 1
        
        # 保存更改
        session.commit()
        
        # 构建消息内容
        result_message = (
            f"✅ 已从规则 `{source_rule_id}` 复制关键字到规则 `{target_rule.id}`\n\n"
            f"普通关键字: 成功复制 {keywords_normal_success} 个, 跳过重复 {keywords_normal_skip} 个\n"
            f"正则关键字: 成功复制 {keywords_regex_success} 个, 跳过重复 {keywords_regex_skip} 个\n"
        )
        
        # 发送结果消息
        await send_result_message(event, message, result_message, source_rule.id)
        
        await event.answer(f"已从规则 {source_rule_id} 复制关键字到规则 {target_rule_id}")
        
    except Exception as e:
        logger.error(f"复制关键字时出错: {str(e)}")
        logger.error(f"错误详情: {traceback.format_exc()}")
        await event.answer(f"复制关键字失败: {str(e)}")
    return

async def callback_perform_copy_replace(event, rule_id_data, session, message, data):
    """执行复制替换规则操作
    
    Args:
        rule_id_data: 格式为 "源规则ID:目标规则ID"
    """
    try:
        # 解析规则ID
        source_rule_id, target_rule_id = await parse_rule_ids(event, rule_id_data)
        if source_rule_id is None or target_rule_id is None:
            return
            
        # 获取源规则和目标规则
        source_rule, target_rule = await get_rules(event, session, source_rule_id, target_rule_id)
        if not source_rule or not target_rule:
            return
        
        # 记录复制的成功数量
        replace_rules_success = 0
        replace_rules_skip = 0
        
        # 复制替换规则
        for replace_rule in source_rule.replace_rules:
            # 检查是否已存在
            exists = any(r.pattern == replace_rule.pattern and r.content == replace_rule.content
                         for r in target_rule.replace_rules)
            if not exists:
                new_rule = ReplaceRule(
                    rule_id=target_rule.id,
                    pattern=replace_rule.pattern,
                    content=replace_rule.content
                )
                session.add(new_rule)
                replace_rules_success += 1
            else:
                replace_rules_skip += 1
        
        # 保存更改
        session.commit()
        
        # 构建消息内容
        result_message = (
            f"✅ 已从规则 `{source_rule_id}` 复制替换规则到规则 `{target_rule.id}`\n\n"
            f"替换规则: 成功复制 {replace_rules_success} 个, 跳过重复 {replace_rules_skip} 个\n"
        )
        
        # 发送结果消息
        await send_result_message(event, message, result_message, source_rule.id)
        
        await event.answer(f"已从规则 {source_rule_id} 复制替换规则到规则 {target_rule_id}")
        
    except Exception as e:
        logger.error(f"复制替换规则时出错: {str(e)}")
        logger.error(f"错误详情: {traceback.format_exc()}")
        await event.answer(f"复制替换规则失败: {str(e)}")
    return

# 通用辅助函数
async def show_rule_selection(event, rule_id, data, title, callback_action):
    """显示规则选择界面的通用函数
    
    Args:
        event: 事件对象
        rule_id: 当前规则ID
        data: 回调数据
        title: 显示标题
        callback_action: 选择后要执行的回调动作
    """
    # 检查是否包含page参数
    parts = data.split(':')
    page = 0
    if len(parts) > 2:
        page = int(parts[2])
    
    # 创建规则选择按钮
    buttons = await create_rule_selection_buttons(rule_id, page, callback_action)
    await event.edit(title, buttons=buttons)

async def create_rule_selection_buttons(rule_id, page=0, callback_action="perform_copy_rule"):
    """创建规则选择按钮的通用函数
    
    Args:
        rule_id: 当前规则ID
        page: 当前页码
        callback_action: 按钮点击后的回调动作
        
    Returns:
        按钮列表
    """
    # 设置分页参数
    RULES_PER_PAGE = 5  # 每页显示的规则数量
    
    buttons = []
    session = get_session()
    
    try:
        # 获取当前规则
        source_rule_id = int(rule_id)
        current_rule = session.query(ForwardRule).get(source_rule_id)
        if not current_rule:
            buttons.append([Button.inline('❌ 规则不存在', 'noop')])
            buttons.append([Button.inline('关闭', 'close_settings')])
            return buttons
        
        # 获取所有规则（除了当前规则）
        all_rules = session.query(ForwardRule).filter(
            ForwardRule.id != source_rule_id
        ).all()
        
        # 计算分页
        total_rules = len(all_rules)
        total_pages = (total_rules + RULES_PER_PAGE - 1) // RULES_PER_PAGE
        
        if total_rules == 0:
            # buttons.append([Button.inline('❌ 没有可用的规则', 'noop')])
            buttons.append([
                Button.inline('👈 返回', f"other_settings:{source_rule_id}"),
                Button.inline('❌ 关闭', 'close_settings')
            ])
            return buttons
        
        # 获取当前页的规则
        start_idx = page * RULES_PER_PAGE
        end_idx = min(start_idx + RULES_PER_PAGE, total_rules)
        current_page_rules = all_rules[start_idx:end_idx]
        
        # 创建规则按钮
        for rule in current_page_rules:
            # 获取源聊天和目标聊天名称
            source_chat = rule.source_chat
            target_chat = rule.target_chat
            
            # 创建按钮文本
            button_text = f"{rule.id} {source_chat.name}->{target_chat.name}"
            
            # 创建回调数据：callback_action:源规则ID:目标规则ID
            callback_data = f"{callback_action}:{source_rule_id}:{rule.id}"
            
            buttons.append([Button.inline(button_text, callback_data)])
        
        # 添加分页按钮
        page_buttons = []
        action_name = callback_action.replace("perform_", "")
        
        if total_pages > 1:
            # 上一页按钮
            if page > 0:
                page_buttons.append(Button.inline("⬅️", f"{action_name}:{source_rule_id}:{page-1}"))
            else:
                page_buttons.append(Button.inline("⬅️", f"noop"))
            
            # 页码指示
            page_buttons.append(Button.inline(f"{page+1}/{total_pages}", f"noop"))
            
            # 下一页按钮
            if page < total_pages - 1:
                page_buttons.append(Button.inline("➡️", f"{action_name}:{source_rule_id}:{page+1}"))
            else:
                page_buttons.append(Button.inline("➡️", f"noop"))
        
        if page_buttons:
            buttons.append(page_buttons)
        
        buttons.append([
            Button.inline('👈 返回', f"other_settings:{source_rule_id}"),
            Button.inline('❌ 关闭', 'close_settings')
        ])
    
    finally:
        session.close()
    
    return buttons

async def parse_rule_ids(event, rule_id_data):
    """解析规则ID
    
    Args:
        event: 事件对象
        rule_id_data: 格式为 "源规则ID:目标规则ID"
        
    Returns:
        (source_rule_id, target_rule_id) 或 (None, None)
    """
    parts = rule_id_data.split(':')
    if len(parts) != 2:
        await event.answer("数据格式错误")
        return None, None
        
    source_rule_id = int(parts[0])
    target_rule_id = int(parts[1])
    
    if source_rule_id == target_rule_id:
        await event.answer('不能复制到自身')
        return None, None
        
    return source_rule_id, target_rule_id

async def get_rules(event, session, source_rule_id, target_rule_id):
    """获取源规则和目标规则
    
    Args:
        event: 事件对象
        session: 数据库会话
        source_rule_id: 源规则ID
        target_rule_id: 目标规则ID
        
    Returns:
        (source_rule, target_rule) 或 (None, None)
    """
    source_rule = session.query(ForwardRule).get(source_rule_id)
    target_rule = session.query(ForwardRule).get(target_rule_id)
    
    if not source_rule or not target_rule:
        await event.answer("源规则或目标规则不存在")
        return None, None
    
    return source_rule, target_rule

async def send_result_message(event, message, result_message, target_rule_id):
    """发送结果消息
    
    Args:
        event: 事件对象
        message: 原消息对象
        result_message: 结果消息内容
        target_rule_id: 目标规则ID
    """
    # 创建返回设置按钮
    buttons = [[
        Button.inline('👈 返回设置', f"other_settings:{target_rule_id}"),
        Button.inline('❌ 关闭', 'close_settings')
    ]]
    
    # 删除原消息
    await message.delete()
    
    # 发送新消息
    await send_message_and_delete(
        event.client,
        event.chat_id,
        result_message,
        buttons=buttons,
        parse_mode='markdown'
    )

async def callback_clear_keyword(event, rule_id, session, message, data):
    """显示清空关键字规则选择界面"""
    try:
        # 检查是否包含page参数
        parts = data.split(':')
        page = 0
        if len(parts) > 2:
            page = int(parts[2])
        
        # 获取规则信息
        current_rule = session.query(ForwardRule).get(int(rule_id))
        if not current_rule:
            await event.answer("规则不存在")
            return
        
        # 创建按钮列表，首先添加当前规则
        buttons = []
        source_chat = current_rule.source_chat
        target_chat = current_rule.target_chat
        
        # 当前规则按钮
        current_button_text = f"🗑️ 清空当前规则"
        current_callback_data = f"perform_clear_keyword:{current_rule.id}"
        buttons.append([Button.inline(current_button_text, current_callback_data)])
        
        # 检查是否有其他规则
        other_rules = session.query(ForwardRule).filter(
            ForwardRule.id != current_rule.id
        ).count()
        
        if other_rules > 0:
            # 分隔符
            buttons.append([Button.inline("---------", "noop")])
            
            # 添加其他规则按钮
            other_buttons = await create_rule_selection_buttons(rule_id, page, "perform_clear_keyword")
            
            # 将所有其他规则按钮添加到buttons中
            buttons.extend(other_buttons)
        else:
            # 添加返回和关闭按钮
            buttons.append([
                Button.inline('👈 返回', f"other_settings:{current_rule.id}"),
                Button.inline('❌ 关闭', 'close_settings')
            ])
        
        await event.edit("请选择要清空关键字的规则：", buttons=buttons)
    except Exception as e:
        logger.error(f"显示清空关键字选择界面时出错: {str(e)}")
        logger.error(f"错误详情: {traceback.format_exc()}")
        await event.answer("显示清空关键字界面失败")
    return

async def callback_clear_replace(event, rule_id, session, message, data):
    """显示清空替换规则选择界面"""
    try:
        # 检查是否包含page参数
        parts = data.split(':')
        page = 0
        if len(parts) > 2:
            page = int(parts[2])
        
        # 获取规则信息
        current_rule = session.query(ForwardRule).get(int(rule_id))
        if not current_rule:
            await event.answer("规则不存在")
            return
        
        # 创建按钮列表，首先添加当前规则
        buttons = []
        source_chat = current_rule.source_chat
        target_chat = current_rule.target_chat
        
        # 当前规则按钮
        current_button_text = f"🗑️ 清空当前规则"
        current_callback_data = f"perform_clear_replace:{current_rule.id}"
        buttons.append([Button.inline(current_button_text, current_callback_data)])
        
        # 检查是否有其他规则
        other_rules = session.query(ForwardRule).filter(
            ForwardRule.id != current_rule.id
        ).count()
        
        if other_rules > 0:
            # 分隔符
            buttons.append([Button.inline("---------", "noop")])
            
            # 添加其他规则按钮
            other_buttons = await create_rule_selection_buttons(rule_id, page, "perform_clear_replace")
            
            # 将所有其他规则按钮添加到buttons中
            buttons.extend(other_buttons)
        else:
            # 添加返回和关闭按钮
            buttons.append([
                Button.inline('👈 返回', f"other_settings:{current_rule.id}"),
                Button.inline('❌ 关闭', 'close_settings')
            ])
        
        await event.edit("请选择要清空替换规则的规则：", buttons=buttons)
    except Exception as e:
        logger.error(f"显示清空替换规则选择界面时出错: {str(e)}")
        logger.error(f"错误详情: {traceback.format_exc()}")
        await event.answer("显示清空替换规则界面失败")
    return

async def callback_delete_rule(event, rule_id, session, message, data):
    """显示删除规则选择界面"""
    try:
        # 检查是否包含page参数
        parts = data.split(':')
        page = 0
        if len(parts) > 2:
            page = int(parts[2])
        
        # 获取规则信息
        current_rule = session.query(ForwardRule).get(int(rule_id))
        if not current_rule:
            await event.answer("规则不存在")
            return
        
        # 创建按钮列表，首先添加当前规则
        buttons = []
        source_chat = current_rule.source_chat
        target_chat = current_rule.target_chat
        
        # 当前规则按钮
        current_button_text = f"❌ 删除当前规则"
        current_callback_data = f"perform_delete_rule:{current_rule.id}"
        buttons.append([Button.inline(current_button_text, current_callback_data)])
        
        # 检查是否有其他规则
        other_rules = session.query(ForwardRule).filter(
            ForwardRule.id != current_rule.id
        ).count()
        
        if other_rules > 0:
            # 分隔符
            buttons.append([Button.inline("---------", "noop")])
            
            # 添加其他规则按钮
            other_buttons = await create_rule_selection_buttons(rule_id, page, "perform_delete_rule")
            
            # 将所有其他规则按钮添加到buttons中
            buttons.extend(other_buttons)
        else:
            # 添加返回和关闭按钮
            buttons.append([
                Button.inline('👈 返回', f"other_settings:{current_rule.id}"),
                Button.inline('❌ 关闭', 'close_settings')
            ])
        
        await event.edit("请选择要删除的规则：", buttons=buttons)
    except Exception as e:
        logger.error(f"显示删除规则选择界面时出错: {str(e)}")
        logger.error(f"错误详情: {traceback.format_exc()}")
        await event.answer("显示删除规则界面失败")
    return

# 执行清空关键字的回调
async def callback_perform_clear_keyword(event, rule_id_data, session, message, data):
    """执行清空关键字操作"""
    try:
        # 检查是否包含多个规则ID（格式为source_id:target_id）
        if ':' in rule_id_data:
            # 解析规则ID
            source_rule_id, target_rule_id = await parse_rule_ids(event, rule_id_data)
            if source_rule_id is None or target_rule_id is None:
                return
            
            # 使用目标规则ID
            rule_id = target_rule_id
        else:
            # 单个规则ID的情况（当前规则）
            rule_id = int(rule_id_data)
        
        # 获取规则
        rule = session.query(ForwardRule).get(rule_id)
        if not rule:
            await event.answer("规则不存在")
            return
            
        # 获取并删除所有关键字
        keyword_count = len(rule.keywords)
        
        # 删除所有关键字
        session.query(Keyword).filter(Keyword.rule_id == rule.id).delete()
        session.commit()
        
        # 构建消息内容
        result_message = f"✅ 已清空规则 `{rule.id}` 的所有关键字，共删除 {keyword_count} 个关键字"
        
        # 返回按钮指向源规则的设置页面（如果有的话）
        source_id = int(rule_id_data.split(':')[0]) if ':' in rule_id_data else rule.id
        
        # 发送结果消息
        # 创建返回设置按钮
        buttons = [[
            Button.inline('👈 返回设置', f"other_settings:{source_id}"),
            Button.inline('❌ 关闭', 'close_settings')
        ]]
        
        # 删除原消息
        await message.delete()
        
        # 发送新消息
        await send_message_and_delete(
            event.client,
            event.chat_id,
            result_message,
            buttons=buttons,
            parse_mode='markdown'
        )
        
        await event.answer(f"已清空规则 {rule.id} 的所有关键字")
        
    except Exception as e:
        logger.error(f"清空关键字时出错: {str(e)}")
        logger.error(f"错误详情: {traceback.format_exc()}")
        await event.answer(f"清空关键字失败: {str(e)}")
    return

# 执行清空替换规则的回调
async def callback_perform_clear_replace(event, rule_id_data, session, message, data):
    """执行清空替换规则操作"""
    try:
        # 检查是否包含多个规则ID（格式为source_id:target_id）
        if ':' in rule_id_data:
            # 解析规则ID
            source_rule_id, target_rule_id = await parse_rule_ids(event, rule_id_data)
            if source_rule_id is None or target_rule_id is None:
                return
            
            # 使用目标规则ID
            rule_id = target_rule_id
        else:
            # 单个规则ID的情况（当前规则）
            rule_id = int(rule_id_data)
        
        # 获取规则
        rule = session.query(ForwardRule).get(rule_id)
        if not rule:
            await event.answer("规则不存在")
            return
            
        # 获取并删除所有替换规则
        replace_count = len(rule.replace_rules)
        
        # 删除所有替换规则
        session.query(ReplaceRule).filter(ReplaceRule.rule_id == rule.id).delete()
        session.commit()
        
        # 构建消息内容
        result_message = f"✅ 已清空规则 `{rule.id}` 的所有替换规则，共删除 {replace_count} 个替换规则"
        
        # 返回按钮指向源规则的设置页面（如果有的话）
        source_id = int(rule_id_data.split(':')[0]) if ':' in rule_id_data else rule.id
        
        # 发送结果消息
        # 创建返回设置按钮
        buttons = [[
            Button.inline('👈 返回设置', f"other_settings:{source_id}"),
            Button.inline('❌ 关闭', 'close_settings')
        ]]
        
        # 删除原消息
        await message.delete()
        
        # 发送新消息
        await send_message_and_delete(
            event.client,
            event.chat_id,
            result_message,
            buttons=buttons,
            parse_mode='markdown'
        )
        
        await event.answer(f"已清空规则 {rule.id} 的所有替换规则")
        
    except Exception as e:
        logger.error(f"清空替换规则时出错: {str(e)}")
        logger.error(f"错误详情: {traceback.format_exc()}")
        await event.answer(f"清空替换规则失败: {str(e)}")
    return

# 执行删除规则的回调
async def callback_perform_delete_rule(event, rule_id_data, session, message, data):
    """执行删除规则操作"""
    try:
        # 检查是否包含多个规则ID（格式为source_id:target_id）
        if ':' in rule_id_data:
            # 解析规则ID
            source_rule_id, target_rule_id = await parse_rule_ids(event, rule_id_data)
            if source_rule_id is None or target_rule_id is None:
                return
            
            # 使用目标规则ID
            rule_id = target_rule_id
        else:
            # 单个规则ID的情况（当前规则）
            rule_id = int(rule_id_data)
        
        # 获取规则
        rule = session.query(ForwardRule).get(rule_id)
        if not rule:
            await event.answer("规则不存在")
            return
            
        # 先保存规则对象，用于后续检查聊天关联
        rule_obj = rule
        
        # 先删除替换规则
        session.query(ReplaceRule).filter(
            ReplaceRule.rule_id == rule.id
        ).delete()

        # 再删除关键字
        session.query(Keyword).filter(
            Keyword.rule_id == rule.id
        ).delete()
        
        # 删除媒体扩展名
        if hasattr(rule, 'media_extensions'):
            session.query(MediaExtensions).filter(MediaExtensions.rule_id == rule.id).delete()
        
        # 删除媒体类型
        if hasattr(rule, 'media_types'):
            session.query(MediaTypes).filter(MediaTypes.rule_id == rule.id).delete()
        
        # 删除规则同步关系
        if hasattr(rule, 'rule_syncs'):
            session.query(RuleSync).filter(RuleSync.rule_id == rule.id).delete()
            session.query(RuleSync).filter(RuleSync.sync_rule_id == rule.id).delete()

        # 删除规则
        session.delete(rule)
        
        # 提交规则删除的更改
        session.commit()
        
        # 尝试删除RSS服务中的相关数据
        try:
            rss_url = f"http://{RSS_HOST}:{RSS_PORT}/api/rule/{rule_id}"
            async with aiohttp.ClientSession() as client_session:
                async with client_session.delete(rss_url) as response:
                    if response.status == 200:
                        logger.info(f"成功删除RSS规则数据: {rule_id}")
                    else:
                        response_text = await response.text()
                        logger.warning(f"删除RSS规则数据失败 {rule_id}, 状态码: {response.status}, 响应: {response_text}")
        except Exception as rss_err:
            logger.error(f"调用RSS删除API时出错: {str(rss_err)}")
            # 不影响主要流程，继续执行
        
        # 使用通用方法检查并清理不再使用的聊天记录
        deleted_chats = await check_and_clean_chats(session, rule_obj)
        if deleted_chats > 0:
            logger.info(f"删除规则后清理了 {deleted_chats} 个未使用的聊天记录")
        
        # 构建消息内容
        result_message = f"✅ 已删除规则 `{rule.id}`"
        
        # 删除原消息
        await message.delete()
        
        # 获取源规则ID（如果有的话）
        source_id = int(rule_id_data.split(':')[0]) if ':' in rule_id_data else None
        
        # 准备按钮
        if source_id and source_id != rule.id:
            # 如果是从另一个规则删除的，提供返回原规则的按钮
            buttons = [[
                Button.inline('👈 返回设置', f"other_settings:{source_id}"),
                Button.inline('❌ 关闭', 'close_settings')
            ]]
        else:
            # 如果是删除的当前规则，只提供关闭按钮
            buttons = [[Button.inline('❌ 关闭', 'close_settings')]]
        
        # 发送结果消息
        await send_message_and_delete(
            event.client,
            event.chat_id,
            result_message,
            buttons=buttons,
            parse_mode='markdown'
        )
        
        await event.answer("规则已成功删除")
        
    except Exception as e:
        session.rollback()
        logger.error(f"删除规则时出错: {str(e)}")
        logger.error(f"错误详情: {traceback.format_exc()}")
        await event.answer(f"删除规则失败: {str(e)}")
    return

