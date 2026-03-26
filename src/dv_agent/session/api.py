"""
Session API 路由

提供会话管理的 REST API 端点
"""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..auth.dependencies import CurrentActiveUser
from ..auth.models import User
from ..config.exceptions import SessionNotFoundError, SessionExpiredError
from .manager import SessionManager
from .models import Session, SessionState

router = APIRouter(prefix="/api/v1/sessions", tags=["Sessions"])

# 全局 SessionManager（需要在应用启动时设置）
_session_manager: Optional[SessionManager] = None


def set_session_manager(manager: SessionManager) -> None:
    """设置 SessionManager 实例"""
    global _session_manager
    _session_manager = manager


async def get_session_manager() -> SessionManager:
    """获取 SessionManager 实例"""
    if _session_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Session manager not available",
        )
    return _session_manager


# ===== 请求/响应模型 =====

class SessionCreateRequest(BaseModel):
    """创建会话请求"""
    title: Optional[str] = Field(None, max_length=200, description="会话标题")
    metadata: Optional[dict] = Field(None, description="自定义元数据")


class SessionResponse(BaseModel):
    """会话响应"""
    session_id: str = Field(..., description="会话 ID")
    user_id: Optional[str] = Field(None, description="用户 ID")
    title: Optional[str] = Field(None, description="会话标题")
    state: str = Field(..., description="会话状态")
    message_count: int = Field(0, description="消息数量")
    created_at: str = Field(..., description="创建时间")
    updated_at: str = Field(..., description="更新时间")
    last_active_at: str = Field(..., description="最后活跃时间")
    
    @classmethod
    def from_session(cls, session: Session) -> "SessionResponse":
        return cls(
            session_id=session.session_id,
            user_id=session.user_id,
            title=session.title,
            state=session.state.value if hasattr(session.state, 'value') else session.state,
            message_count=session.history.message_count,
            created_at=session.created_at.isoformat(),
            updated_at=session.updated_at.isoformat(),
            last_active_at=session.last_active_at.isoformat(),
        )


class SessionListResponse(BaseModel):
    """会话列表响应"""
    sessions: list[SessionResponse] = Field(..., description="会话列表")
    total: int = Field(..., description="总数量")


class SessionUpdateRequest(BaseModel):
    """更新会话请求"""
    title: Optional[str] = Field(None, max_length=200, description="新标题")
    metadata: Optional[dict] = Field(None, description="新元数据")


# ===== 会话归属验证 =====

async def verify_session_ownership(
    session_id: str,
    current_user: User,
    session_manager: SessionManager,
) -> Session:
    """
    验证会话归属权
    
    确保用户只能访问自己的会话
    """
    try:
        session = await session_manager.get_session(session_id, touch=False)
    except SessionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    except SessionExpiredError:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Session has expired",
        )
    
    # 验证归属权
    if session.user_id and session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this session",
        )
    
    return session


# ===== API 端点 =====

@router.get(
    "",
    response_model=SessionListResponse,
    summary="列出用户会话",
    description="获取当前用户的所有会话列表",
)
async def list_sessions(
    current_user: CurrentActiveUser,
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
    active_only: bool = True,
):
    """
    列出当前用户的所有会话
    
    - **active_only**: 是否只返回活跃会话（默认 True）
    
    返回按最后活跃时间倒序排列的会话列表
    """
    sessions = await session_manager.get_user_sessions(
        user_id=current_user.id,
        active_only=active_only,
    )
    
    return SessionListResponse(
        sessions=[SessionResponse.from_session(s) for s in sessions],
        total=len(sessions),
    )


@router.post(
    "",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建新会话",
    description="为当前用户创建一个新的会话",
)
async def create_session(
    current_user: CurrentActiveUser,
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
    request: Optional[SessionCreateRequest] = None,
):
    """
    创建新会话
    
    - **title**: 可选的会话标题
    - **metadata**: 可选的自定义元数据
    """
    session = await session_manager.create_session(
        user_id=current_user.id,
        title=request.title if request else None,
        metadata=request.metadata if request else None,
    )
    
    return SessionResponse.from_session(session)


@router.get(
    "/{session_id}",
    response_model=SessionResponse,
    summary="获取会话详情",
    description="获取指定会话的详细信息",
)
async def get_session(
    session_id: str,
    current_user: CurrentActiveUser,
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
):
    """
    获取会话详情
    
    只能获取属于当前用户的会话
    """
    session = await verify_session_ownership(
        session_id, current_user, session_manager
    )
    
    return SessionResponse.from_session(session)


@router.put(
    "/{session_id}",
    response_model=SessionResponse,
    summary="更新会话",
    description="更新会话的标题或元数据",
)
async def update_session(
    session_id: str,
    request: SessionUpdateRequest,
    current_user: CurrentActiveUser,
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
):
    """
    更新会话
    
    可以更新标题和元数据
    """
    session = await verify_session_ownership(
        session_id, current_user, session_manager
    )
    
    if request.title is not None:
        session.title = request.title
    
    if request.metadata is not None:
        session.metadata.update(request.metadata)
    
    await session_manager.update_session(session)
    
    return SessionResponse.from_session(session)


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除会话",
    description="删除指定会话",
)
async def delete_session(
    session_id: str,
    current_user: CurrentActiveUser,
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
):
    """
    删除会话
    
    会同时删除会话的所有消息和上下文
    """
    await verify_session_ownership(session_id, current_user, session_manager)
    await session_manager.delete_session(session_id)


