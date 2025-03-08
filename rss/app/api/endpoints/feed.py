from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends, Body, Request
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
from models.models import get_session, RSSConfig
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter()

# 添加本地访问验证依赖
async def verify_local_access(request: Request):
    """验证请求是否来自本地或Docker内部网络"""
    client_host = request.client.host if request.client else None
    
    # 允许的本地IP地址列表
    local_addresses = ['127.0.0.1', '::1', 'localhost', '0.0.0.0']
    
    # 如果设置了 HOST 环境变量，也将其添加到允许列表中
    if hasattr(settings, 'HOST') and settings.HOST:
        local_addresses.append(settings.HOST)
    
    # 检查是否是Docker内部网络IP (常见的私有网络范围)
    docker_ip = False
    if client_host:
        docker_prefixes = ['172.', '192.168.', '10.']
        docker_ip = any(client_host.startswith(prefix) for prefix in docker_prefixes)
    
    # 如果是本地地址或Docker内部网络IP，允许访问
    if client_host in local_addresses or docker_ip:
        logger.debug(f"已验证访问权限: {client_host}")
        return True
    
    # 拒绝来自外部网络的访问
    logger.warning(f"拒绝来自外部网络的访问: {client_host}")
    raise HTTPException(
        status_code=403, 
        detail="此API端点仅允许本地或内部网络访问"
    )

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
    session = None
    try:
        # 创建数据库会话
        session = get_session()
        
        # 查询规则配置
        rss_config = session.query(RSSConfig).filter(RSSConfig.rule_id == rule_id).first()
        if not rss_config or not rss_config.enable_rss:
            logger.warning(f"规则 {rule_id} 的RSS未启用或不存在")
            raise HTTPException(status_code=404, detail="RSS feed 未启用或不存在")
        
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"生成RSS feed时出错: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        # 确保会话被关闭
        if session:
            session.close()

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

