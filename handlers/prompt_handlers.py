import logging
from models.models import get_session, ForwardRule
from managers.state_manager import state_manager
from utils.common import get_ai_settings_text
from handlers import bot_handler

logger = logging.getLogger(__name__)

async def handle_prompt_setting(event, client, sender_id, chat_id, current_state):
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
            
            logger.info(f"清除用户状态,用户ID:{sender_id},聊天ID:{chat_id}")
            state_manager.clear_state(sender_id, chat_id)
            
            logger.info("准备发送更新后的设置消息")
            await client.send_message(
                chat_id,
                await get_ai_settings_text(rule),
                buttons=await bot_handler.create_ai_settings_buttons(rule)
            )
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