# PRESAGIO Backend — Setup

## 1. Crear base de datos

```bash
createdb presagio
# o con psql:
psql -c "CREATE DATABASE presagio;"
```

## 2. Instalar dependencias

```bash
cd presagio-mx-backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 3. Configurar variables de entorno

```bash
cp .env.example .env
# Editar .env con tus credenciales OAuth y el DATABASE_URL correcto
```

### Crear OAuth Apps:

**Google:** https://console.cloud.google.com/apis/credentials
- Authorized redirect URI: `http://localhost:8000/api/auth/google/callback`

**GitHub:** https://github.com/settings/developers
- Authorization callback URL: `http://localhost:8000/api/auth/github/callback`

## 4. Levantar el servidor

```bash
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

El servidor crea las tablas y siembra los mercados automáticamente en el primer arranque.

## 5. API Docs

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Endpoints principales

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | /api/markets | Listar mercados |
| GET | /api/markets/{id} | Detalle de mercado |
| GET | /api/markets/{id}/history | Historial de precios |
| POST | /api/markets/{id}/trade | Ejecutar operación (auth) |
| GET | /api/markets/{id}/comments | Comentarios |
| POST | /api/markets/{id}/comments | Nuevo comentario (auth) |
| GET | /api/users/me | Usuario actual (auth) |
| GET | /api/auth/google | Login con Google |
| GET | /api/auth/github | Login con GitHub |
| WS | /ws/market/{id} | Precios en tiempo real |
| WS | /ws/feed | Feed global de actividad |

## LMSR — Cómo funciona

El motor de precios usa LMSR (Logarithmic Market Scoring Rule):

- `b = 100` por defecto → pérdida máxima del market maker = ~69 PT por mercado
- Cada compra mueve el precio según `p = 1 / (1 + exp((q_no - q_yes) / b))`
- Al resolver: holders del lado correcto reciben 1 PT por acción
