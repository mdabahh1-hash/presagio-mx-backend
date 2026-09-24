from datetime import datetime
from sqlalchemy import JSON, String, DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class ReviewPlan(Base):
    """Plan del agente revisor (`app/services/revision`): hallazgos de los mercados
    activos, con `fix` los que el agente arregla solo al aprobarlos. Mismo esquema
    de aprobación que `SeedPlan` (nonce en el token del correo, se aplica una vez).
    """
    __tablename__ = "review_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")  # pending|applying|applied|expired
    nonce: Mapped[str] = mapped_column(String(64), nullable=False)
    plan: Mapped[dict] = mapped_column(JSON, nullable=False)
    resumen: Mapped[dict] = mapped_column(JSON, nullable=False)
    resultado: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
