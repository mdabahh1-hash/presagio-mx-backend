import logging
import httpx
from app.config import settings

logger = logging.getLogger(__name__)


async def send_verification_email(to_email: str, display_name: str, code: str) -> None:
    if not settings.RESEND_API_KEY:
        logger.info(f"[DEV] Código de verificación para {to_email}: {code}")
        return

    html = f"""
    <div style="font-family: -apple-system, sans-serif; max-width: 480px; margin: 0 auto;
                background: #07071A; color: #F5F0E8; padding: 40px 32px; border-radius: 16px;">
      <div style="font-size: 28px; font-weight: 900; letter-spacing: 0.12em;
                  color: #FFD700; margin-bottom: 28px;">VEREDIKT</div>
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
    </div>
    """

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
            json={
                "from": settings.FROM_EMAIL,
                "to": [to_email],
                "subject": f"{code} es tu código de verificación VEREDIKT",
                "html": html,
            },
        )
        if not resp.is_success:
            logger.error(f"Resend error {resp.status_code}: {resp.text}")