@router.post(
    "/{session_id}/pause",
    response_model=SessionResponse,
    summary="暂停会话",
    description="暂停会话，可以稍后恢复",
)
async def pause_session(
    session_id: str,
    current_user: CurrentActiveUser,
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
):
    """暂停会话"""
    session = await verify_session_ownership(
        session_id, current_user, session_manager
    )
    
    await session_manager.pause_session(session_id)
    session = await session_manager.get_session(session_id, touch=False)
    
    return SessionResponse.from_session(session)


@router.post(
    "/{session_id}/resume",
    response_model=SessionResponse,
    summary="恢复会话",
    description="恢复之前暂停的会话",
)
async def resume_session(
    session_id: str,
    current_user: CurrentActiveUser,
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
):
    """恢复会话"""
    await verify_session_ownership(session_id, current_user, session_manager)
    
    try:
        session = await session_manager.resume_session(session_id)
    except SessionExpiredError:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Session cannot be resumed (expired)",
        )
    
    return SessionResponse.from_session(session)


@router.get(
    "/resumable",
    response_model=list[dict],
    summary="获取可恢复会话",
    description="获取有未完成任务的会话列表",
)
async def get_resumable_sessions(
    current_user: CurrentActiveUser,
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
):
    """
    获取可恢复的会话
    
    返回有未完成任务的会话列表，包含恢复上下文
    """
    return await session_manager.get_resumable_sessions(current_user.id)


# ===== 消息相关模型 =====

class MessageRequest(BaseModel):
    """发送消息请求"""
    content: str = Field(..., min_length=1, max_length=100000, description="消息内容")
    role: str = Field(default="user", description="消息角色")


class MessageResponse(BaseModel):
    """消息响应"""
    id: str = Field(..., description="消息 ID")
    session_id: str = Field(..., description="会话 ID")
    role: str = Field(..., description="消息角色")
    content: str = Field(..., description="消息内容")
    created_at: str = Field(..., description="创建时间")
    metadata: Optional[dict] = Field(None, description="元数据")


class MessageListResponse(BaseModel):
    """消息列表响应"""
    messages: list[MessageResponse] = Field(..., description="消息列表")
    total: int = Field(..., description="总数量")


# ===== 消息端点 =====

@router.get(
    "/{session_id}/messages",
    response_model=MessageListResponse,
    summary="获取会话消息",
    description="获取指定会话的消息历史",
)
async def get_session_messages(
    session_id: str,
    current_user: CurrentActiveUser,
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
    limit: int = 50,
    offset: int = 0,
):
    """
    获取会话消息历史
    
    支持分页，返回消息列表
    """
    session = await verify_session_ownership(
        session_id, current_user, session_manager
    )
    
    # 获取消息历史
    all_messages = session.history.messages
    total = len(all_messages)
    
    # 分页
    paginated = all_messages[offset:offset + limit]
    
    # 转换为响应格式
    from .models import MessageType
    
    messages = []
    for i, msg in enumerate(paginated, start=offset):
        # 从 metadata 获取 id，或生成一个
        msg_id = msg.metadata.get("id") if hasattr(msg, 'metadata') and msg.metadata else f"{session_id}_{i}"
        
        # 从 type 字段转换为 role
        if hasattr(msg, 'type'):
            if msg.type == MessageType.USER:
                role = "user"
            elif msg.type == MessageType.ASSISTANT:
                role = "assistant"
            elif msg.type == MessageType.SYSTEM:
                role = "system"
            else:
                role = "user"
        else:
            role = "user"
        
        # 获取内容
        content = msg.content if hasattr(msg, 'content') else str(msg)
        
        # 获取时间戳
        created_at = msg.timestamp.isoformat() if hasattr(msg, 'timestamp') else session.created_at.isoformat()
        
        messages.append(MessageResponse(
            id=msg_id,
            session_id=session_id,
            role=role,
            content=content,
            created_at=created_at,
            metadata=msg.metadata if hasattr(msg, 'metadata') else None,
        ))
    
    return MessageListResponse(messages=messages, total=total)


