"""GitHub OAuth 认证流程的 API endpoint。

提供登录跳转、OAuth callback、token 刷新、退出与用户资料接口，并使用 HTTP-only
cookie 管理会话，避免前端脚本直接读取认证 token。
"""

from typing import Annotated, Any

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_deps import get_current_user
from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token, verify_token
from app.db.session import get_db
from app.models.user import User
from app.repositories.user import UserRepository
from app.services.oauth import github_oauth

router = APIRouter()


def _set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
) -> None:
    """用一致的安全参数设置 access 与 refresh cookie。"""
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=False,  # 生产环境启用 HTTPS 后应设为 True。
        samesite="lax",
        max_age=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=False,  # 生产环境启用 HTTPS 后应设为 True。
        samesite="lax",
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    )


def _clear_auth_cookies(response: Response) -> None:
    """从响应中清除认证 cookie。"""
    response.delete_cookie(key="access_token")
    response.delete_cookie(key="refresh_token")


@router.get("/login/github")
async def github_login() -> RedirectResponse:
    """启动 GitHub OAuth 流程。

    把用户重定向到 GitHub 授权页；用户授权后，GitHub 再跳回 callback endpoint。
    """
    auth_url = github_oauth.get_authorization_url()
    return RedirectResponse(url=auth_url)


@router.get("/callback/github")
async def github_callback(
    code: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """处理 GitHub OAuth callback。

    接收 GitHub authorization code，换取 access token 并读取用户资料；随后创建或更新
    User、生成应用 JWT、设置安全 cookie，最后跳转 dashboard。
    """
    # 用一次性 authorization code 换取 GitHub access token。
    token_data = await github_oauth.exchange_code_for_token(code)
    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token")

    # 使用 access token 读取 GitHub 用户资料。
    user_info = await github_oauth.get_user_info(access_token)

    # 以 GitHub ID 为稳定键创建或更新本地 User。
    existing_user = await UserRepository.get_by_github_id(db, user_info["id"])

    if existing_user:
        # 已存在用户：轮换加密保存的 OAuth token。
        user = await UserRepository.update_tokens(db, existing_user, access_token, refresh_token)
    else:
        # 首次登录：创建新的 User。
        user = await UserRepository.create(
            db=db,
            github_id=user_info["id"],
            username=user_info["login"],
            email=user_info.get("email"),
            avatar_url=user_info.get("avatar_url"),
            access_token=access_token,
            refresh_token=refresh_token,
        )

    await db.commit()

    # 生成 NexusCoder 自己的 access/refresh JWT，而不是把 GitHub token 暴露给前端。
    jwt_access_token = create_access_token(data={"sub": str(user.id)})
    jwt_refresh_token = create_refresh_token(user_id=str(user.id))

    # 设置 HTTP-only cookie 后跳转 dashboard。
    response = RedirectResponse(url=f"{settings.FRONTEND_URL}/dashboard")

    _set_auth_cookies(
        response=response,
        access_token=jwt_access_token,
        refresh_token=jwt_refresh_token,
    )

    return response


@router.post("/refresh")
async def refresh_access_token(
    refresh_token: Annotated[str | None, Cookie()] = None,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """使用 refresh token 刷新 access token。

    access token 过期后，前端携带 refresh cookie 调用本接口，无需重新走 GitHub 授权。
    """
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token")

    try:
        payload = verify_token(refresh_token)

    # 明确校验 token 类型，防止把 access token 当作 refresh token 使用。
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type"
            )

        user_id_raw = payload.get("sub")
        if not user_id_raw or not isinstance(user_id_raw, str):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload"
            )

        user_id: str = user_id_raw

    # 刷新前确认用户仍存在且处于启用状态。
        user = await UserRepository.get_by_id(db, user_id)
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    # 同时轮换两类 JWT，保持会话连续并缩短 refresh token 的重放窗口。
        new_access_token = create_access_token(data={"sub": str(user.id)})
        new_refresh_token = create_refresh_token(user_id=str(user.id))

        response = Response(
            content='{"message":"Token refreshed"}',
            media_type="application/json",
        )
        _set_auth_cookies(
            response=response,
            access_token=new_access_token,
            refresh_token=new_refresh_token,
        )
        return response

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e


@router.post("/logout")
async def logout() -> Response:
    """通过清除认证 cookie 退出登录。

    同时删除 access_token 与 refresh_token cookie；前端随后应跳转首页。
    """
    response = Response(
        content='{"message": "Logged out successfully"}', media_type="application/json"
    )

    _clear_auth_cookies(response)

    return response


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    """读取当前已认证用户的资料。

    这是受保护 endpoint，需要 cookie 中的有效 JWT，并返回前端展示所需用户资料。
    """
    return {
        "id": str(current_user.id),
        "username": current_user.username,
        "email": current_user.email,
        "avatar_url": current_user.avatar_url,
        "github_id": current_user.github_id,
        "last_login_at": (
            current_user.last_login_at.isoformat() if current_user.last_login_at else None
        ),
        "is_active": current_user.is_active,
    }
