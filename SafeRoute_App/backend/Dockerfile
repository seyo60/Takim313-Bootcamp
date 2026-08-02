# SafeRoute Backend — multi-stage build.
# Build context: SafeRoute_App/ (COPY yolları backend/ ve data-science/ içindir).
#   docker build -f backend/Dockerfile -t saferoute-backend .
#
# 1) builder: bağımlılıkları izole bir venv'e kurar (derleme araçları burada kalır).
# 2) runtime: sadece çalışma-zamanı paylaşımlı kütüphaneler + venv + uygulama kodu.

# ---------------------------------------------------------------------------
# Stage 1 — builder
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS builder

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
FROM python:3.12-slim-bookworm AS runtime

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

# Production için yalnızca 10 MB'lık sıkıştırılmış ikili grafı kopyala (470 MB'lık GraphML DAHİL EDİLMEZ)
COPY backend/ /app/
COPY data-science/compact_graph_res10.npz /data-science/compact_graph_res10.npz
COPY data-science/compact_graph.npz /data-science/compact_graph_res9.npz
COPY data-science/navigation_sidecar_res10.npz /data-science/navigation_sidecar_res10.npz

# Container varsayılan rotalama ayarları
ENV ROUTING_ENGINE=compact
ENV ROUTING_SEARCH_ALGORITHM=scipy_dijkstra
ENV COMPACT_GRAPH_PATH=/data-science/compact_graph_res10.npz
ENV NAVIGATION_SIDECAR_PATH=/data-science/navigation_sidecar_res10.npz
ENV NAVIGATION_SIDECAR_REQUIRED=true
ENV GRAPH_PATH=/data-science/chicago_walk.graphml
ENV ROUTING_H3_RESOLUTION=10
ENV ETL_H3_RESOLUTION=10
ENV REPORT_H3_RESOLUTION=9
ENV H3_PARENT_RESOLUTION=9

RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3)" || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
