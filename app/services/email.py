import logging
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_FROM = "VEREDIKT <noreply@veredikt.mx>"
_SITE = "https://veredikt.mx"


async def _send(to_email: str, subject: str, html: str) -> None:
    """Low-level send via Resend. No-op (logged) if no API key configured."""
    if not settings.RESEND_API_KEY:
        logger.info(f"[DEV] Email a {to_email}: {subject}")
        return
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                json={"from": _FROM, "to": [to_email], "subject": subject, "html": html},
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


async def send_verification_email(to_email: str, display_name: str, code: str) -> None:
    body = f"""
      <p style="margin: 0 0 8px; font-size: 16px; color: #F5F0E8;">Hola {display_name},</p>
      <p style="margin: 0 0 28px; font-size: 14px; color: rgba(245,240,232,0.6);">
        Tu código de verificación es:
      </p>
      <div style="background: rgba(255,215,0,0.08); border: 1px solid rgba(255,215,0,0.3);
                  border-radius: 12px; padding: 28px; text-align: center; margin-bottom: 28px;">
        <span style="font-family: 'Courier New', monospace; font-size: 42px; font-weight: 700;
                     letter-spacing: 14px; color: #FFD700;">{code}</span>
      </div>
      <p style="margin: 0; font-size: 12px; color: rgba(245,240,232,0.35);">
        Válido por 15 minutos. Si no creaste esta cuenta, ignora este correo.
      </p>
    """
    await _send(to_email, f"{code} es tu código de verificación VEREDIKT", _wrap(body))


async def send_resolution_email(
    to_email: str, display_name: str, question: str, won: bool, payout: float
) -> None:
    """Notify a position holder that a market they traded resolved."""
    if won:
        headline = "✅ ¡Ganaste!"
        color = "#00FF88"
        detail = f"Tu predicción fue correcta. Ganaste <b style=\"color:#00FF88\">+{round(payout)} PT</b>."
    else:
        headline = "Resultado del mercado"
        color = "#FF2D55"
        detail = "Esta vez tu predicción no acertó. ¡Va la próxima!"

    body = f"""
      <p style="margin: 0 0 8px; font-size: 16px; color: #F5F0E8;">Hola {display_name},</p>
      <p style="margin: 0 0 18px; font-size: 14px; color: rgba(245,240,232,0.6);">
        El mercado en el que participaste ya se resolvió:
      </p>
      <div style="background: rgba(255,255,255,0.04); border: 1px solid rgba(255,215,0,0.18);
                  border-radius: 12px; padding: 20px; margin-bottom: 22px;">
        <div style="font-size: 15px; font-weight: 700; color: #F5F0E8; margin-bottom: 12px;">{question}</div>
        <div style="font-size: 18px; font-weight: 800; color: {color}; margin-bottom: 6px;">{headline}</div>
        <div style="font-size: 14px; color: rgba(245,240,232,0.7);">{detail}</div>
      </div>
      <a href="{_SITE}" style="display:inline-block; background:#FFD700; color:#07071A;
         text-decoration:none; font-weight:800; font-size:14px; padding:12px 24px; border-radius:10px;">
        Ver mercados →
      </a>
      <p style="margin: 24px 0 0; font-size: 11px; color: rgba(245,240,232,0.3);">
        Recibes este correo porque participaste en este mercado. Puedes desactivar las
        notificaciones en tu perfil en {_SITE}/#/perfil
      </p>
    """
    await _send(to_email, "Tu mercado en VEREDIKT se resolvió", _wrap(body))
