from telethon import Button
from utils.constants import *
from utils.settings import load_summary_times, load_ai_models
from managers.settings_manager import AI_SETTINGS, AI_MODELS

SUMMARY_TIMES = load_summary_times()
AI_MODELS= load_ai_models()

async def create_ai_settings_buttons(rule):
    """创建 AI 设置按钮"""
    buttons = []

    # 添加 AI 设置按钮
    for field, config in AI_SETTINGS.items():
        current_value = getattr(rule, field)
        if field == 'ai_prompt':
            display_value = current_value[:20] + '...' if current_value and len(current_value) > 20 else (
                        current_value or os.getenv('DEFAULT_AI_PROMPT'))
        else:
            display_value = config['values'].get(current_value, str(current_value))
        button_text = f"{config['display_name']}: {display_value}"
        callback_data = f"{config['toggle_action']}:{rule.id}"
        buttons.append([Button.inline(button_text, callback_data)])

    # 添加返回按钮
    buttons.append([Button.inline('👈 返回规则设置', f"rule_settings:{rule.id}")])

    return buttons


async def create_list_buttons(total_pages, current_page, command):
    """创建分页按钮"""
    buttons = []
    row = []

    # 上一页按钮
    if current_page > 1:
        row.append(Button.inline(
            '⬅️ 上一页',
            f'page:{current_page-1}:{command}'
        ))

    # 页码显示
    row.append(Button.inline(
        f'{current_page}/{total_pages}',
        'noop:0'  # 空操作
    ))

    # 下一页按钮
    if current_page < total_pages:
        row.append(Button.inline(
            '下一页 ➡️',
            f'page:{current_page+1}:{command}'
        ))

    buttons.append(row)
    return buttons


# 添加模型选择按钮创建函数
async def create_model_buttons(rule_id, page=0):
    """创建模型选择按钮，支持分页

    Args:
        rule_id: 规则ID
        page: 当前页码（从0开始）
    """
    buttons = []
    total_models = len(AI_MODELS)
    total_pages = (total_models + MODELS_PER_PAGE - 1) // MODELS_PER_PAGE

    # 计算当前页的模型范围
    start_idx = page * MODELS_PER_PAGE
    end_idx = min(start_idx + MODELS_PER_PAGE, total_models)

    # 添加模型按钮
    for model in AI_MODELS[start_idx:end_idx]:
        buttons.append([Button.inline(f"{model}", f"select_model:{rule_id}:{model}")])

    # 添加导航按钮
    nav_buttons = []
    if page > 0:  # 不是第一页，显示"上一页"
        nav_buttons.append(Button.inline("⬅️ 上一页", f"model_page:{rule_id}:{page - 1}"))
    # 添加页码显示在中间
    nav_buttons.append(Button.inline(f"{page + 1}/{total_pages}", f"noop:{rule_id}"))
    if page < total_pages - 1:  # 不是最后一页，显示"下一页"
        nav_buttons.append(Button.inline("下一页 ➡️", f"model_page:{rule_id}:{page + 1}"))
    if nav_buttons:
        buttons.append(nav_buttons)

    # 添加返回按钮
    buttons.append([Button.inline("返回", f"rule_settings:{rule_id}")])

    return buttons


async def create_summary_time_buttons(rule_id, page=0):
    """创建时间选择按钮"""
    # 从环境变量获取布局设置
    rows = SUMMARY_TIME_ROWS
    cols = SUMMARY_TIME_COLS
    times_per_page = rows * cols

    buttons = []
    total_times = len(SUMMARY_TIMES)
    start_idx = page * times_per_page
    end_idx = min(start_idx + times_per_page, total_times)

    # 检查是否是频道消息
    buttons = []
    total_times = len(SUMMARY_TIMES)

    # 添加时间按钮
    current_row = []
    for i, time in enumerate(SUMMARY_TIMES[start_idx:end_idx], start=1):
        current_row.append(Button.inline(
            time,
            f"select_time:{rule_id}:{time}"
        ))

        # 当达到每行的列数时，添加当前行并重置
        if i % cols == 0:
            buttons.append(current_row)
            current_row = []

    # 添加最后一个不完整的行
    if current_row:
        buttons.append(current_row)

    # 添加导航按钮
    nav_buttons = []
    if page > 0:
        nav_buttons.append(Button.inline(
            "⬅️ 上一页",
            f"time_page:{rule_id}:{page - 1}"
        ))

    nav_buttons.append(Button.inline(
        f"{page + 1}/{(total_times + times_per_page - 1) // times_per_page}",
        "noop:0"
    ))

    if end_idx < total_times:
        nav_buttons.append(Button.inline(
            "下一页 ➡️",
            f"time_page:{rule_id}:{page + 1}"
        ))

    buttons.append(nav_buttons)
    buttons.append([Button.inline("👈 返回", f"ai_settings:{rule_id}")])

    return buttons