# SafeRoute Backend — multi-stage build.
# Build context: SafeRoute_App/ (COPY yolları backend/ ve data-science/ içindir).
#   docker build -f backend/Dockerfile -t saferoute-backend .
#
# 1) builder: bağımlılıkları izole bir venv'e kurar (derleme araçları burada kalır).
# 2) runtime: sadece çalışma-zamanı paylaşımlı kütüphaneler + venv + uygulama kodu.

# ---------------------------------------------------------------------------
# Stage 1 — builder
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

# Derleme için gereken başlıklar/araçlar (yalnızca bu aşamada; final imaja gitmez).
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgeos-dev \
    libspatialindex-dev \
    && rm -rf /var/lib/apt/lists/*

# İzole venv — final aşamaya sadece kurulu paketleri kopyalayabilelim diye.
ENV VIRTUAL_ENV=/opt/venv
RUN python -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ---------------------------------------------------------------------------
# Stage 2 — runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Yalnızca çalışma-zamanı paylaşımlı kütüphaneler (başlık/derleme aracı YOK):
#  - postgresql-client: entrypoint'teki pg_isready
#  - libgeos-c1v5 / libspatialindex6: shapely & osmnx (rtree) runtime bağımlılığı
# NOT: paket adları Debian bookworm (python:3.12-slim) içindir. Temel imaj
# değişirse burada güncellenmeli. Değişiklik sonrası bir kez `docker build` ile
# doğrulayın (bu ortamda Docker çalıştırılamadı).
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    libgeos-c1v5 \
    libspatialindex6 \
    && rm -rf /var/lib/apt/lists/*

# Kurulu bağımlılıkları builder'dan al.
ENV VIRTUAL_ENV=/opt/venv
COPY --from=builder /opt/venv /opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR /app

# Backend kodu ve graf/veri dosyaları.
COPY backend/ /app/
COPY data-science/ /data-science/

# Container içinde graf yolu (compose'da GRAPH_PATH ile override edilebilir).
ENV GRAPH_PATH=/data-science/chicago.graphml

RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
