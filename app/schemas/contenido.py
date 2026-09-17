"""Contenido curado por categoría (ver `contenido_categorias/__init__.py` para el formato)."""
from datetime import date

from pydantic import BaseModel, Field, model_validator


class Hito(BaseModel):
    fecha: date
    etiqueta: str
    texto: str
    clave: bool = False


class Cronologia(BaseModel):
    titulo: str
    subtitulo: str | None = None
    # Enlace "Fuente" de la tarjeta (calendario oficial); https.
    fuente_url: str | None = Field(default=None, pattern=r"^https://")
    hitos: list[Hito] = Field(min_length=2)


class Bloque(BaseModel):
    """Un partido de la barra: su mercado multi de rangos y los escaños representativos por opción.

    Los escaños esperados NO viven aquí: el frontend los calcula con los precios vivos
    (Σ precio × escanos_por_opcion). Las keys deben ser las outcomes del mercado.
    """
    partido: str
    mercado_id: str
    escanos_por_opcion: dict[str, int] = Field(min_length=2)


class Proyeccion(BaseModel):
    titulo: str
    total: int = Field(gt=0)
    umbral: int = Field(gt=0)
    umbral_etiqueta: str
    mercado_umbral_id: str | None = None
    bloques: list[Bloque] = Field(min_length=1)
    coalicion: list[str] = Field(min_length=1)
    nota: str | None = None

    @model_validator(mode="after")
    def _coherente(self):
        ids = [b.mercado_id for b in self.bloques]
        if len(set(ids)) != len(ids):
            raise ValueError("mercado_id repetido en bloques")
        for b in self.bloques:
            fuera = [k for k, v in b.escanos_por_opcion.items() if not 0 <= v <= self.total]
            if fuera:
                raise ValueError(f"{b.partido}: escaños fuera de 0..{self.total} en {fuera}")
        if self.umbral > self.total:
            raise ValueError(f"umbral {self.umbral} > total {self.total}")
        en_bloques = {b.partido for b in self.bloques}
        fuera = set(self.coalicion) - en_bloques
        if fuera:
            raise ValueError(f"coalición con partidos sin bloque: {sorted(fuera)}")
        return self


class Partido(BaseModel):
    clave: str
    nombre: str
    siglas: str


class Fuente(BaseModel):
    host: str
    etiqueta: str


class Hero(BaseModel):
    secundario_id: str | None = None


class ContenidoCategoria(BaseModel):
    categoria: str
    actualizado: date
    resumen: str | None = None
    hero: Hero = Hero()
    proyeccion: Proyeccion | None = None
    cronologia: Cronologia | None = None
    partidos: list[Partido] = []
    fuentes: list[Fuente] = []
    notas: dict[str, str] = {}
    # Deportes: subcategoría (liga) → id del multi de campeón de la temporada. La landing
    # pinta "Probabilidad de título" con los precios vivos de ese mercado; sin entrada, no
    # monta la tabla. Las claves se validan en tests/test_contenido_categorias.py.
    titulos: dict[str, str] = {}
