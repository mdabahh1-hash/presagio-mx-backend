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
    hitos: list[Hito] = Field(min_length=2)


class Bloque(BaseModel):
    partido: str
    escanos: int = Field(ge=0)


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
        suma = sum(b.escanos for b in self.bloques)
        if suma > self.total:
            raise ValueError(f"los bloques suman {suma} > total {self.total}")
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
