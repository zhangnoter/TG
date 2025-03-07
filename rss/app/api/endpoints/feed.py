from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
import logging
from ...services.feed_generator import FeedService

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/")
async def root():
    """服务状态检查"""
    return {
        "status": "ok",
        "service": "TG Forwarder RSS Test"
    }

@router.get("/rss/{rule_id}")
async def get_feed(rule_id: int):
    """返回测试 Feed"""
    try:
        # 生成 Feed
        fg = FeedService.generate_test_feed(rule_id)
        # 生成 RSS XML
        rss_xml = fg.rss_str(pretty=True)
        return Response(
            content=rss_xml,
            media_type="application/rss+xml; charset=utf-8"
        )
    except Exception as e:
        logger.error(f"生成RSS feed时出错: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error") 