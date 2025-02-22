from handlers.button_helpers import *

async def show_list(event, command, items, formatter, title, page=1):
    """显示分页列表"""

    # KEYWORDS_PER_PAGE
    PAGE_SIZE = KEYWORDS_PER_PAGE
    total_items = len(items)
    total_pages = (total_items + PAGE_SIZE - 1) // PAGE_SIZE

    if not items:
        try:
            return await event.edit(f'没有找到任何{title}')
        except:
            return await event.reply(f'没有找到任何{title}')

    # 获取当前页的项目
    start = (page - 1) * PAGE_SIZE
    end = min(start + PAGE_SIZE, total_items)
    current_items = items[start:end]

    # 格式化列表项
    item_list = [formatter(i + start + 1, item) for i, item in enumerate(current_items)]

    # 创建分页按钮
    buttons = await create_list_buttons(total_pages, page, command)

    # 构建消息文本
    text = f'{title}\n{chr(10).join(item_list)}'
    if len(text) > 4096:  # Telegram消息长度限制
        text = text[:4093] + '...'

    try:
        return await event.edit(text, buttons=buttons)
    except:
        return await event.reply(text, buttons=buttons)

