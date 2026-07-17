# SafeRoute Backend Dockerfile
FROM python:3.12-slim

# pg_isready icin postgresql-client, osmnx/shapely icin derleme kutuphaneleri
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    libgeos-dev \
    libspatialindex-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Backend kodu ve graf/veri dosyalari
COPY backend/ /app/
COPY data-science/ /data-science/

# Container icinde graf yolu (compose'da GRAPH_PATH ile override edilebilir)
ENV GRAPH_PATH=/data-science/chicago.graphml

RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
