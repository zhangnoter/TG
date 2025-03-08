#!/usr/bin/env python
"""
单独启动RSS Web服务的脚本
"""
import uvicorn

if __name__ == "__main__":
    print("正在启动RSS Web服务...")
    uvicorn.run("rss.main:app", host="0.0.0.0", port=8000, reload=True) 