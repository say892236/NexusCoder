"""认证与 token 管理的安全辅助函数。

提供 JWT 生成与校验、OAuth token 对称加解密等能力。
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from cryptography.fernet import Fernet

from app.core.config import settings

# Fernet 用于 OAuth token 的应用层对称加密。
cipher_suite = Fernet(settings.ENCRYPTION_KEY.encode())


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """创建可指定过期时间的 JWT access token。

    把用户声明编码为 JWT，并使用 SECRET_KEY 与 HS256 签名。
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode.update(
        {
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "type": "access",
        }
    )

    encoded_jwt: str = jwt.encode(
        to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def create_refresh_token(user_id: str) -> str:
    """创建用于换取新 access token 的 refresh token。"""
    expire = datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
    }

    encoded_jwt: str = jwt.encode(
        to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def verify_token(token: str) -> dict[str, Any]:
    """校验并解码 JWT。

    token 无效、过期或被篡改时抛出 ValueError；成功时返回包含 user_id 与过期时间的 payload。
    """
    try:
        payload: dict[str, Any] = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except jwt.PyJWTError as e:
        raise ValueError(f"Invalid token: {e}") from e


def encrypt_token(token: str) -> str:
    """OAuth token 入库前使用 Fernet 加密。

    数据库只保存密文，降低明文 token 泄露风险。
    """
    encrypted: bytes = cipher_suite.encrypt(token.encode())
    return encrypted.decode()


def decrypt_token(encrypted_token: str) -> str:
    """解密数据库中的 OAuth token。

    仅在服务端调用 GitHub API 前恢复原始 token。
    """
    decrypted: bytes = cipher_suite.decrypt(encrypted_token.encode())
    return decrypted.decode()
