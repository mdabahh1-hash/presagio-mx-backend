"""Contenido curado por categoría (landing de Política): datos editoriales que no se calculan.

GET /api/contenido/categorias/{categoria} — `categoria` es el VALOR del enum, igual que
`?category=` del listado (`/api/contenido/categorias/Pol%C3%ADtica`). Sin BD.
"""
from fastapi import APIRouter, HTTPException

from app.models.market import MarketCategory
from app.schemas.contenido import ContenidoCategoria
from contenido_categorias import CATEGORIAS

router = APIRouter(prefix="/contenido", tags=["contenido"])


@router.get("/categorias/{categoria}", response_model=ContenidoCategoria)
async def contenido_categoria(categoria: MarketCategory):
    data = CATEGORIAS.get(categoria.name)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "CONTENIDO_NO_ENCONTRADO", "message": f"Sin contenido curado para {categoria.value}"},
        )
    return data
