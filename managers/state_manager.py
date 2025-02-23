import logging
from typing import Dict, Tuple, Optional

logger = logging.getLogger(__name__)

class StateManager:
    def __init__(self):
        self._states: Dict[Tuple[int, int], str] = {}
        logger.info("StateManager 初始化")
    
    def set_state(self, user_id: int, chat_id: int, state: str) -> None:
        """设置用户状态"""
        key = (user_id, chat_id)
        self._states[key] = state
        logger.info(f"设置状态 - key: {key}, state: {state}")
        logger.debug(f"当前所有状态: {self._states}")  # 改为 debug 级别
    
    def get_state(self, user_id: int, chat_id: int) -> Optional[str]:
        """获取用户状态"""
        key = (user_id, chat_id)
        state = self._states.get(key)
        if state:  # 只在状态存在时记录日志
            logger.info(f"获取状态 - key: {key}, state: {state}")
        return state
    
    def clear_state(self, user_id: int, chat_id: int) -> None:
        """清除用户状态"""
        key = (user_id, chat_id)
        if key in self._states:
            del self._states[key]
            logger.info(f"清除状态 - key: {key}")
        logger.debug(f"当前所有状态: {self._states}")  # 改为 debug 级别

# 创建全局实例
state_manager = StateManager()
logger.info("StateManager 全局实例已创建")