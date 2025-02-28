import logging
from models.models import get_session, ForwardRule
from managers.state_manager import state_manager
from utils.common import get_ai_settings_text
from handlers import bot_handler

logger = logging.getLogger(__name__)

async def handle_prompt_setting(event, client, sender_id, chat_id, current_state):
    """处理设置提示词的逻辑"""
    if not current_state:
        return False

    rule_id = None
    field_name = None
    prompt_type = None

    if current_state.startswith("set_summary_prompt:"):
        rule_id = current_state.split(":")[1]
        field_name = "summary_prompt"
        prompt_type = "总结"
    elif current_state.startswith("set_ai_prompt:"):
        rule_id = current_state.split(":")[1]
        field_name = "ai_prompt"
        prompt_type = "AI"
    else:
        return False

    logger.info(f"处理设置{prompt_type}提示词,规则ID: {rule_id}")
    session = get_session()
    try:
        rule = session.query(ForwardRule).get(int(rule_id))
        if rule:
            setattr(rule, field_name, event.message.text)
            session.commit()
            logger.info(f"已更新规则 {rule_id} 的{prompt_type}提示词: {getattr(rule, field_name)}")
            
            state_manager.clear_state(sender_id, chat_id)
            await client.send_message(
                chat_id,
                await get_ai_settings_text(rule),
                buttons=await bot_handler.create_ai_settings_buttons(rule)
            )
            return True
        else:
            logger.warning(f"未找到规则ID: {rule_id}")
    finally:
        session.close()
    return True 