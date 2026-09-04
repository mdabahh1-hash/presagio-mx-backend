"""Helpers compartidos por los módulos de contenido (Normas / Contexto / fuente).

Convenciones:
- Los textos van en español, con párrafos separados por "\n\n" (el frontend usa
  white-space: pre-line).
- Toda entrada SIN source_url debe abrir sus Normas con "Cómo se resuelve:" —
  el backfill lo verifica antes de escribir.
- Las horas se expresan en hora de la Ciudad de México (UTC-6 todo el año
  desde 2022, sin horario de verano).
"""
from datetime import datetime, timedelta, timezone

CDMX = timezone(timedelta(hours=-6))

_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def fecha_mx(iso: str, con_hora: bool = True) -> str:
    """'2026-09-05T14:15:00+00:00' → 'sábado 5 de septiembre de 2026, 8:15 h (CDMX)'."""
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(CDMX)
    s = f"{_DIAS[dt.weekday()]} {dt.day} de {_MESES[dt.month - 1]} de {dt.year}"
    if con_hora:
        s += f", {dt.hour}:{dt.minute:02d} h (CDMX)"
    return s


def entry(rules: str, context: str, source_url: str | None) -> dict:
    return {"rules": rules.strip(), "context": context.strip(), "source_url": source_url}


# ---------------------------------------------------------------------------
# Partidos de fútbol (1X2)
# ---------------------------------------------------------------------------
def partido_rules(local: str, visitante: str, competencia: str, fuente: str,
                  ventana: str, kickoff_iso: str, copa: bool = False) -> str:
    """Normas de un mercado 1X2 (local / empate / visitante)."""
    penales = (
        "Si el partido se define en prórroga o penales, para este mercado cuenta "
        "únicamente el marcador al minuto 90 más el añadido: un empate en ese "
        "momento resuelve «Empate» aunque después haya un ganador."
        if copa else
        "Prórroga y tanda de penales no aplican en este tipo de partido y, en "
        "cualquier caso, no contarían."
    )
    return f"""
El mercado se resuelve con el marcador final de {local} vs. {visitante} ({competencia}) al término de los 90 minutos reglamentarios más el tiempo añadido que indique el árbitro. Gana exactamente uno de los tres resultados: victoria de {local} (local), empate o victoria de {visitante} (visitante). {penales}

La fuente que decide es {fuente}. Si un medio reporta un marcador distinto, prevalece el acta oficial de la competencia. Sanciones administrativas posteriores (resultados anulados en mesa, alineación indebida, deducción de puntos) no modifican un mercado que ya fue resuelto con el resultado de la cancha.

Si el partido se pospone pero se juega dentro de {ventana}, el mercado sigue abierto y la fecha de cierre se recorre al nuevo horario. Si se reprograma fuera de esa ventana, se suspende sin reanudarse o se abandona sin que la competencia publique un resultado oficial, el mercado se cancela y las posiciones se reembolsan.

El mercado deja de aceptar predicciones al silbatazo inicial programado: {fecha_mx(kickoff_iso)}. Se resuelve normalmente en las horas posteriores al final del partido; cada acción del resultado ganador paga 1 PT y las demás valen 0.
"""


# ---------------------------------------------------------------------------
# Binarios genéricos
# ---------------------------------------------------------------------------
def cierre_txt(ends_iso: str, con_hora: bool = False) -> str:
    return fecha_mx(ends_iso, con_hora=con_hora)


BINARIO_PAGO = (
    "Es un mercado binario: si la condición se cumple resuelve SÍ y cada acción "
    "de SÍ paga 1 PT; en cualquier otro caso resuelve NO y paga la acción de NO."
)

def binario_rules(cuerpo: str, ends_iso: str, como: str | None = None,
                  con_hora: bool = False, anticipado: bool = True) -> str:
    """Normas de un mercado SÍ/NO.

    cuerpo: párrafos específicos (condición, exclusiones, fuente, aplazamientos).
    como:   texto para el párrafo inicial "Cómo se resuelve:" — OBLIGATORIO
            cuando el mercado no tiene resolution_source_url.
    """
    partes = []
    if como:
        partes.append(f"Cómo se resuelve: {como.strip()}")
    partes.append(cuerpo.strip())
    cierre = f"El mercado cierra el {fecha_mx(ends_iso, con_hora=con_hora)}. {BINARIO_PAGO}"
    if anticipado:
        cierre += " Si la condición se cumple antes del cierre, el mercado puede resolverse SÍ de forma anticipada."
    partes.append(cierre)
    return "\n\n".join(partes)


def multi_rules(cuerpo: str, ends_iso: str, como: str | None = None) -> str:
    partes = []
    if como:
        partes.append(f"Cómo se resuelve: {como.strip()}")
    partes.append(cuerpo.strip())
    partes.append(
        f"El mercado cierra el {fecha_mx(ends_iso, con_hora=False)}. Gana exactamente un resultado: "
        "cada acción del ganador paga 1 PT y las demás valen 0. Si el ganador real no está entre las "
        "opciones nombradas, gana «Otro»."
    )
    return "\n\n".join(partes)


FUENTE_CAIDA = (
    "Si la fuente oficial deja de publicar el dato o cambia su metodología antes "
    "de la resolución, el equipo de VEREDIKT usará la fuente sustituta más cercana "
    "y lo anunciará en los comentarios del mercado antes de resolver."
)
