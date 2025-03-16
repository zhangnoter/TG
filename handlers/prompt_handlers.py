import logging
from models.models import get_session, ForwardRule, RuleSync
from managers.state_manager import state_manager
from utils.common import get_ai_settings_text
from handlers import bot_handler
from utils.auto_delete import async_delete_user_message
from utils.common import get_bot_client
from utils.common import get_main_module
logger = logging.getLogger(__name__)

async def handle_prompt_setting(event, client, sender_id, chat_id, current_state, message):
    """处理设置提示词的逻辑"""
    logger.info(f"开始处理提示词设置,用户ID:{sender_id},聊天ID:{chat_id},当前状态:{current_state}")
    
    if not current_state:
        logger.info("当前无状态,返回False")
        return False

    rule_id = None
    field_name = None 
    prompt_type = None

    if current_state.startswith("set_summary_prompt:"):
        rule_id = current_state.split(":")[1]
        field_name = "summary_prompt"
        prompt_type = "总结"
        logger.info(f"检测到设置总结提示词,规则ID:{rule_id}")
    elif current_state.startswith("set_ai_prompt:"):
        rule_id = current_state.split(":")[1]
        field_name = "ai_prompt"
        prompt_type = "AI"
        logger.info(f"检测到设置AI提示词,规则ID:{rule_id}")
    else:
        logger.info(f"未知的状态类型:{current_state}")
        return False

    logger.info(f"处理设置{prompt_type}提示词,规则ID:{rule_id},字段名:{field_name}")
    session = get_session()
    try:
        logger.info(f"查询规则ID:{rule_id}")
        rule = session.query(ForwardRule).get(int(rule_id))
        if rule:
            old_prompt = getattr(rule, field_name)
            new_prompt = event.message.text
            logger.info(f"找到规则,原提示词:{old_prompt}")
            logger.info(f"准备更新为新提示词:{new_prompt}")
            
            setattr(rule, field_name, new_prompt)
            session.commit()
            logger.info(f"已更新规则{rule_id}的{prompt_type}提示词")

            # 检查是否启用了同步功能
            if rule.enable_sync:
                logger.info(f"规则 {rule.id} 启用了同步功能，正在同步提示词设置到关联规则")
                # 获取需要同步的规则列表
                sync_rules = session.query(RuleSync).filter(RuleSync.rule_id == rule.id).all()
                
                # 为每个同步规则应用相同的提示词设置
                for sync_rule in sync_rules:
                    sync_rule_id = sync_rule.sync_rule_id
                    logger.info(f"正在同步{prompt_type}提示词到规则 {sync_rule_id}")
                    
                    # 获取同步目标规则
                    target_rule = session.query(ForwardRule).get(sync_rule_id)
                    if not target_rule:
                        logger.warning(f"同步目标规则 {sync_rule_id} 不存在，跳过")
                        continue
                    
                    # 更新同步目标规则的提示词设置
                    try:
                        # 记录旧提示词
                        old_target_prompt = getattr(target_rule, field_name)
                        
                        # 设置新提示词
                        setattr(target_rule, field_name, new_prompt)
                        
                        logger.info(f"同步规则 {sync_rule_id} 的{prompt_type}提示词从 '{old_target_prompt}' 到 '{new_prompt}'")
                    except Exception as e:
                        logger.error(f"同步{prompt_type}提示词到规则 {sync_rule_id} 时出错: {str(e)}")
                        continue
                
                # 提交所有同步更改
                session.commit()
                logger.info("所有同步提示词更改已提交")
            
            logger.info(f"清除用户状态,用户ID:{sender_id},聊天ID:{chat_id}")
            state_manager.clear_state(sender_id, chat_id)
            
            
            message_chat_id = event.message.chat_id
            bot_client = await get_bot_client()
            
            
            try:
                await async_delete_user_message(bot_client, message_chat_id, event.message.id, 0)
            except Exception as e:
                logger.error(f"删除用户消息失败: {str(e)}")

            await message.delete()
            logger.info("准备发送更新后的设置消息")
            await client.send_message(
                chat_id,
                await get_ai_settings_text(rule),
                buttons=await bot_handler.create_ai_settings_buttons(rule)
            )
            
            # 删除用户消息
            logger.info("设置消息发送成功")
            return True
        else:
            logger.warning(f"未找到规则ID:{rule_id}")
    except Exception as e:
        logger.error(f"处理提示词设置时发生错误:{str(e)}")
        raise
    finally:
        session.close()
        logger.info("数据库会话已关闭")
    return True