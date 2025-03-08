from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends, Body
from fastapi.responses import Response, FileResponse
from typing import List, Optional, Dict, Any
import logging
import os
import json
from pathlib import Path
from ...services.feed_generator import FeedService
from ...models.entry import Entry
from ...core.config import settings
from ...crud.entry import get_entries, create_entry, update_entry, delete_entry
from ...core.exceptions import ValidationError
import mimetypes

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/")
async def root():
    """服务状态检查"""
    return {
        "status": "ok",
        "service": "TG Forwarder RSS"
    }

@router.get("/rss/feed/{rule_id}")
async def get_feed(rule_id: int):
    """返回规则对应的RSS Feed"""
    try:
        # 获取规则对应的条目
        entries = await get_entries(rule_id)
        
        # 如果没有条目，返回测试数据
        if not entries:
            logger.warning(f"规则 {rule_id} 没有条目数据，返回测试数据")
            fg = FeedService.generate_test_feed(rule_id)
        else:
            # 根据真实数据生成 Feed
            fg = await FeedService.generate_feed_from_entries(rule_id, entries)
        
        # 生成 RSS XML
        rss_xml = fg.rss_str(pretty=True)
        return Response(
            content=rss_xml,
            media_type="application/xml; charset=utf-8"
        )
    except Exception as e:
        logger.error(f"生成RSS feed时出错: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/media/{rule_id}/{filename}")
async def get_media(rule_id: int, filename: str):
    """返回媒体文件"""
    # 构建规则特定的媒体文件路径
    media_path = Path(settings.get_rule_media_path(rule_id)) / filename
    
    # 记录尝试访问的路径
    logger.info(f"尝试访问媒体文件: {media_path}")
    
    # 检查文件是否存在
    if not media_path.exists():
        # 文件不存在，返回404
        logger.error(f"媒体文件未找到: {filename}")
        raise HTTPException(status_code=404, detail=f"媒体文件未找到: {filename}")
    
    # 确定正确的MIME类型
    mime_type = mimetypes.guess_type(str(media_path))[0]
    if not mime_type:
        # 如果无法确定MIME类型，根据文件扩展名猜测
        ext = filename.split('.')[-1].lower() if '.' in filename else ''
        if ext in ['mp4', 'mov', 'avi', 'webm']:
            mime_type = f"video/{ext}"
        elif ext in ['mp3', 'wav', 'ogg', 'flac']:
            mime_type = f"audio/{ext}"
        elif ext in ['jpg', 'jpeg', 'png', 'gif']:
            mime_type = f"image/{ext}"
        else:
            mime_type = "application/octet-stream"
            
    logger.info(f"发送媒体文件: {filename}, MIME类型: {mime_type}")
    
    # 返回文件，并设置正确的Content-Type
    return FileResponse(
        path=media_path,
        media_type=mime_type,
        filename=filename
    )

@router.post("/api/entries/{rule_id}/add")
async def add_entry(rule_id: int, entry_data: Dict[str, Any] = Body(...)):
    """添加新的条目"""
    try:
        # 记录接收到的数据摘要
        media_count = len(entry_data.get("media", []))
        logger.info(f"接收到新条目数据: 规则ID={rule_id}, 标题='{entry_data.get('title', '无标题')}', 媒体数量={media_count}")
        
        # 验证媒体数据
        if media_count > 0:
            media_filenames = []
            for m in entry_data.get("media", []):
                if isinstance(m, dict):
                    media_filenames.append(m.get('filename', '未知'))
                else:
                    media_filenames.append(getattr(m, 'filename', '未知'))
            logger.info(f"媒体文件列表: {media_filenames}")
            
            # 确保媒体文件存在
            for media in entry_data.get("media", []):
                if isinstance(media, dict):
                    filename = media.get("filename", "")
                else:
                    filename = getattr(media, "filename", "")
                
                media_path = os.path.join(settings.MEDIA_PATH, filename)
                if not os.path.exists(media_path):
                    logger.warning(f"媒体文件不存在: {media_path}")
        
        # 确保必要的字段存在
        entry_data["rule_id"] = rule_id
        if not entry_data.get("message_id"):
            entry_data["message_id"] = entry_data.get("id", "")
        
        # 转换为Entry对象
        entry = Entry(
            rule_id=rule_id,
            message_id=entry_data.get("message_id", entry_data.get("id", "")),
            title=entry_data.get("title", "新消息"),
            content=entry_data.get("content", ""),
            published=entry_data.get("published"),
            author=entry_data.get("author", ""),
            link=entry_data.get("link", ""),
            media=entry_data.get("media", [])
        )
        
        # 添加条目
        success = await create_entry(entry)
        if success:
            return {"status": "success", "message": f"条目已添加，媒体文件数量: {media_count}"}
        else:
            logger.error("添加条目失败")
            raise HTTPException(status_code=500, detail="添加条目失败")
            
    except ValidationError as e:
        logger.error(f"验证错误: {str(e)}")
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"添加条目时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/api/entries/{rule_id}/{entry_id}")
async def delete_entry_api(rule_id: int, entry_id: str):
    """删除条目"""
    try:
        # 删除条目
        success = await delete_entry(rule_id, entry_id)
        if not success:
            raise HTTPException(status_code=404, detail="条目未找到")
        
        return {"status": "success", "message": "条目已删除"}
    except Exception as e:
        logger.error(f"删除条目时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/entries/{rule_id}")
async def list_entries(rule_id: int, limit: int = 20, offset: int = 0):
    """列出规则对应的所有条目"""
    try:
        entries = await get_entries(rule_id, limit, offset)
        return {"entries": entries, "total": len(entries), "limit": limit, "offset": offset}
    except Exception as e:
        logger.error(f"获取条目列表时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 