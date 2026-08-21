"""GitHub webhook 的 FastAPI endpoint。"""

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.webhook import (
    handle_other_event,
    handle_ping,
    handle_pull_request,
    verify_github_signature,
)

router = APIRouter()


@router.post("/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(None),
    x_github_event: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """接收 GitHub webhook，并把耗时处理投递为异步 task。"""
    # 签名校验必须使用未经 JSON 解析的原始请求体。
    payload = await request.body()

    # 在处理事件前验证 GitHub webhook 签名。
    if not verify_github_signature(payload, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid Webhook Signature")

    # 签名通过后再解析 JSON payload。
    data = await request.json()

    # 根据 GitHub event 类型分发到对应 handler。
    match x_github_event:
        case "ping":
            result = handle_ping()
            return JSONResponse(content=result, status_code=200)

        case "pull_request":
            result = await handle_pull_request(
                action=data["action"],
                pull_request=data["pull_request"],
                repository=data["repository"],
                installation=data["installation"],
                db=db,
            )
    # 后台任务已受理但尚未完成，因此返回 202 Accepted。
            return JSONResponse(content=result, status_code=202)

        case _:
            result = handle_other_event(x_github_event)
            return JSONResponse(content=result, status_code=200)
