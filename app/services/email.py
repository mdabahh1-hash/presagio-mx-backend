import logging
from datetime import datetime, timezone, timedelta
from html import escape as _esc

import httpx

from app.config import settings
from app.services.resolucion.sujeto import texto_identidad  # puro (sin BD ni red)

logger = logging.getLogger(__name__)

_FROM = "VEREDIKT <noreply@veredikt.mx>"
_SITE = "https://veredikt.mx"
_ADMIN_EMAIL = "mdabahh@atid.edu.mx"

# Mexico time (UTC−6, no DST since 2022) for human-readable dates in emails.
_MX_TZ = timezone(timedelta(hours=-6))
_MX_MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def _fmt_mx(dt: datetime) -> str:
    """e.g. '28 jun, 13:00 (CDMX)'."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    d = dt.astimezone(_MX_TZ)
    return f"{d.day} {_MX_MONTHS[d.month - 1]}, {d:%H:%M} (CDMX)"


async def _send(to_email: str, subject: str, html: str, text: str | None = None) -> None:
    """Low-level send via Resend. No-op (logged) if no API key configured.
    `text` (opcional) es la versión texto plano del mismo correo."""
    if not settings.RESEND_API_KEY:
        logger.info(f"[DEV] Email a {to_email}: {subject}")
        return
    payload: dict = {"from": _FROM, "to": [to_email], "subject": subject, "html": html}
    if text:
        payload["text"] = text
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                json=payload,
                timeout=15,
            )
            if not resp.is_success:
                logger.error(f"Resend error {resp.status_code}: {resp.text}")
            else:
                logger.info(f"Email enviado a {to_email} — id: {resp.json().get('id')}")
    except Exception as e:
        logger.error(f"Error enviando email a {to_email}: {e}")


def _wrap(body_html: str) -> str:
    """Branded Noche/gold email shell."""
    return f"""
    <div style="font-family: -apple-system, sans-serif; max-width: 480px; margin: 0 auto;
                background: #07071A; color: #F5F0E8; padding: 40px 32px; border-radius: 16px;">
      <div style="font-size: 28px; font-weight: 900; letter-spacing: 0.12em;
                  color: #FFD700; margin-bottom: 28px;">VEREDIKT</div>
      {body_html}
    </div>
    """


# ---------------------------------------------------------------------------
# Correos de usuario (marca v2, tema claro). Espejo de los tokens light de
# veredikt-mx/src/index.css (`html[data-theme='light']`): hex sólidos porque
# los clientes de correo no entienden rgba ni variables CSS. Un solo botón
# dorado por correo; verde/rojo solo para Acierto/Fallo y PT; sin emoji.
# `_wrap` (arriba) es el shell viejo y sigue en uso SOLO en los correos al admin.
# ---------------------------------------------------------------------------
_FONT = "'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
_C = {
    "fondo": "#F7F7F5",    # --bg-surface
    "tarjeta": "#FFFFFF",  # --bg-card
    "suave": "#F2F2EF",    # --bg-elevated
    "borde": "#E6E6E4",    # --border-subtle sobre blanco
    "texto": "#111111",    # --text-primary
    "texto2": "#616161",   # --text-secondary
    "texto3": "#808080",   # --text-tertiary
    "oro": "#E6B422",      # --accent-fill (light): solo el CTA
    "verde": "#0F8A4B",    # --green (light)
    "rojo": "#D11F3D",     # --red (light)
}
_LOGO_URL = f"{_SITE}/logo.png"
_PERFIL_URL = f"{_SITE}/#/perfil"


def _asunto(prefijo: str, pregunta: str, limite: int = 70) -> str:
    q = pregunta if len(pregunta) <= limite else pregunta[: limite - 1].rstrip() + "…"
    return f"{prefijo}: {q}"


def _p(texto_html: str, *, color: str | None = None, size: int = 14, margin: str = "0 0 16px") -> str:
    return (f'<p style="margin:{margin};font-family:{_FONT};font-size:{size}px;line-height:1.5;'
            f'color:{color or _C["texto2"]};">{texto_html}</p>')


def _valor(texto: str, color: str | None = None) -> str:
    return f'<span style="color:{color or _C["texto"]};">{_esc(texto)}</span>'


def _bloque_mercado(pregunta: str, filas: list[tuple[str, str]]) -> str:
    """Pregunta del mercado sobre fondo suave y, debajo, filas planas
    label/valor separadas por hairline (como `.list-row` en el sitio)."""
    tr = "".join(
        f'<tr>'
        f'<td style="padding:11px 0;border-bottom:1px solid {_C["borde"]};font-family:{_FONT};font-size:12px;'
        f'font-weight:500;color:{_C["texto3"]};">{_esc(label)}</td>'
        f'<td align="right" style="padding:11px 0;border-bottom:1px solid {_C["borde"]};font-family:{_FONT};'
        f'font-size:14px;font-weight:600;color:{_C["texto"]};font-variant-numeric:tabular-nums;">{valor_html}</td>'
        f'</tr>'
        for label, valor_html in filas
    )
    filas_html = (f'<tr><td style="padding:4px 0 0;"><table role="presentation" width="100%" cellpadding="0" '
                  f'cellspacing="0" border="0">{tr}</table></td></tr>') if tr else ""
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 20px;">'
        f'<tr><td style="background:{_C["suave"]};border-radius:12px;padding:14px 16px;font-family:{_FONT};'
        f'font-size:15px;font-weight:500;line-height:1.4;color:{_C["texto"]};">{_esc(pregunta)}</td></tr>'
        f'{filas_html}</table>'
    )


def _boton(texto: str, url: str) -> str:
    """CTA primario (el único oro del correo) + enlace de texto de respaldo."""
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 10px;">'
        f'<tr><td style="background:{_C["oro"]};border-radius:8px;">'
        f'<a href="{_esc(url)}" style="display:inline-block;padding:13px 22px;font-family:{_FONT};font-size:14px;'
        f'font-weight:600;line-height:18px;color:{_C["texto"]};text-decoration:none;">{_esc(texto)}</a>'
        f'</td></tr></table>'
        f'<p style="margin:0;font-family:{_FONT};font-size:12px;line-height:1.5;color:{_C["texto3"]};word-break:break-all;">'
        f'O abre este enlace: <a href="{_esc(url)}" style="color:{_C["texto2"]};text-decoration:underline;">{_esc(url)}</a></p>'
    )


def _pie_notificaciones(motivo: str) -> str:
    return (f'{_esc(motivo)} Puedes desactivar estas notificaciones en '
            f'<a href="{_PERFIL_URL}" style="color:{_C["texto3"]};text-decoration:underline;">tu perfil</a>.')


def _shell_usuario(titulo: str, preheader: str, cuerpo_html: str, pie_html: str) -> str:
    """Documento HTML completo: tabla centrada de 520px, header con logo y
    wordmark (texto vivo, nunca dorado), tarjeta con el cuerpo y pie."""
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<meta name="supported-color-schemes" content="light">
<title>{_esc(titulo)}</title>
</head>
<body style="margin:0;padding:0;background:{_C["fondo"]};">
<div style="display:none;max-height:0;overflow:hidden;font-size:1px;line-height:1px;color:{_C["fondo"]};">{_esc(preheader)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{_C["fondo"]};">
<tr><td align="center" style="padding:32px 16px;">
<table role="presentation" width="520" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:520px;">
<tr><td style="padding:0 4px 18px;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
<td style="padding-right:9px;"><img src="{_LOGO_URL}" width="27" height="24" alt="" style="display:block;border:0;"></td>
<td style="font-family:{_FONT};font-size:17px;font-weight:700;letter-spacing:0.04em;line-height:1;color:{_C["texto"]};">VEREDIKT</td>
</tr></table>
</td></tr>
<tr><td style="background:{_C["tarjeta"]};border:1px solid {_C["borde"]};border-radius:12px;padding:28px 28px 26px;">
<h1 style="margin:0 0 16px;font-family:{_FONT};font-size:20px;font-weight:600;line-height:1.3;color:{_C["texto"]};">{_esc(titulo)}</h1>
{cuerpo_html}
</td></tr>
<tr><td style="padding:18px 4px 0;font-family:{_FONT};font-size:12px;line-height:1.5;color:{_C["texto3"]};">
<p style="margin:0 0 6px;">VEREDIKT · El veredicto del mercado.</p>
<p style="margin:0;">{pie_html}</p>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""


def _texto_plano(titulo: str, lineas: list[str], url: str | None = None, pie: str | None = None) -> str:
    """Versión texto plano (Resend la manda como alternativa multipart)."""
    partes = ["VEREDIKT", "", titulo, ""] + list(lineas)
    if url:
        partes += ["", url]
    if pie:
        partes += ["", pie]
    return "\n".join(partes) + "\n"


_PIE_TEXTO = f"Puedes desactivar estas notificaciones en {_PERFIL_URL}"


async def send_verification_email(to_email: str, display_name: str, code: str) -> None:
    titulo = "Tu código de verificación"
    aviso = "Vence en 15 minutos. Si no creaste una cuenta en VEREDIKT, ignora este correo."
    cuerpo = (
        _p(f"Hola {_esc(display_name)},")
        + _p("Usa este código para confirmar tu correo.")
        + f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 20px;">'
          f'<tr><td align="center" style="background:{_C["suave"]};border-radius:12px;padding:22px 16px;font-family:{_FONT};'
          f'font-size:32px;font-weight:700;letter-spacing:6px;line-height:1;color:{_C["texto"]};'
          f'font-variant-numeric:tabular-nums;">{_esc(code)}</td></tr></table>'
        + _p(aviso, size=13, margin="0")
    )
    html = _shell_usuario(titulo, f"{code} es tu código. Vence en 15 minutos.", cuerpo,
                          "Correo automático, no respondas a este mensaje.")
    text = _texto_plano(titulo, [f"Hola {display_name},", "", f"Tu código: {code}", "", aviso])
    await _send(to_email, f"{code} es tu código de verificación VEREDIKT", html, text)


async def send_market_cancelled_email(to_email: str, display_name: str, question: str, refund: float) -> None:
    """Aviso a quien tenía posición en un mercado cancelado: se le devolvió lo que pagó."""
    titulo = "Mercado cancelado"
    url = f"{_SITE}/#/mercados"
    devuelto = f"+{round(refund)} PT"
    motivo = "Un mercado en el que participabas se canceló por evento aplazado, jugador inactivo o sin resultado válido."
    detalle = "Te devolvimos lo que pagaste por tus acciones. No cuenta como acierto ni como fallo."
    cuerpo = (
        _p(f"Hola {_esc(display_name)},")
        + _p(motivo)
        + _bloque_mercado(question, [("Devuelto", _valor(devuelto, _C["verde"]))])
        + _p(detalle)
        + _boton("Ver mercados", url)
    )
    html = _shell_usuario(titulo, f"Te devolvimos {devuelto}. {question}", cuerpo,
                          _pie_notificaciones("Recibes este correo porque participaste en este mercado."))
    text = _texto_plano(titulo, [f"Hola {display_name},", "", question, f"Devuelto: {devuelto}", "", motivo, detalle],
                        url, _PIE_TEXTO)
    await _send(to_email, _asunto("Mercado cancelado", question), html, text)


async def send_resolution_email(
    to_email: str, display_name: str, question: str, won: bool, payout: float, market_id: str | None = None
) -> None:
    """Notify a position holder that a market they traded resolved."""
    url = f"{_SITE}/#/mercado/{market_id}" if market_id else f"{_SITE}/#/mercados"
    puntos = f"+{round(payout)} PT" if won else "0 PT"
    if won:
        titulo, prefijo, resultado = "Acertaste", "Acertaste", "Acierto"
        filas = [("Resultado", _valor(resultado, _C["verde"])), ("Puntos", _valor(puntos, _C["verde"]))]
        detalle = "Cada acción ganadora pagó 1 PT. Los puntos ya están en tu cuenta."
        preheader = f"Acierto, {puntos}. {question}"
    else:
        titulo, prefijo, resultado = "Este mercado se resolvió", "Se resolvió", "Fallo"
        filas = [("Resultado", _valor(resultado, _C["rojo"])), ("Puntos", _valor(puntos))]
        detalle = "Esta vez no acertaste. Tu posición se liquidó en 0 PT."
        preheader = f"Fallo. {question}"
    cuerpo = (
        _p(f"Hola {_esc(display_name)},")
        + _p("El mercado en el que participaste ya tiene veredicto.")
        + _bloque_mercado(question, filas)
        + _p(detalle)
        + _boton("Ver mercado", url)
    )
    html = _shell_usuario(titulo, preheader, cuerpo,
                          _pie_notificaciones("Recibes este correo porque participaste en este mercado."))
    text = _texto_plano(titulo, [f"Hola {display_name},", "", question, f"Resultado: {resultado}", f"Puntos: {puntos}", "", detalle],
                        url, _PIE_TEXTO)
    await _send(to_email, _asunto(prefijo, question), html, text)


async def send_closing_soon_email(
    to_email: str, display_name: str, question: str, ends_at: datetime, market_id: str
) -> None:
    """Heads-up to an open-position holder that their market closes within ~24h."""
    titulo = "Tu mercado cierra pronto"
    url = f"{_SITE}/#/mercado/{market_id}"
    cierre = _fmt_mx(ends_at)
    detalle = "Tienes una posición abierta. Si quieres ajustarla, hazlo antes del cierre; después ya no se puede operar."
    cuerpo = (
        _p(f"Hola {_esc(display_name)},")
        + _p("Un mercado en el que tienes posición está por cerrar.")
        + _bloque_mercado(question, [("Cierra", _valor(cierre))])
        + _p(detalle)
        + _boton("Ver mercado", url)
    )
    html = _shell_usuario(titulo, f"Cierra el {cierre}. {question}", cuerpo,
                          _pie_notificaciones("Recibes este correo porque tienes una posición abierta en este mercado."))
    text = _texto_plano(titulo, [f"Hola {display_name},", "", question, f"Cierra: {cierre}", "", detalle], url, _PIE_TEXTO)
    await _send(to_email, _asunto("Cierra pronto", question), html, text)


async def send_admin_resolution_reminder(markets: list[tuple[str, str, datetime]]) -> None:
    """Digest to the admin listing markets that closed and need resolution.

    `markets` is a list of (market_id, question, ends_at).
    """
    if not markets:
        return
    rows = "".join(
        f"""
        <div style="background: rgba(255,255,255,0.04); border: 1px solid rgba(255,215,0,0.18);
                    border-radius: 10px; padding: 14px 16px; margin-bottom: 10px;">
          <div style="font-size: 14px; font-weight: 700; color: #F5F0E8; margin-bottom: 4px;">{_esc(question)}</div>
          <div style="font-size: 12px; color: rgba(245,240,232,0.55);">Cerró el {_fmt_mx(ends_at)} · <span style="font-family:'Courier New',monospace">{_esc(market_id)}</span></div>
        </div>
        """
        for market_id, question, ends_at in markets
    )
    n = len(markets)
    plural = "mercado" if n == 1 else "mercados"
    body = f"""
      <p style="margin: 0 0 8px; font-size: 16px; color: #F5F0E8;">🔔 {n} {plural} por resolver</p>
      <p style="margin: 0 0 18px; font-size: 14px; color: rgba(245,240,232,0.6);">
        Estos mercados cerraron y están pendientes de resolución:
      </p>
      {rows}
      <a href="{_SITE}/#/admin" style="display:inline-block; background:#FFD700; color:#07071A;
         text-decoration:none; font-weight:800; font-size:14px; padding:12px 24px; border-radius:10px; margin-top:8px;">
        Ir al panel de admin →
      </a>
    """
    await _send(_ADMIN_EMAIL, f"🔔 {n} {plural} por resolver en VEREDIKT", _wrap(body))


async def send_resolution_plan_email(
    plan_id: int, plan: dict, resumen: dict, url_aprobar: str, auto_resultado: dict | None = None,
    origen: str = "nocturno",
) -> None:
    """Plan de resolución al admin: tabla de resoluciones con evidencia, botón de
    aprobación (enlace firmado, un solo uso) y lista de escalados. Con
    `auto_resultado` (auto-aprobación de 1X2) el correo es un reporte sin botón.
    `origen="agente"` distingue en el asunto los planes propuestos por el CLI."""
    res = sorted(plan.get("resoluciones", []), key=lambda x: (x.get("liga") or "", x["id"]))
    esc = plan.get("escalados", [])
    n, con_ops, vol = resumen.get("resoluciones", len(res)), resumen.get("con_operaciones", 0), resumen.get("volumen", 0)

    def identidad(e: dict) -> str:
        # accesorios de jugador: quién quedó confirmado y con qué id en cada fuente
        t = texto_identidad(e.get("sujeto_confirmado"))
        return f'<br><span style="color:rgba(245,240,232,0.55)">Identidad: {_esc(t)}</span>' if t else ""

    def fila(r: dict) -> str:
        warn = f' <span style="color:#FFD700">⚠️ {round(float(r.get("volume") or 0))} PT</span>' if (r.get("num_trades") or 0) else ""
        return (
            f'<tr><td style="padding:6px 4px;border-bottom:1px solid rgba(255,255,255,0.08);font-size:12px;color:rgba(245,240,232,0.55)">{_esc(r.get("liga") or "")}</td>'
            f'<td style="padding:6px 4px;border-bottom:1px solid rgba(255,255,255,0.08);font-size:12px">{_esc(r.get("pregunta") or r["id"])}{warn}</td>'
            f'<td style="padding:6px 4px;border-bottom:1px solid rgba(255,255,255,0.08);font-size:12px;font-weight:700">{_esc(str(r.get("veredicto")))}</td>'
            f'<td style="padding:6px 4px;border-bottom:1px solid rgba(255,255,255,0.08);font-size:12px">{_esc(r.get("resultado") or "")} '
            f'<a href="{_esc(r.get("fuente_1") or "#")}" style="color:#8AB4FF">F1</a> <a href="{_esc(r.get("fuente_2") or "#")}" style="color:#8AB4FF">F2</a>{identidad(r)}</td></tr>'
        )

    tabla = ('<table style="width:100%;border-collapse:collapse;margin:0 0 18px">' + "".join(fila(r) for r in res) + "</table>") if res else \
        ('<p style="font-size:13px;color:rgba(245,240,232,0.6)">Ningún mercado quedó con marcador confirmado en dos fuentes, '
         'así que <b>no hay nada que aprobar</b> y este correo no lleva botón. Los escalados de abajo se cierran a mano en /admin.</p>')

    def item(e: dict) -> str:
        sug = f' · sugerido: <b>{_esc(str(e["veredicto_sugerido"]))}</b>' if e.get("veredicto_sugerido") else ""
        ev = f' <a href="{_esc(e["fuente_1"])}" style="color:#8AB4FF">evidencia</a>' if e.get("fuente_1") else ""
        ev += f' · <a href="{_esc(e["fuente_2"])}" style="color:#8AB4FF">evidencia 2</a>' if e.get("fuente_2") else ""
        res = f'<br><span style="color:rgba(245,240,232,0.7)">{_esc(str(e["resultado"])[:300])}</span>' if e.get("resultado") else ""
        citas = "".join(f'<br><i style="color:rgba(245,240,232,0.5)">“{_esc(str(c)[:200])}”</i>' for c in (e.get("citas") or [])[:3])
        warn = f' <span style="color:#FFD700">⚠️ {e.get("volume")} PT</span>' if (e.get("num_trades") or 0) else ""
        return (f'<li style="margin-bottom:8px;font-size:12px"><b>{_esc(e.get("pregunta") or e["id"])}</b>{warn}<br>'
                f'<span style="color:rgba(245,240,232,0.55)">{_esc(e.get("razon") or "")}{sug}{ev}</span>{res}{identidad(e)}{citas}</li>')

    sin_receta = resumen.get("sin_receta") or 0
    aviso_skill = (f'<p style="margin:12px 0 0;font-size:12px;color:#FFD700">{sin_receta} no deportivos sin receta: '
                   f'pídele a Claude Code correr la skill <b>resolver-no-deportivos</b>.</p>') if sin_receta else ""
    escalados = (f'<p style="margin:18px 0 6px;font-size:14px;font-weight:700">Escalados ({len(esc)}) — ciérralos en <a href="{_SITE}/#/admin" style="color:#8AB4FF">/admin</a></p>'
                 f'<ul style="padding-left:18px;margin:0">{"".join(item(e) for e in esc)}</ul>{aviso_skill}') if esc else ""

    if auto_resultado is not None:
        r_ok, r_f = auto_resultado.get("resueltos", []), auto_resultado.get("fallidos", [])
        fallos = "".join(f'<li style="font-size:12px;color:#FF2D55">{_esc(x["id"])}: {_esc(x.get("razon") or "")}</li>' for x in r_f)
        boton = (f'<p style="margin:0 0 18px;font-size:13px;color:#00FF88"><b>✅ Resueltos automáticamente: {len(r_ok)}</b> '
                 f'(1X2 con marcador coincidente en ESPN y TheSportsDB) · posiciones liquidadas {auto_resultado.get("posiciones_liquidadas", 0)}'
                 f'{f" · fallidos {len(r_f)}" if r_f else ""}</p>{f"<ul>{fallos}</ul>" if fallos else ""}')
        titulo = f"✅ Resueltos solos {len(r_ok)} mercados ({con_ops} con operaciones, {vol} PT)"
    else:
        boton = (f'<a href="{_esc(url_aprobar)}" style="display:inline-block; background:#FFD700; color:#07071A; text-decoration:none; '
                 f'font-weight:800; font-size:14px; padding:12px 24px; border-radius:10px; margin:0 0 18px;">Revisar y aprobar {n} resoluciones →</a>'
                 f'<p style="margin:0 0 18px;font-size:11px;color:rgba(245,240,232,0.35)">El enlace abre una página de confirmación y vence en {settings.PLAN_APPROVAL_TTL_HOURS} h.</p>') if res else ""
        quien = "Plan del agente" if origen == "agente" else "Plan de resolución"
        titulo = f"🧾 {quien}: {n} mercados listos ({con_ops} con operaciones, {vol} PT)" if res else f"🧾 {quien}: 0 listos, {len(esc)} escalados"

    body = f"""
      <p style="margin: 0 0 8px; font-size: 16px; color: #F5F0E8;">🧾 Plan de resolución #{plan_id}{" · propuesto por el agente" if origen == "agente" else ""}</p>
      <p style="margin: 0 0 18px; font-size: 14px; color: rgba(245,240,232,0.6);">
        {n} mercados con marcador confirmado en dos fuentes · {con_ops} con operaciones · {vol} PT · {len(esc)} escalados
      </p>
      {boton}
      {tabla}
      {escalados}
    """
    subject = titulo
    await _send(_ADMIN_EMAIL, subject, _wrap(body).replace("max-width: 480px", "max-width: 720px"))


async def send_resolution_plan_applied_email(plan_id: int, resultado: dict) -> None:
    r, s, f = resultado.get("resueltos", []), resultado.get("saltados", []), resultado.get("fallidos", [])
    fallos = "".join(f'<li style="font-size:12px;color:#FF2D55">{_esc(x["id"])}: {_esc(x.get("razon") or "")}</li>' for x in f)
    # accesorios de jugador resueltos: con qué identidad (ids por fuente) se liquidaron
    con_sujeto = "".join(
        f'<li style="font-size:12px">{_esc(x["id"])} → <b>{_esc(str(x.get("veredicto")))}</b><br>'
        f'<span style="color:rgba(245,240,232,0.55)">Identidad: {_esc(texto_identidad(x["sujeto_confirmado"]))}</span></li>'
        for x in r if texto_identidad(x.get("sujeto_confirmado"))
    )
    body = f"""
      <p style="margin: 0 0 8px; font-size: 16px; color: #F5F0E8;">✅ Plan #{plan_id} aplicado</p>
      <p style="margin: 0 0 18px; font-size: 14px; color: rgba(245,240,232,0.6);">
        Resueltos {len(r)} · saltados {len(s)} · fallidos {len(f)} · posiciones liquidadas {resultado.get("posiciones_liquidadas", 0)}
      </p>
      {f'<ul style="padding-left:18px">{con_sujeto}</ul>' if con_sujeto else ''}
      {f'<ul style="padding-left:18px">{fallos}</ul>' if fallos else ''}
      <a href="{_SITE}/#/admin" style="display:inline-block; background:#FFD700; color:#07071A;
         text-decoration:none; font-weight:800; font-size:14px; padding:12px 24px; border-radius:10px;">Ir al panel de admin →</a>
    """
    await _send(_ADMIN_EMAIL, f"✅ Plan #{plan_id} aplicado: {len(r)} resueltos, {len(f)} fallidos", _wrap(body))


async def send_proposal_notification(
    question: str,
    category: str,
    description: str | None,
    contact: str | None,
    created_at: datetime,
) -> None:
    """Notify the admin that a visitor proposed a new market."""
    body = f"""
      <p style="margin: 0 0 8px; font-size: 16px; color: #F5F0E8;">💡 Nueva propuesta de mercado</p>
      <div style="background: rgba(255,255,255,0.04); border: 1px solid rgba(255,215,0,0.18);
                  border-radius: 12px; padding: 20px; margin-bottom: 22px;">
        <div style="font-size: 15px; font-weight: 700; color: #F5F0E8; margin-bottom: 12px;">{_esc(question)}</div>
        <div style="font-size: 13px; color: rgba(245,240,232,0.7); margin-bottom: 6px;">
          <b style="color:#FFD700">Categoría:</b> {_esc(category)}
        </div>
        <div style="font-size: 13px; color: rgba(245,240,232,0.7); margin-bottom: 6px;">
          <b style="color:#FFD700">Criterio / descripción:</b> {_esc(description) if description else "—"}
        </div>
        <div style="font-size: 13px; color: rgba(245,240,232,0.7); margin-bottom: 6px;">
          <b style="color:#FFD700">Contacto:</b> {_esc(contact) if contact else "Anónimo"}
        </div>
        <div style="font-size: 12px; color: rgba(245,240,232,0.55);">Recibida el {_fmt_mx(created_at)}</div>
      </div>
    """
    subject_q = question if len(question) <= 80 else question[:77] + "…"
    await _send(_ADMIN_EMAIL, f"Nueva propuesta de mercado: {subject_q}", _wrap(body))
