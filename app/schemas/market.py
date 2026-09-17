from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field
from app.models.market import MarketStatus, MarketCategory

# Tercer nivel del rail de Deportes (deporte → liga → tipo). Ver Market.kind.
MarketKind = Literal["partido", "accesorio"]


class PricePoint(BaseModel):
    recorded_at: datetime
    yes_price: float
    volume_snapshot: float
    outcome_key: str | None = None

    model_config = {"from_attributes": True}


class MoverPoint(BaseModel):
    recorded_at: datetime
    price: float


class MoverOut(BaseModel):
    """Un mercado en la página "Noticias": cuánto se movió en la ventana
    (`change` en puntos porcentuales; en multi, el outcome que más se movió)."""
    id: str
    question: str
    category: MarketCategory
    subcategory: str | None = None
    image_url: str | None = None
    market_type: str
    status: MarketStatus
    ends_at: datetime
    outcome_key: str | None = None
    outcome_label: str | None = None
    price: float
    price_before: float
    change: float
    volume_delta: float
    points: list[MoverPoint]


class OutcomeOut(BaseModel):
    outcome_key: str
    label: str
    price: float

    model_config = {"from_attributes": True}


class MarketBase(BaseModel):
    id: str
    question: str
    description: str
    category: MarketCategory
    subcategory: str | None = None
    resolution_criteria: str
    resolution_source_url: str | None = None
    image_url: str | None = None
    kind: str | None = None
    yes_price: float
    volume: float
    num_trades: int
    status: MarketStatus
    trending: bool
    ends_at: datetime
    # Instante del evento (partido / accesorio de partido); NULL en futuros, F1, boxeo. Ver Market.kickoff_at.
    kickoff_at: datetime | None = None
    created_at: datetime
    market_type: str = "binary"
    outcomes: list[OutcomeOut] = []

    model_config = {"from_attributes": True}


class MarketList(MarketBase):
    pass


class MarketDetail(MarketBase):
    b: float
    q_yes: float
    q_no: float
    resolved_at: datetime | None
    resolved_outcome_key: str | None = None
    # Textos largos: solo en el detalle, no en los listados (100+ filas).
    rules: str | None = None
    context: str | None = None
    auto_resolucion: dict | None = None  # receta mecánica (recetas.py); la usa agent-resolver.py
    sujeto: dict | None = None  # identidad del jugador de un accesorio (resolucion/sujeto.py)


class MarketCreate(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1, max_length=4000)
    category: MarketCategory
    subcategory: str | None = Field(default=None, max_length=50)
    resolution_criteria: str = Field(min_length=1, max_length=4000)
    resolution_source_url: str | None = Field(default=None, max_length=500)
    rules: str | None = Field(default=None, max_length=6000)
    context: str | None = Field(default=None, max_length=6000)
    image_url: str | None = Field(default=None, max_length=500)
    kind: MarketKind | None = None
    ends_at: datetime
    b: float = Field(default=3000.0, gt=0)  # LMSR liquidity; must be positive
    initial_yes_price: float = Field(default=50.0, ge=1, le=99)  # percentage


class MarketResolve(BaseModel):
    resolution: str | None = None   # "YES" or "NO" for binary markets
    outcome_key: str | None = None  # outcome key for multi-outcome markets


class MarketPatch(BaseModel):
    """Edición admin de un mercado no resuelto: reabrir un aplazado con su nueva
    fecha, corregir pregunta/descripción/criterios/fuente/normas/contexto o las
    etiquetas de los outcomes."""
    status: Literal["open"] | None = None   # solo se puede volver a abrir
    ends_at: datetime | None = None
    kickoff_at: datetime | None = None  # hora del evento; en un partido, mover ends_at la mueve sola
    question: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, min_length=1, max_length=4000)
    resolution_criteria: str | None = Field(default=None, min_length=1, max_length=4000)
    resolution_source_url: str | None = Field(default=None, max_length=500)
    rules: str | None = None
    context: str | None = None
    outcome_labels: dict[str, str] | None = None  # outcome_key → etiqueta nueva
    auto_resolucion: dict | None = None  # receta mecánica; {} la borra
    sujeto: dict | None = None  # identidad del jugador de un accesorio; {} la borra


class ResumenSubcategoria(BaseModel):
    subcategory: str
    abiertos: int
    volumen_total: float   # suma de markets.volume, todos los estatus (incluye resueltos)
    volumen_7d: float      # suma de trades.cost de los últimos 7 días


class ResumenCategoria(BaseModel):
    """Agregados de una categoría para su landing (riel de ligas, volumen por liga).
    Ver app/services/resumen.py."""
    categoria: MarketCategory
    abiertos: int
    volumen_total: float
    volumen_7d: float
    subcategorias: list[ResumenSubcategoria]