@router.post(
    "/{session_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="发送消息",
    description="向会话发送新消息",
)
async def send_message(
    session_id: str,
    request: MessageRequest,
    current_user: CurrentActiveUser,
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
    background_tasks: "BackgroundTasks" = None,
):
    """
    发送消息到会话
    
    消息会被添加到会话历史中，然后异步触发 LLM 响应
    """
    from datetime import datetime, timezone
    from fastapi import BackgroundTasks
    import uuid
    
    session = await verify_session_ownership(
        session_id, current_user, session_manager
    )
    
    # 创建消息
    message_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    
    # 添加到会话历史
    from .models import ConversationMessage, MessageType
    
    # 确定消息类型
    msg_type = MessageType.USER if request.role == "user" else MessageType.ASSISTANT
    
    message = ConversationMessage(
        type=msg_type,
        content=request.content,
        timestamp=now,
        metadata={"id": message_id},
    )
    session.history.add_message(message)
    
    # 保存会话
    await session_manager.update_session(session)
    
    # 如果是用户消息，异步触发 LLM 响应
    if request.role == "user":
        import asyncio
        asyncio.create_task(
            generate_llm_response(
                session_id=session_id,
                user_id=current_user.id,
                user_message=request.content,
                session_manager=session_manager,
            )
        )
    
    return MessageResponse(
        id=message_id,
        session_id=session_id,
        role=request.role,
        content=request.content,
        created_at=now.isoformat(),
        metadata=None,
    )


async def generate_llm_response(
    session_id: str,
    user_id: str,
    user_message: str,
    session_manager: SessionManager,
):
    """
    异步生成 LLM 响应并通过 WebSocket 推送
    """
    import uuid
    import logging
    from datetime import datetime, timezone
    from .models import ConversationMessage, MessageType
    
    logger = logging.getLogger(__name__)
    
    try:
        # 导入 WebSocket 管理器
        from ..websocket.manager import ws_manager
        from ..websocket.models import WSMessage
        
        # 发送 "正在思考" 状态
        await ws_manager.send_to_user(
            user_id,
            WSMessage(
                type="agent.thinking",
                session_id=session_id,
                data={
                    "status": "thinking",
                }
            )
        )
        
        # 尝试调用 LLM
        response_content = ""
        try:
            import os
            from ..llm_gateway import LLMGateway
            from ..llm_gateway.openai_adapter import OpenAIAdapter
            from ..llm_gateway.models import LLMRequest, Message, MessageRole, ProviderConfig
            
            # 从环境变量读取配置
            api_key = os.getenv("OPENAI_API_KEY")
            base_url = os.getenv("LLM_OPENAI_BASE_URL", "https://api.openai.com/v1")
            model = os.getenv("LLM_OPENAI_MODEL", "gpt-4o")
            
            if not api_key:
                raise ValueError("OPENAI_API_KEY not set")
            
            # 创建 provider 配置
            provider_config = ProviderConfig(
                type="openai",
                api_key=api_key,
                base_url=base_url,
                model=model,
            )
            
            # 创建 adapter 并初始化
            adapter = OpenAIAdapter(provider_config)
            await adapter.initialize()
            
            # 创建 gateway 并添加 provider
            gateway = LLMGateway(default_provider="openai")
            gateway.add_provider("openai", adapter)
            
            # 构建聊天请求
            llm_request = LLMRequest(
                messages=[
                    Message(role=MessageRole.USER, content=user_message)
                ],
                stream=True,
                model=model,
            )
            
            # 流式生成响应
            async for chunk in gateway.stream(llm_request):
                if chunk.content:
                    response_content += chunk.content
                    # 推送流式内容
                    await ws_manager.send_to_user(
                        user_id,
                        WSMessage(
                            type="agent.stream",
                            session_id=session_id,
                            data={
                                "content": chunk.content,
                                "done": False,
                            }
                        )
                    )
            
        except Exception as llm_error:
            logger.warning(f"LLM call failed: {llm_error}, using fallback response")
            # LLM 不可用时的备用响应
            response_content = f"收到您的消息：「{user_message}」\n\n（LLM 服务暂时不可用，请稍后再试）"
        
        # 保存助手响应到会话
        try:
            session = await session_manager.get_session(session_id, touch=True)
            assistant_message = ConversationMessage(
                type=MessageType.ASSISTANT,
                content=response_content,
                timestamp=datetime.now(timezone.utc),
                metadata={"id": str(uuid.uuid4())},
            )
            session.history.add_message(assistant_message)
            await session_manager.update_session(session)
        except Exception as save_error:
            logger.error(f"Failed to save assistant response: {save_error}")
        
        # 发送完成信号
        await ws_manager.send_to_user(
            user_id,
            WSMessage(
                type="agent.response",
                session_id=session_id,
                data={
                    "content": response_content,
                    "done": True,
                }
            )
        )
        
    except Exception as e:
        logger.error(f"Error generating LLM response: {e}")
        # 发送错误消息
        try:
            await ws_manager.send_to_user(
                user_id,
                WSMessage(
                    type="agent.error",
                    session_id=session_id,
                    data={
                        "error": str(e),
                    }
                )
            )
        except:
            pass


@router.delete(
    "/{session_id}/messages/{message_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除消息",
    description="删除指定消息",
)
async def delete_message(
    session_id: str,
    message_id: str,
    current_user: CurrentActiveUser,
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
):
    """
    删除会话中的指定消息
    """
    session = await verify_session_ownership(
        session_id, current_user, session_manager
    )
    
    # 从历史中删除消息
    original_count = len(session.history.messages)
    session.history.messages = [
        msg for msg in session.history.messages 
        if not (hasattr(msg, 'id') and msg.id == message_id)
    ]
    
    if len(session.history.messages) == original_count:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )
    
    # 保存会话
    await session_manager.update_session(session)
