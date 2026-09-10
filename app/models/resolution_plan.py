from datetime import datetime
from sqlalchemy import JSON, String, DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class ResolutionPlan(Base):
    """Plan de resoluciones armado por el job nocturno (`app/services/resolucion`).

    `plan` guarda las resoluciones propuestas (doble fuente) y los escalados;
    `resultado` lo que pasó al aplicarlo. El `nonce` viaja dentro del token de
    aprobación del correo: un plan solo se aplica una vez.
    """
    __tablename__ = "resolution_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")  # pending|applied|partial|expired
    nonce: Mapped[str] = mapped_column(String(64), nullable=False)
    plan: Mapped[dict] = mapped_column(JSON, nullable=False)
    resumen: Mapped[dict] = mapped_column(JSON, nullable=False)
    resultado: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
