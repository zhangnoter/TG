import re
from urlextract import URLExtract
#传入字符串，返回字符串

#匹配前处理字符串
def pre_handle(message: str) -> str:

    # 去除 markdown 链接格式，包括带单星号和双星号的，只去除紧贴着方括号的星号
    message = re.sub(r'\[(\*{1,2})?(.+?)(\*{1,2})?\]\(.+?\)', r'\2', message)
    
    # 使用 urlextract 提取链接，删除括号内的链接及括号
    extractor = URLExtract()
    urls = extractor.find_urls(message)
    for url in urls:
        # 检查链接是否在括号内
        if f"({url})" in message:
            message = message.replace(f"({url})", "")
    
    return message
