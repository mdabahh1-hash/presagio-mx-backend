"""Utilidades de prueba sin red para app/services/resolucion: FakeHttp (misma
interfaz que fuentes.Http: `get` JSON y `get_text` HTML) y lectura de los
fixtures recortados de tests/fixtures."""
import copy
import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_json(nombre: str):
    return json.loads((FIXTURES / nombre).read_text(encoding="utf-8"))


def fixture_texto(nombre: str) -> str:
    return (FIXTURES / nombre).read_text(encoding="utf-8")


class FakeHttp:
    """Responde por fragmento de URL (el primero, en orden de inserción, que
    aparezca en la URL); una URL sin respuesta se comporta como una fuente caída
    (RuntimeError, igual que fuentes.Http). `urls` guarda todo lo pedido."""

    def __init__(self, json_map: dict | None = None, text_map: dict | None = None):
        self.json_map = json_map or {}
        self.text_map = text_map or {}
        self.urls: list[str] = []

    def _responder(self, mapa: dict, url: str):
        self.urls.append(url)
        for fragmento, respuesta in mapa.items():
            if fragmento in url:
                return copy.deepcopy(respuesta)
        raise RuntimeError(f"GET {url} falló: HTTP Error 404 (FakeHttp sin respuesta)")

    def get(self, url: str):
        return self._responder(self.json_map, url)

    def get_text(self, url: str) -> str:
        return self._responder(self.text_map, url)