@router.post("/api/entries/{rule_id}/add", dependencies=[Depends(verify_local_access)])
async def add_entry(rule_id: int, entry_data: Dict[str, Any] = Body(...)):
    """添加新的条目 (仅限本地访问)"""
    try:
        # 记录接收到的数据摘要
        media_count = len(entry_data.get("media", []))
        has_context = "context" in entry_data and entry_data["context"] is not None
        logger.info(f"接收到新条目数据: 规则ID={rule_id}, 标题='{entry_data.get('title', '无标题')}', 媒体数量={media_count}, 包含上下文={has_context}")
        
        # 获取 RSS 配置信息，确定最大条目数量
        session = get_session()
        max_items = None
        try:
            rss_config = session.query(RSSConfig).filter(RSSConfig.rule_id == rule_id).first()
            max_items = rss_config.max_items
        finally:
            session.close()
        
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
        
        # 记录上下文信息
        if has_context:
            logger.info(f"条目包含原始上下文对象，属性: {', '.join(entry_data['context'].keys()) if hasattr(entry_data['context'], 'keys') else '无法获取属性'}")
        
        # 确保必要的字段存在
        entry_data["rule_id"] = rule_id
        if not entry_data.get("message_id"):
            entry_data["message_id"] = entry_data.get("id", "")
        
        # 检查当前条目数量，如果接近限制则删除最旧的条目
        current_entries = await get_entries(rule_id)
        if len(current_entries) >= max_items - 1:
            # 计算需要删除的条目数量，确保添加新条目后总数不超过最大限制
            to_delete_count = len(current_entries) - (max_items - 1)
            if to_delete_count > 0:
                logger.info(f"当前条目数量({len(current_entries)})将超过限制({max_items})，需要删除 {to_delete_count} 个最早的条目")
                
                # 对条目按发布时间排序（从早到晚）
                sorted_entries = sorted(current_entries, key=lambda e: datetime.fromisoformat(e.published) if hasattr(e, 'published') else datetime.now())
                
                # 获取要删除的条目
                entries_to_delete = sorted_entries[:to_delete_count]
                
                # 删除多余条目
                for entry in entries_to_delete:
                    try:
                        # 删除条目前先处理其媒体文件
                        if hasattr(entry, 'media') and entry.media:
                            logger.info(f"条目 {entry.id} 包含 {len(entry.media)} 个媒体文件，将一并删除")
                            
                            # 删除媒体文件
                            media_dir = Path(settings.get_rule_media_path(rule_id))
                            for media in entry.media:
                                if hasattr(media, 'filename'):
                                    media_path = media_dir / media.filename
                                    if media_path.exists():
                                        try:
                                            os.remove(media_path)
                                            logger.info(f"已删除媒体文件: {media_path}")
                                        except Exception as e:
                                            logger.error(f"删除媒体文件失败: {media_path}, 错误: {str(e)}")
                        
                        # 删除条目
                        success = await delete_entry(rule_id, entry.id)
                        if success:
                            logger.info(f"已删除条目: {entry.id}")
                        else:
                            logger.warning(f"删除条目失败: {entry.id}")
                    except Exception as e:
                        logger.error(f"处理过期条目时出错: {str(e)}")
        
        # 转换为Entry对象
        entry = Entry(
            rule_id=rule_id,
            message_id=entry_data.get("message_id", entry_data.get("id", "")),
            title=entry_data.get("title", "新消息"),
            content=entry_data.get("content", ""),
            published=entry_data.get("published"),
            author=entry_data.get("author", ""),
            link=entry_data.get("link", ""),
            media=entry_data.get("media", []),
            context=entry_data.get("context")
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

@router.delete("/api/entries/{rule_id}/{entry_id}", dependencies=[Depends(verify_local_access)])
async def delete_entry_api(rule_id: int, entry_id: str):
    """删除条目 (仅限本地访问)"""
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

@router.delete("/api/rule/{rule_id}", dependencies=[Depends(verify_local_access)])
async def delete_rule_data(rule_id: int):
    """删除规则相关的所有数据和媒体文件 (仅限本地访问)"""
    try:
        import shutil
        import time
        import os
        import subprocess
        import platform
        
        # 获取规则的数据目录和媒体目录
        data_path = Path(settings.get_rule_data_path(rule_id))
        media_path = Path(settings.get_rule_media_path(rule_id))
        
        deleted_files = 0
        deleted_dirs = 0
        failed_paths = []
        
        # 辅助函数：强制删除目录
        def force_delete_directory(dir_path):
            if not dir_path.exists():
                return True, "目录不存在"
                
            # 方法1: 使用 shutil.rmtree
            try:
                shutil.rmtree(dir_path, ignore_errors=True)
                if not dir_path.exists():
                    return True, "使用 shutil.rmtree 成功删除"
            except Exception as e:
                pass
                
            # 方法2: 使用系统命令
            try:
                system = platform.system()
                if system == "Windows":
                    # Windows: 使用 rd /s /q
                    subprocess.run(["rd", "/s", "/q", str(dir_path)], 
                                  shell=True, 
                                  stderr=subprocess.PIPE, 
                                  stdout=subprocess.PIPE)
                else:
                    # Linux/Mac: 使用 rm -rf
                    subprocess.run(["rm", "-rf", str(dir_path)], 
                                  stderr=subprocess.PIPE, 
                                  stdout=subprocess.PIPE)
                    
                if not dir_path.exists():
                    return True, "使用系统命令成功删除"
            except Exception as e:
                pass
                
            # 方法3: 重命名后删除
            try:
                temp_path = dir_path.parent / f"temp_delete_{time.time()}"
                os.rename(dir_path, temp_path)
                shutil.rmtree(temp_path, ignore_errors=True)
                if not dir_path.exists() and not temp_path.exists():
                    return True, "使用重命名后删除成功"
            except Exception as e:
                pass
            
            return False, "所有删除方法都失败"
        
        # 删除媒体目录
        if media_path.exists():
            logger.info(f"开始删除媒体目录: {media_path}")
            success, method = force_delete_directory(media_path)
            if success:
                deleted_dirs += 1
                logger.info(f"已删除媒体目录: {media_path} - {method}")
            else:
                logger.error(f"无法删除媒体目录: {media_path} - {method}")
                failed_paths.append(str(media_path))
        
        # 删除数据目录
        if data_path.exists():
            logger.info(f"开始删除数据目录: {data_path}")
            success, method = force_delete_directory(data_path)
            if success:
                deleted_dirs += 1
                logger.info(f"已删除数据目录: {data_path} - {method}")
            else:
                logger.error(f"无法删除数据目录: {data_path} - {method}")
                failed_paths.append(str(data_path))
        
        # 验证删除结果
        remaining_paths = []
        if media_path.exists():
            remaining_paths.append(str(media_path))
        if data_path.exists():
            remaining_paths.append(str(data_path))
        
        # 返回删除结果
        status = "success" if not remaining_paths else "failed"
        return {
            "status": status,
            "message": f"处理规则 {rule_id} 的数据{'失败，目录仍然存在' if remaining_paths else '成功，目录已删除'}",
            "details": {
                "data_path": str(data_path),
                "media_path": str(media_path),
                "deleted_files": deleted_files,
                "deleted_dirs": deleted_dirs,
                "failed_paths": failed_paths,
                "remaining_paths": remaining_paths,
                "data_dir_exists": data_path.exists(),
                "media_dir_exists": media_path.exists()
            }
        }
    except Exception as e:
        logger.error(f"删除规则数据时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除规则数据时出错: {str(e)}") 