"""
密码安全工具

提供密码哈希和验证功能，使用 bcrypt 算法
"""

import hashlib
import secrets
from typing import Optional

from passlib.context import CryptContext


class PasswordHasher:
    """密码哈希处理器"""
    
    def __init__(self, rounds: int = 12):
        """
        初始化密码哈希器
        
        Args:
            rounds: bcrypt 加盐轮数，默认 12 轮
        """
        self._context = CryptContext(
            schemes=["bcrypt"],
            deprecated="auto",
            bcrypt__rounds=rounds,
        )
    
    def hash(self, password: str) -> str:
        """
        对密码进行哈希处理
        
        Args:
            password: 原始密码
            
        Returns:
            哈希后的密码字符串
        """
        return self._context.hash(password)
    
    def verify(self, password: str, hashed: str) -> bool:
        """
        验证密码是否匹配
        
        Args:
            password: 原始密码
            hashed: 哈希后的密码
            
        Returns:
            是否匹配
        """
        try:
            return self._context.verify(password, hashed)
        except Exception:
            # 处理无效的哈希格式
            return False
    
    def needs_rehash(self, hashed: str) -> bool:
        """
        检查是否需要重新哈希（例如算法升级后）
        
        Args:
            hashed: 当前哈希值
            
        Returns:
            是否需要重新哈希
        """
        return self._context.needs_update(hashed)


class TokenHasher:
    """Token 哈希处理器（用于 Refresh Token 存储）"""
    
    @staticmethod
    def hash(token: str) -> str:
        """
        对 Token 进行 SHA-256 哈希
        
        Args:
            token: 原始 Token
            
        Returns:
            哈希后的 Token
        """
        return hashlib.sha256(token.encode()).hexdigest()
    
    @staticmethod
    def verify(token: str, hashed: str) -> bool:
        """
        验证 Token 哈希
        
        Args:
            token: 原始 Token
            hashed: 哈希后的 Token
            
        Returns:
            是否匹配
        """
        return secrets.compare_digest(
            hashlib.sha256(token.encode()).hexdigest(),
            hashed
        )


def generate_secure_token(length: int = 32) -> str:
    """
    生成安全的随机 Token
    
    Args:
        length: Token 长度（字节数）
        
    Returns:
        URL 安全的 Base64 编码 Token
    """
    return secrets.token_urlsafe(length)


def validate_password_strength(password: str) -> tuple[bool, Optional[str]]:
    """
    验证密码强度
    
    Args:
        password: 待验证的密码
        
    Returns:
        (是否有效, 错误信息)
    """
    if len(password) < 8:
        return False, "密码长度至少为 8 个字符"
    
    if len(password) > 128:
        return False, "密码长度不能超过 128 个字符"
    
    has_letter = any(c.isalpha() for c in password)
    has_digit = any(c.isdigit() for c in password)
    
    if not has_letter:
        return False, "密码必须包含字母"
    
    if not has_digit:
        return False, "密码必须包含数字"
    
    return True, None


# 默认实例
password_hasher = PasswordHasher()
token_hasher = TokenHasher()
