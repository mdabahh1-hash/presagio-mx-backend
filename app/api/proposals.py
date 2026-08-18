"""Public market proposals: anyone can suggest a market (no auth, rate-limited).

# TODO(admin): panel de aprobación/rechazo de propuestas (listar pending,
# aprobar → crear Market, rechazar). Ver app/api/admin.py.
"""
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.background import spawn
from app.database import get_db
from app.models.market_proposal import MarketProposal
from app.schemas.proposal import ProposalCreate
from app.services.email import send_proposal_notification

router = APIRouter(prefix="/proposals", tags=["proposals"])

# ── Simple in-memory rate limit: max 5 proposals per IP per hour ─────────────
# Single uvicorn instance on Railway, so process-local state is enough; it
# resets on redeploy, which is fine for a soft anti-spam guard.
_RATE_LIMIT = 5
_RATE_WINDOW = 3600.0  # seconds
_recent: dict[str, deque[float]] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    # Railway sits behind a proxy: the real client IP is the first entry of
    # X-Forwarded-For; request.client is the proxy itself.
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_rate_limit(ip: str) -> bool:
    now = time.monotonic()
    dq = _recent[ip]
    while dq and now - dq[0] > _RATE_WINDOW:
        dq.popleft()
    if len(dq) >= _RATE_LIMIT:
        return False
    dq.append(now)
    # Bound key growth from IP churn: sweep empty deques occasionally.
    if len(_recent) > 10_000:
        for key in [k for k, v in _recent.items() if not v]:
            del _recent[key]
    return True


@router.post("", status_code=201)
async def create_proposal(
    payload: ProposalCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ip = _client_ip(request)
    if not _check_rate_limit(ip):
        raise HTTPException(status_code=429, detail={"code": "PROPOSAL_RATE_LIMITED", "message": "Demasiadas propuestas. Intenta de nuevo en una hora."})

    proposal = MarketProposal(
        question=payload.question,
        category=payload.category,
        description=payload.description,
        proposer_contact=payload.proposer_contact,
    )
    db.add(proposal)
    await db.commit()
    await db.refresh(proposal)  # picks up server-side created_at / status

    # AFTER commit: the row is safe no matter what happens to the email.
    # send_proposal_notification logs failures internally and never raises.
    spawn(send_proposal_notification(
        proposal.question, proposal.category, proposal.description,
        proposal.proposer_contact, proposal.created_at,
    ))

    return {"ok": True, "message": "Gracias, revisaremos tu propuesta."}
