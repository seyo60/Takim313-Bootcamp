from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List

app = FastAPI(title="Safe Route App - Backend Mock Server")

# Osman'ın (Mobil) ağ üzerinden senin bilgisayarına bağlanabilmesi için CORS izni
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# İstek modeli (Gelen başlangıç ve bitiş koordinatları için şema)
class RouteRequest(BaseModel):
    start_lat: float
    start_lng: float
    end_lat: float
    end_lng: float

@app.get("/")
def read_root():
    return {"message": "Safe Route App Backend Çalışıyor!"}

@app.post("/api/v1/route")
def get_mock_route(payload: RouteRequest):
    # Osman haritada test edebilsin diye Chicago Downtown 
    # (Millennium Park civarı) sahte rota koordinat bloğu [cite: 115, 117]
    mock_coordinates = [
        [41.8827, -87.6227],
        [41.8815, -87.6227],
        [41.8815, -87.6245],
        [41.8789, -87.6245]
    ]
    return {
        "status": "success",
        "distance_meters": 1200,
        "safety_score": 95,
        "route": mock_coordinates
    }

@app.get("/api/v1/heatmap")
def get_mock_heatmap():
    # Osman'ın ısı haritası katmanını test etmesi için sahte birkaç riskli nokta
    return {
        "points": [
            {"lat": 41.8850, "lng": -87.6270, "weight": 80},
            {"lat": 41.8800, "lng": -87.6200, "weight": 60},
            {"lat": 41.8750, "lng": -87.6250, "weight": 90}
        ]
    }