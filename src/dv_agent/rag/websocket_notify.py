"""
RAG WebSocket 通知模块

提供文档处理进度的 WebSocket 通知功能
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def notify_document_progress(
    tenant_id: str,
    document_id: str,
    stage: str,
    progress: float,
    message: str = "",
) -> bool:
    """
    发送文档处理进度通知
    
    Args:
        tenant_id: 租户ID（用户ID）
        document_id: 文档ID
        stage: 处理阶段 (parsing, chunking, embedding, indexing)
        progress: 进度 (0.0 - 1.0)
        message: 进度消息
        
    Returns:
        是否发送成功
    """
    try:
        from ..websocket.manager import ws_manager
        from ..websocket.models import DocumentProgressEvent
        
        event = DocumentProgressEvent.create(
            document_id=document_id,
            stage=stage,
            progress=progress,
            message=message,
        )
        
        # 发送给用户的所有连接
        sent = await ws_manager.send_to_user(tenant_id, event)
        
        if sent > 0:
            logger.debug(f"Sent progress notification to {sent} connections: {document_id} - {stage}")
        
        return sent > 0
        
    except Exception as e:
        logger.warning(f"Failed to send document progress notification: {e}")
        return False


async def notify_document_completed(
    tenant_id: str,
    document_id: str,
    filename: str,
    chunk_count: int,
) -> bool:
    """
    发送文档处理完成通知
    
    Args:
        tenant_id: 租户ID
        document_id: 文档ID
        filename: 文件名
        chunk_count: 文档块数量
        
    Returns:
        是否发送成功
    """
    try:
        print(f"[WS-NOTIFY] 准备发送文档完成通知:")
        print(f"[WS-NOTIFY]   - tenant_id: {tenant_id}")
        print(f"[WS-NOTIFY]   - document_id: {document_id}")
        print(f"[WS-NOTIFY]   - filename: {filename}")
        print(f"[WS-NOTIFY]   - chunk_count: {chunk_count}")
        
        from ..websocket.manager import ws_manager
        from ..websocket.models import DocumentCompletedEvent
        
        event = DocumentCompletedEvent.create(
            document_id=document_id,
            filename=filename,
            chunk_count=chunk_count,
        )
        
        print(f"[WS-NOTIFY] 调用 ws_manager.send_to_user()...")
        sent = await ws_manager.send_to_user(tenant_id, event)
        
        if sent > 0:
            print(f"[WS-NOTIFY] ✅ 成功发送到 {sent} 个连接")
            logger.info(f"Sent completion notification to {sent} connections: {document_id}")
        else:
            print(f"[WS-NOTIFY] ⚠️  没有活动的 WebSocket 连接 (sent={sent})")
            logger.warning(f"No active WebSocket connections for tenant {tenant_id}")
        
        return sent > 0
        
    except Exception as e:
        print(f"[WS-NOTIFY] ❌ 发送失败: {e}")
        logger.warning(f"Failed to send document completion notification: {e}")
        import traceback
        traceback.print_exc()
        return False


async def notify_document_error(
    tenant_id: str,
    document_id: str,
    error: str,
    stage: Optional[str] = None,
) -> bool:
    """
    发送文档处理错误通知
    
    Args:
        tenant_id: 租户ID
        document_id: 文档ID
        error: 错误信息
        stage: 出错阶段
        
    Returns:
        是否发送成功
    """
    try:
        from ..websocket.manager import ws_manager
        from ..websocket.models import DocumentErrorEvent
        
        event = DocumentErrorEvent.create(
            document_id=document_id,
            error=error,
            stage=stage,
        )
        
        sent = await ws_manager.send_to_user(tenant_id, event)
        
        if sent > 0:
            logger.info(f"Sent error notification to {sent} connections: {document_id}")
        
        return sent > 0
        
    except Exception as e:
        logger.warning(f"Failed to send document error notification: {e}")
        return False
