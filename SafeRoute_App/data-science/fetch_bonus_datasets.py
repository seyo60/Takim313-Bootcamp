# data-science/fetch_bonus_datasets.py
"""
XGBoost (item B) icin ek OZELLIK (feature) hammaddesi.

Bu script'in ciktilari SU ANKI risk formulune (build_risk_dataset.py)
KATILMAZ - sadece data-science/raw/ altina kaydedilir. Amac: ilerideki
XGBoost modelinde "bos bina yogunlugu", "toplu tasima yakinligi" gibi
ek ozellikler kullanilmak istenirse hazir ham veri bulunmasi.

Kullanim:
    <backend_venv>/python.exe fetch_bonus_datasets.py
"""
import csv
import json
import urllib.parse
import urllib.request
from pathlib import Path

RAW_DIR = Path(__file__).parent / "raw"
RAW_DIR.mkdir(exist_ok=True)

SOCRATA_BASE = "https://data.cityofchicago.org/resource"


def fetch_all(dataset: str, select: str, where: str = "", page_size: int = 50000) -> list[dict]:
    records = []
    offset = 0
    while True:
        params = {"$select": select, "$limit": page_size, "$offset": offset}
        if where:
            params["$where"] = where
        url = f"{SOCRATA_BASE}/{dataset}.json?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=60) as response:
            page = json.loads(response.read())
        if not page:
            break
        records.extend(page)
        if len(page) < page_size:
            break
        offset += page_size
    return records


def save(records: list[dict], filename: str, fieldnames: list[str]) -> None:
    path = RAW_DIR / filename
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    print(f"  {path} ({len(records)} kayit)")


def main():
    print("1) Bos/terk edilmis bina sikayetleri (son 24 ay, birlesik 311 sisteminden)...")
    vacant = fetch_all(
        "v6vf-nfxy",
        select="latitude,longitude,created_date,status,sr_type",
        where=(
            "sr_type='Vacant/Abandoned Building Complaint' "
            "AND created_date > '2024-07-25T00:00:00' AND latitude IS NOT NULL"
        ),
    )
    save(vacant, "chicago_vacant_buildings_raw.csv",
         ["latitude", "longitude", "created_date", "status", "sr_type"])

    print("2) CTA otobus durak konumlari (statik referans)...")
    bus_stops = fetch_all("qs84-j7wh", select="systemstop,public_nam,street,cross_st,the_geom")
    for stop in bus_stops:
        coords = stop.get("the_geom", {}).get("coordinates", [None, None])
        stop["longitude"], stop["latitude"] = coords[0], coords[1]
    save(bus_stops, "chicago_cta_bus_stops_raw.csv",
         ["systemstop", "public_nam", "street", "cross_st", "latitude", "longitude"])

    print("\nTamamlandi.")


if __name__ == "__main__":
    main()
