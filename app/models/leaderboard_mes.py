from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class LeaderboardMes(Base):
    """Cierre de un mes del leaderboard (`app/services/leaderboard_mensual.py`).
    pending → Mark lo revisa por correo (enlace firmado con `nonce`) → approved
    (público en /users/leaderboard/ganadores)."""
    __tablename__ = "leaderboard_meses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mes: Mapped[str] = mapped_column(String(7), unique=True, nullable=False)  # 'YYYY-MM'
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")  # pending|approved
    nonce: Mapped[str] = mapped_column(String(64), nullable=False)
    cerrado_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    correo_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    aprobado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LeaderboardMesFila(Base):
    """Un elegible del mes congelado. `rank` None = descalificado."""
    __tablename__ = "leaderboard_mes_filas"
    __table_args__ = (UniqueConstraint("mes", "user_id", name="uq_leaderboard_mes_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mes: Mapped[str] = mapped_column(String(7), ForeignKey("leaderboard_meses.mes"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    ganancia: Mapped[float] = mapped_column(Float, nullable=False)
    volumen: Mapped[float] = mapped_column(Float, nullable=False)
    n_trades: Mapped[int] = mapped_column(Integer, nullable=False)
    n_mercados: Mapped[int] = mapped_column(Integer, nullable=False)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    descalificado: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false", default=False)


class LeaderboardAviso(Base):
    """Correo de competencia ya mandado (`avisos_competencia`): uno por usuario, mes y tipo."""
    __tablename__ = "leaderboard_avisos"
    __table_args__ = (UniqueConstraint("user_id", "mes", "tipo", name="uq_leaderboard_aviso"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    mes: Mapped[str] = mapped_column(String(7), nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)  # semana-<n> | ultimos
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
