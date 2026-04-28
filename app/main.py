from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import create_tables
from app.config import settings
from app.api import auth, markets, trades, comments, users, websockets, admin
from app.services.seed import seed_markets


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    await seed_markets()
    yield


app = FastAPI(
    title="PRESAGIO API",
    description="Mercado de predicciones — LMSR pricing engine",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL, "http://localhost:5173", "http://localhost:5174", "http://localhost:5175"],
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
