"""
Auth 模块 - 用户认证服务

提供：
- 用户注册和登录
- JWT Token 签发和验证
- 密码安全处理
- 用户数据存储

使用示例:
    from dv_agent.auth import AuthService
    
    auth = AuthService()
    user = await auth.register("user@example.com", "password123")
    tokens = await auth.login("user@example.com", "password123")
"""

from .models import User, UserCreate, UserResponse, TokenPair, TokenPayload
from .security import PasswordHasher
from .jwt import JWTManager
from .repository import UserRepository
from .service import AuthService
from .router import router as auth_router
from .dependencies import get_current_user, get_current_active_user

__all__ = [
    # Models
    "User",
    "UserCreate",
    "UserResponse",
    "TokenPair",
    "TokenPayload",
    # Services
    "AuthService",
    "UserRepository",
    "PasswordHasher",
    "JWTManager",
    # Router
    "auth_router",
    # Dependencies
    "get_current_user",
    "get_current_active_user",
]
