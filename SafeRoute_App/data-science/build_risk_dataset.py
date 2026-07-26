# data-science/build_risk_dataset.py
"""
Chicago Data Portal (Socrata) uzerinden GERCEK, koordinatli suc ve sokak
lambasi arizasi verisini ceker; H3 (res 9) hucresi bazinda toplar; ekibin
ROUTE_SCORES_INFO.md'de tanimladigi formulu (Suc*0.75 + Lamba*0.25,
yuzdelik dilim) uygulayip backend/seed.py'nin bekledigi semada
chicago_clean_data.csv uretir.

NEDEN Chicago_Route_Scores.json DOGRUDAN KULLANILMADI:
O dosyadaki anahtarlar sokak adi degil, BLOK bazli adres ("100A N LOTUS
AVE"). Bunlari harita koordinatina baglamak icin ya 2859 adresi tek tek
geocode etmek (yavas, kirilgan) ya da OSM sokak adlariyla metin
eslestirmesi yapmak (adres formatlari uyusmuyor) gerekirdi. Bunun yerine
ham suc/311 verisi zaten kendi enlem/boylamiyla geliyor - geocoding'e hic
gerek yok ve ayni zamanda XGBoost (item B) icin gereken ham/granuler veriyi
de saglar.

OLCEK DUZELTMESI (onemli, ekibe bildirilmeli):
crud.py'deki agirlikli formul: total_risk = historical*0.5 + live*0.5
'live' kanali (llm_service.py / report_analyzer) 0-100 olcekte skor
uretiyor. Eski Chicago_Route_Scores.json ise 1.0-10.0 olcektendi - yani
historical kanalinin gercek katkisi live'in onda biri kadar kaliyordu.
Bu script historical skoru da 0-100'e tasiyarak iki kanali karsilastirilabilir
hale getiriyor.

Kullanim:
    <backend_venv>/python.exe build_risk_dataset.py
"""
import csv
import json
import statistics
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

import h3

H3_RESOLUTION = 9  # main.py / routing.py ile ayni cozunurluk

DATA_DIR = Path(__file__).parent
RAW_DIR = DATA_DIR / "raw"
RAW_DIR.mkdir(exist_ok=True)

SOCRATA_BASE = "https://data.cityofchicago.org/resource"
CRIMES_DATASET = "ijzp-q8t2"    # Crimes - 2001 to Present
# NOT: eski "zuxi-7xem" (311 Street Lights - All Out) 2018'de donduruldu
# (Historical). Sehir artik TUM 311 taleplerini tek datasette topluyor;
# lamba arizasi icin sr_type filtresi kullaniliyor.
SERVICE_311_DATASET = "v6vf-nfxy"  # 311 Service Requests (birlesik, canli)
LIGHT_SR_TYPES = ["Street Light Out Complaint", "Alley Light Out Complaint"]

# Yayaya/sokak guvenligine dogrudan iliskili, acik/kamusal alan konumlari.
# (Sprint 1 notu: "sadece acik alanlarda gerceklesen, sokak guvenligini
# ilgilendiren suclar filtrelendi" - ayni mantik burada uygulaniyor.)
OUTDOOR_LOCATIONS = [
    "STREET", "SIDEWALK", "ALLEY", "PARK PROPERTY", "GAS STATION",
    "PARKING LOT/GARAGE(NON.RESID.)", "PARKING LOT / GARAGE (NON RESIDENTIAL)",
    "VEHICLE NON-COMMERCIAL", "CHA PARKING LOT/GROUNDS", "BRIDGE",
    "HIGHWAY/EXPRESSWAY", "VACANT LOT/LAND", "LAKEFRONT/WATERFRONT/RIVERBANK",
]

CRIME_LOOKBACK_WHERE = "date > '2025-07-25T00:00:00'"  # son 12 ay
LIGHTS_LOOKBACK_WHERE = "created_date > '2024-07-25T00:00:00'"  # son 24 ay


def fetch_all(dataset: str, select: str, where: str, page_size: int = 50000) -> list[dict]:
    """Socrata API'den $limit/$offset sayfalamasiyla TUM kayitlari ceker."""
    records = []
    offset = 0
    while True:
        params = {
            "$select": select,
            "$where": where,
            "$limit": page_size,
            "$offset": offset,
        }
        url = f"{SOCRATA_BASE}/{dataset}.json?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=60) as response:
            page = json.loads(response.read())
        if not page:
            break
        records.extend(page)
        print(f"  [{dataset}] {len(records)} kayit cekildi...")
        if len(page) < page_size:
            break
        offset += page_size
    return records


def save_raw_csv(records: list[dict], filename: str, fieldnames: list[str]) -> None:
    """Ham veriyi data-science/raw/ altina kaydeder (item B / XGBoost hammaddesi)."""
    path = RAW_DIR / filename
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    print(f"  Ham veri kaydedildi: {path} ({len(records)} kayit)")


