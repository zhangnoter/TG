from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from rss.app.routes.auth import router as auth_router
from rss.app.routes.rss import router as rss_router
from rss.app.api.endpoints import feed
import uvicorn

app = FastAPI(title="TG Forwarder RSS")

# 挂载静态文件
app.mount("/static", StaticFiles(directory="rss/app/static"), name="static")

# 注册路由
app.include_router(auth_router)
app.include_router(rss_router)
app.include_router(feed.router)

# 模板配置
templates = Jinja2Templates(directory="rss/app/templates")

def run_server(host: str = "0.0.0.0", port: int = 8000):
    """运行 RSS 服务器"""
    uvicorn.run(app, host=host, port=port)

# 添加直接运行支持
if __name__ == "__main__":
    run_server() 