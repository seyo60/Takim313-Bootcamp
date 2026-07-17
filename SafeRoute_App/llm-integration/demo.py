# llm-integration/demo.py
"""
LLM modülünü mock verilerle test eden demo script.
Backend'e dokunmadan çalışır.

Kullanım:
    cd SafeRoute_App/llm-integration
    python demo.py
"""
import asyncio
import json
from pathlib import Path

from schemas.types import StreetRiskData, UserReport
from services.street_explainer import explain_street_risk
from services.report_analyzer import analyze_report
from services.alert_dispatcher import find_nearby_users, dispatch_alerts
from config import settings


MOCKS_DIR = Path(__file__).parent / settings.mocks_dir

# Gemini ucretsiz kota: dakikada 5 istek. Demo toplam 2 LLM cagrisi yapar (1 sokak + 1 ihbar).
DEMO_LLM_LIMIT = 1


def load_json(filename: str) -> list:
    with open(MOCKS_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


async def demo_task1_street_explanations():
    """Görev 1: Sokakların neden güvensiz olduğunu açıkla."""
    print("=" * 60)
    print("GÖREV 1: Sokak Güvenlik Açıklamaları")
    print("=" * 60)

    streets = load_json("sample_streets.json")[:DEMO_LLM_LIMIT]

    for street_data in streets:
        street = StreetRiskData(**street_data)
        explanation = await explain_street_risk(street)

        print(f"\n[Sokak] {street.location_description}")
        print(f"   H3: {street.h3_index} | Toplam Risk: {street.total_risk}")
        print(f"   Seviye: {explanation.risk_level.upper()}")
        print(f"   Açıklama: {explanation.summary}")
        print(f"   Faktörler: {', '.join(explanation.factors)}")


async def demo_task2_report_and_alerts():
    """Görev 2: İhbar analizi + yakın kullanıcılara bildirim."""
    print("\n" + "=" * 60)
    print("GÖREV 2: İhbar Analizi ve Yakın Kullanıcı Bildirimleri")
    print("=" * 60)

    reports = load_json("sample_reports.json")[:DEMO_LLM_LIMIT]

    for report_data in reports:
        report = UserReport(**report_data)
        analysis = await analyze_report(report)

        print(f"\n[Ihbar] \"{report.text}\"")
        print(f"   Konum: ({report.latitude}, {report.longitude})")
        if report.user_score is not None:
            print(f"   Kullanıcı puanı: {report.user_score}")
        print(f"   LLM Analizi -> Risk: {analysis.risk_score} | {analysis.category} | {analysis.severity}")
        print(f"   Özet: {analysis.summary}")
        print(f"   H3: {analysis.h3_index}")

        nearby = find_nearby_users(report.latitude, report.longitude)
        print(f"   Yakın kullanıcı sayısı: {len(nearby)}")

        if analysis.severity in ("high", "critical"):
            alerts = await dispatch_alerts(analysis, report.latitude, report.longitude, nearby)
            print(f"   Gönderilen bildirim: {len(alerts)}")
        else:
            print("   Düşük/orta risk — bildirim gönderilmedi.")


async def main():
    print(f"\nLLM Modu: {settings.llm_mode.upper()}")
    print(f"Mock veri klasoru: {MOCKS_DIR}")
    print(f"Demo LLM istek sayisi: {DEMO_LLM_LIMIT * 2} (sokak: {DEMO_LLM_LIMIT}, ihbar: {DEMO_LLM_LIMIT})\n")

    await demo_task1_street_explanations()

    if settings.llm_mode == "live":
        print("\n[Gemini] Istekler arasi 6s bekleniyor (dakikalik kota limiti)...")
        await asyncio.sleep(6)

    await demo_task2_report_and_alerts()

    print("\n" + "=" * 60)
    print("Demo tamamlandı.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
