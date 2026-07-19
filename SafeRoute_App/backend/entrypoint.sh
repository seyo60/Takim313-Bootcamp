#!/bin/sh
# SafeRoute backend entrypoint:
#   1. Veritabani TAM hazir olana kadar pg_isready ile bekle
#   2. Alembic migration'larini otomatik uygula (alembic upgrade head)
#   3. (Opsiyonel) SEED_ON_START=true ise Chicago suç verisini yükle
#   4. Uvicorn'u baslat
set -e

DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-saferoute}"

echo "[entrypoint] Veritabani bekleniyor: ${DB_HOST}:${DB_PORT} ..."
RETRIES=60
until pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" >/dev/null 2>&1; do
  RETRIES=$((RETRIES - 1))
  if [ "$RETRIES" -le 0 ]; then
    echo "[entrypoint] HATA: Veritabani zaman asimina ugradi." >&2
    exit 1
  fi
  sleep 1
done
echo "[entrypoint] Veritabani hazir."

echo "[entrypoint] Alembic migration'lari uygulaniyor (alembic upgrade head)..."
alembic upgrade head

if [ "${SEED_ON_START:-false}" = "true" ]; then
  echo "[entrypoint] Seed verisi yukleniyor (SEED_ON_START=true)..."
  python seed.py
fi

echo "[entrypoint] Uvicorn baslatiliyor..."
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
