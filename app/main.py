import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import create_tables, migrate_enums, migrate_columns, AsyncSessionLocal
from app.config import settings
from app.api import auth, markets, trades, comments, users, websockets, admin
from app.services.seed import seed_markets
from app.services.ledger_backfill import backfill_ledger
from app.services.referral import assign_codes_to_all
from app.services.market_maintenance import run_market_maintenance, get_maintenance_status

# How often the background job runs (closing-soon notices, auto-close, admin reminders).
MAINTENANCE_INTERVAL_SECONDS = 900  # 15 min


async def _maintenance_loop() -> None:
    while True:
        await asyncio.sleep(MAINTENANCE_INTERVAL_SECONDS)
        try:
            await run_market_maintenance()
        except Exception as e:  # noqa: BLE001
            print(f"[maintenance] error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    await migrate_enums()
    await migrate_columns()
    # Best-effort historical backfill — must never block startup.
    try:
        await backfill_ledger()
    except Exception as e:  # noqa: BLE001
        print(f"[startup] ledger backfill skipped: {e}")
    try:
        async with AsyncSessionLocal() as db:
            await assign_codes_to_all(db)
    except Exception as e:  # noqa: BLE001
        print(f"[startup] referral code backfill skipped: {e}")
    await seed_markets()
    # Run once at boot, then on a fixed interval in the background.
    try:
        await run_market_maintenance()
    except Exception as e:  # noqa: BLE001
        print(f"[startup] market maintenance skipped: {e}")
    task = asyncio.create_task(_maintenance_loop())
    yield
    task.cancel()


app = FastAPI(
    title="PRESAGIO API",
    description="Mercado de predicciones — LMSR pricing engine",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "https://veredikt.mx", "http://localhost:5173", "http://localhost:5174", "http://localhost:5175"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# REST routes
app.include_router(auth.router, prefix="/api")
app.include_router(markets.router, prefix="/api")
app.include_router(trades.router, prefix="/api")
app.include_router(comments.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(admin.router, prefix="/api")

# WebSocket routes (no prefix — path is /ws/...)
app.include_router(websockets.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/api/health/maintenance")
async def maintenance_health():
    """Liveness of the periodic market-maintenance job.

    `healthy` is False if it hasn't run within 2 intervals (job stalled / server
    slept). Pointing an external uptime monitor here also keeps the server awake.
    """
    st = get_maintenance_status()
    seconds_since = None
    healthy = False
    if st["ran_at"]:
        delta = (datetime.now(timezone.utc) - datetime.fromisoformat(st["ran_at"])).total_seconds()
        seconds_since = round(delta)
        healthy = delta < MAINTENANCE_INTERVAL_SECONDS * 2
    return {
        **st,
        "seconds_since_run": seconds_since,
        "interval_seconds": MAINTENANCE_INTERVAL_SECONDS,
        "healthy": healthy,
    }

@app.get("/api/debug/oauth")
async def debug_oauth():
    g_id = settings.GOOGLE_CLIENT_ID
    g_sec = settings.GOOGLE_CLIENT_SECRET
    gh_id = settings.GITHUB_CLIENT_ID
    return {
        "google_client_id_len": len(g_id),
        "google_client_id_preview": f"{g_id[:20]}...{g_id[-10:]}" if len(g_id) > 30 else g_id,
        "google_secret_len": len(g_sec),
        "google_secret_preview": f"{g_sec[:8]}...{g_sec[-4:]}" if len(g_sec) > 12 else "(empty)",
        "github_client_id": gh_id,
        "frontend_url": settings.FRONTEND_URL,
        "backend_url": settings.BACKEND_URL,
    }
