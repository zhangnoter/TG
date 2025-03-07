from fastapi import FastAPI
from rss.app.api.endpoints import feed
from rss.app.core.config import settings

app = FastAPI(title=settings.PROJECT_NAME)

# 注册路由
app.include_router(feed.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT
    ) 