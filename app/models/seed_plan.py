from datetime import datetime
from sqlalchemy import JSON, String, DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class SeedPlan(Base):
    """Plan de siembra armado por el agente (`app/services/siembra`).

    `plan` guarda las propuestas (doc YAML del sembrador + evidencia) y los
    descartes con su motivo; `resultado` lo que pasó al aprobarlo (insertados,
    existentes, vencidos, desmarcados). Mismo esquema de aprobación que
    `ResolutionPlan`: el `nonce` viaja en el token del correo y el plan se aplica
    una sola vez. Tabla aparte para no mezclarse con el job de resolución.
    """
    __tablename__ = "seed_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")  # pending|applying|applied|expired
    nonce: Mapped[str] = mapped_column(String(64), nullable=False)
    plan: Mapped[dict] = mapped_column(JSON, nullable=False)
    resumen: Mapped[dict] = mapped_column(JSON, nullable=False)
    resultado: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
