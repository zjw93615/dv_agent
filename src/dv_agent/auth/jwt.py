"""
JWT Token 管理器

提供 JWT Token 的签发和验证功能
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from jose import JWTError, jwt

from .models import TokenPayload, TokenPair, User


class JWTConfig:
    """JWT 配置"""
    
    def __init__(
        self,
        secret_key: Optional[str] = None,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 15,
        refresh_token_expire_days: int = 7,
        issuer: str = "dv-agent",
    ):
        """
        初始化 JWT 配置
        
        Args:
            secret_key: JWT 密钥（默认从环境变量获取）
            algorithm: 签名算法
            access_token_expire_minutes: Access Token 过期时间（分钟）
            refresh_token_expire_days: Refresh Token 过期时间（天）
            issuer: Token 签发者
        """
        self.secret_key = secret_key or os.getenv(
            "JWT_SECRET_KEY", 
            "dv-agent-jwt-secret-key-change-in-production"
        )
        self.algorithm = algorithm
        self.access_token_expire_minutes = access_token_expire_minutes
        self.refresh_token_expire_days = refresh_token_expire_days
        self.issuer = issuer
        
        # 验证密钥强度
        if len(self.secret_key) < 32:
            import warnings
            warnings.warn(
                "JWT_SECRET_KEY 长度小于 32 字符，建议使用更长的密钥",
                UserWarning
            )


class JWTManager:
    """JWT Token 管理器"""
    
    def __init__(self, config: Optional[JWTConfig] = None):
        """
        初始化 JWT 管理器
        
        Args:
            config: JWT 配置，默认使用默认配置
        """
        self.config = config or JWTConfig()
    
    def create_access_token(
        self,
        user: User,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """
        创建 Access Token
        
        Args:
            user: 用户对象
            expires_delta: 自定义过期时间
            
        Returns:
            JWT Access Token
        """
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(
                minutes=self.config.access_token_expire_minutes
            )
        
        payload = {
            "sub": user.id,
            "email": user.email,
            "role": user.role.value if hasattr(user.role, 'value') else user.role,
            "exp": int(expire.timestamp()),
            "iat": int(datetime.now(timezone.utc).timestamp()),
            "jti": str(uuid4()),
            "type": "access",
            "iss": self.config.issuer,
        }
        
        return jwt.encode(
            payload,
            self.config.secret_key,
            algorithm=self.config.algorithm,
        )
    
    def create_refresh_token(
        self,
        user: User,
        expires_delta: Optional[timedelta] = None,
    ) -> tuple[str, datetime]:
        """
        创建 Refresh Token
        
        Args:
            user: 用户对象
            expires_delta: 自定义过期时间
            
        Returns:
            (JWT Refresh Token, 过期时间)
        """
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(
                days=self.config.refresh_token_expire_days
            )
        
        payload = {
            "sub": user.id,
            "email": user.email,
            "role": user.role.value if hasattr(user.role, 'value') else user.role,
            "exp": int(expire.timestamp()),
            "iat": int(datetime.now(timezone.utc).timestamp()),
            "jti": str(uuid4()),
            "type": "refresh",
            "iss": self.config.issuer,
        }
        
        token = jwt.encode(
            payload,
            self.config.secret_key,
            algorithm=self.config.algorithm,
        )
        
        return token, expire
    
    def create_token_pair(self, user: User) -> TokenPair:
        """
        创建 Token 对
        
        Args:
            user: 用户对象
            
        Returns:
            TokenPair 包含 access_token 和 refresh_token
        """
        access_token = self.create_access_token(user)
        refresh_token, _ = self.create_refresh_token(user)
        
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=self.config.access_token_expire_minutes * 60,
        )
    
    def verify_token(
        self,
        token: str,
        expected_type: str = "access",
    ) -> Optional[TokenPayload]:
        """
        验证并解析 Token
        
        Args:
            token: JWT Token
            expected_type: 期望的 Token 类型
            
        Returns:
            Token 负载，验证失败返回 None
        """
        try:
            payload = jwt.decode(
                token,
                self.config.secret_key,
                algorithms=[self.config.algorithm],
                options={
                    "verify_exp": True,
                    "verify_iat": True,
                    "require_exp": True,
                    "require_iat": True,
                }
            )
            
            # 验证 Token 类型
            if payload.get("type") != expected_type:
                return None
            
            # 验证签发者
            if payload.get("iss") != self.config.issuer:
                return None
            
            return TokenPayload(
                sub=payload["sub"],
                email=payload["email"],
                role=payload.get("role", "user"),
                exp=payload["exp"],
                iat=payload["iat"],
                jti=payload.get("jti", str(uuid4())),
                type=payload.get("type", "access"),
            )
            
        except JWTError:
            return None
    
    def decode_token_unverified(self, token: str) -> Optional[dict]:
        """
        解析 Token 但不验证（用于获取过期 Token 的信息）
        
        Args:
            token: JWT Token
            
        Returns:
            Token 负载字典
        """
        try:
            return jwt.decode(
                token,
                self.config.secret_key,
                algorithms=[self.config.algorithm],
                options={
                    "verify_exp": False,
                    "verify_iat": False,
                }
            )
        except JWTError:
            return None
    
    def get_token_jti(self, token: str) -> Optional[str]:
        """
        获取 Token 的 JTI
        
        Args:
            token: JWT Token
            
        Returns:
            Token ID (jti)
        """
        payload = self.decode_token_unverified(token)
        return payload.get("jti") if payload else None
    
    def get_token_expiry(self, token: str) -> Optional[datetime]:
        """
        获取 Token 的过期时间
        
        Args:
            token: JWT Token
            
        Returns:
            过期时间
        """
        payload = self.decode_token_unverified(token)
        if payload and "exp" in payload:
            return datetime.fromtimestamp(payload["exp"])
        return None
    
    @property
    def access_token_expire_seconds(self) -> int:
        """Access Token 过期时间（秒）"""
        return self.config.access_token_expire_minutes * 60
    
    @property
    def refresh_token_expire_seconds(self) -> int:
        """Refresh Token 过期时间（秒）"""
        return self.config.refresh_token_expire_days * 24 * 60 * 60


# 默认实例
jwt_manager = JWTManager()