def percentile_scores(counts: dict) -> dict:
    """
    {h3_index: count} -> {h3_index: 0-100 yuzdelik dilim skoru}.
    En yuksek sayima sahip hucre ~100, hic olayi olmayan hucreler bu
    sozlukte hic yer almaz (cagiran taraf eksik anahtarlari 0 kabul eder).
    """
    if not counts:
        return {}
    sorted_cells = sorted(counts.items(), key=lambda kv: kv[1])
    n = len(sorted_cells)
    scores = {}
    for rank, (cell, _count) in enumerate(sorted_cells):
        # rank 0 -> en dusuk (ama sifir degil, olay en az bir kez oldu)
        # rank n-1 -> en yuksek
        scores[cell] = round((rank / max(n - 1, 1)) * 100, 2)
    return scores


def main():
    print("1) Chicago suc verisi cekiliyor (son 12 ay, acik alan filtreli)...")
    location_filter = " OR ".join(f"location_description='{loc}'" for loc in OUTDOOR_LOCATIONS)
    crimes_where = f"{CRIME_LOOKBACK_WHERE} AND latitude IS NOT NULL AND ({location_filter})"
    crimes = fetch_all(
        CRIMES_DATASET,
        select="latitude,longitude,date,primary_type,location_description",
        where=crimes_where,
    )
    save_raw_csv(
        crimes, "chicago_crimes_raw.csv",
        ["latitude", "longitude", "date", "primary_type", "location_description"],
    )

    print("\n2) Chicago 311 sokak lambasi arizasi verisi cekiliyor (son 24 ay)...")
    sr_type_filter = " OR ".join(f"sr_type='{t}'" for t in LIGHT_SR_TYPES)
    lights = fetch_all(
        SERVICE_311_DATASET,
        select="latitude,longitude,created_date,status,sr_type",
        where=f"{LIGHTS_LOOKBACK_WHERE} AND latitude IS NOT NULL AND ({sr_type_filter})",
    )
    save_raw_csv(
        lights, "chicago_streetlights_raw.csv",
        ["latitude", "longitude", "created_date", "status", "sr_type"],
    )

    print("\n3) H3 (res 9) hucrelerine agregasyon yapiliyor...")
    crime_counts = defaultdict(int)
    for row in crimes:
        cell = h3.latlng_to_cell(float(row["latitude"]), float(row["longitude"]), H3_RESOLUTION)
        crime_counts[cell] += 1

    light_counts = defaultdict(int)
    for row in lights:
        cell = h3.latlng_to_cell(float(row["latitude"]), float(row["longitude"]), H3_RESOLUTION)
        light_counts[cell] += 1

    print(f"  Suc verisi {len(crime_counts)} farkli H3 hucresine dagildi.")
    print(f"  Lamba arizasi verisi {len(light_counts)} farkli H3 hucresine dagildi.")

    print("\n4) Yuzdelik dilim skorlari hesaplaniyor (0-100 olcek)...")
    crime_pct = percentile_scores(crime_counts)
    light_pct = percentile_scores(light_counts)

    all_cells = set(crime_pct) | set(light_pct)
    print(f"  Toplam {len(all_cells)} benzersiz H3 hucresi risk skoru alacak.")

    print("\n5) Agirlikli formul uygulaniyor: total = suc*0.75 + lamba*0.25")
    rows = []
    for cell in all_cells:
        crime_score = crime_pct.get(cell, 0.0)
        light_score = light_pct.get(cell, 0.0)
        total_risk = round(crime_score * 0.75 + light_score * 0.25, 2)
        lat, lng = h3.cell_to_latlng(cell)
        rows.append({
            "osmid": cell,
            "name": (
                f"H3:{cell} (suc={crime_counts.get(cell, 0)}, "
                f"lamba_ariza={light_counts.get(cell, 0)})"
            ),
            "anlik_risk": total_risk,
            # seed.py sadece LINESTRING'in ILK koordinatini kullanir; H3
            # hucre merkezini gecerli bir LINESTRING olarak temsil etmek
            # icin ayni nokta iki kez yazilir.
            "geometry": f"LINESTRING ({lng} {lat}, {lng} {lat})",
        })

    print("\n6) chicago_clean_data.csv yaziliyor (backend/seed.py semasi)...")
    out_path = DATA_DIR / "chicago_clean_data.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["osmid", "name", "anlik_risk", "geometry"])
        writer.writeheader()
        writer.writerows(rows)

    risk_values = [r["anlik_risk"] for r in rows]
    print(f"\nTAMAMLANDI: {out_path}")
    print(f"  {len(rows)} H3 hucresi yazildi (oncesi: 12 satirlik test verisi).")
    print(f"  Risk dagilimi: min={min(risk_values):.1f} "
          f"medyan={statistics.median(risk_values):.1f} max={max(risk_values):.1f}")


if __name__ == "__main__":
    main()
