"""Genera el JWT de admin para el agente de mercados y lo guarda en .env.agent.

No requiere contraseña ni Railway: firma el token con la SECRET_KEY del .env
local (misma que producción) y lo valida contra el servidor antes de guardarlo.
El token nunca se imprime en pantalla; solo se escribe en .env.agent
(chmod 600, ignorado por git).

Nota: la variable SECRET_KEY en Railway tiene actualmente dos saltos de línea
al final del valor (accidente de copy/paste al crearla), así que la clave
efectiva del servidor es "clave\n\n". Este script prueba las variantes con y
sin saltos y guarda el token que el servidor acepte — si algún día se limpia
la variable en Railway (lo cual invalida las sesiones de los usuarios), el
script se adapta solo.

Uso (desde la raíz del repo):
  ./venv/bin/python generate-agent-token.py
"""
import json
import os
import stat
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from jose import jwt

ADMIN_EMAIL = "mdabahh@atid.edu.mx"
ADMIN_USER_ID = "1"
API_BASE = "https://presagio-mx-backend-production-a30e.up.railway.app"
REPO_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(REPO_DIR, ".env.agent")
DIAS_VALIDEZ = 7  # igual que ACCESS_TOKEN_EXPIRE_MINUTES del backend (7 días)


def secret_key_from_env_file() -> str | None:
    env_path = os.path.join(REPO_DIR, ".env")
    if not os.path.exists(env_path):
        return None
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("SECRET_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def valida_contra_produccion(token: str) -> bool:
    req = urllib.request.Request(
        f"{API_BASE}/api/users/me", headers={"Authorization": f"Bearer {token}"}
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.load(r).get("email") == ADMIN_EMAIL
    except urllib.error.HTTPError:
        return False


def main() -> None:
    base_key = os.environ.get("SECRET_KEY") or secret_key_from_env_file()
    if not base_key:
        sys.exit("ERROR: no hay SECRET_KEY ni en el entorno ni en el .env local.")

    expire = datetime.now(timezone.utc) + timedelta(days=DIAS_VALIDEZ)
    for sufijo in ("\n\n", "", "\n", "\n\n\n", "\r\n"):
        token = jwt.encode(
            {"sub": ADMIN_USER_ID, "exp": expire}, base_key + sufijo, algorithm="HS256"
        )
        if valida_contra_produccion(token):
            with open(ENV_FILE, "w") as f:
                f.write(f"VEREDIKT_ADMIN_TOKEN={token}\n")
            os.chmod(ENV_FILE, stat.S_IRUSR | stat.S_IWUSR)  # 600
            print(f"✅ Token de admin validado contra producción y guardado en {ENV_FILE}")
            print(f"   Válido hasta: {expire.strftime('%d-%b-%Y %H:%M UTC')} (renovar con este mismo script)")
            return

    sys.exit(
        "ERROR: ninguna variante firmó un token que producción acepte. "
        "La SECRET_KEY del .env local ya no coincide con la del servidor: "
        "cópiala de nuevo desde Railway (dashboard → presagio-mx-backend → Variables)."
    )


main()
