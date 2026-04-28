from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, update
from app.database import get_db
from app.models.comment import Comment
from app.models.market import Market
from app.models.user import User
from app.schemas.comment import CommentCreate, CommentOut
from app.core.auth import get_current_user
from app.core.websocket_manager import ws_manager
import asyncio

router = APIRouter(prefix="/markets", tags=["comments"])


@router.get("/{market_id}/comments", response_model=list[CommentOut])
async def list_comments(
    market_id: str,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Comment)
        .where(Comment.market_id == market_id)
        .order_by(desc(Comment.created_at))
        .limit(limit)
    )
    return result.scalars().all()


@router.post("/{market_id}/comments", response_model=CommentOut, status_code=201)
async def create_comment(
    market_id: str,
    payload: CommentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    market_exists = await db.execute(select(Market.id).where(Market.id == market_id))
    if not market_exists.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Mercado no encontrado")

    comment = Comment(
        user_id=current_user.id,
        market_id=market_id,
        text=payload.text,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    # Eagerly load user for response
    await db.refresh(comment, ["user"])

    asyncio.create_task(ws_manager.broadcast_market_update(market_id, {
        "market_id": market_id,
        "event": "new_comment",
        "comment": {
            "id": comment.id,
            "text": comment.text,
            "user": current_user.display_name,
            "avatar_url": current_user.avatar_url,
        },
    }))

    return comment


@router.post("/{market_id}/comments/{comment_id}/like", response_model=CommentOut)
async def like_comment(
    market_id: str,
    comment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Comment).where(Comment.id == comment_id, Comment.market_id == market_id)
    )
    comment = result.scalar_one_or_none()
    if not comment:
        raise HTTPException(status_code=404, detail="Comentario no encontrado")
    comment.likes += 1
    await db.commit()
    await db.refresh(comment, ["user"])
    return comment
