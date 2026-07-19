# backend/llm_service.py
"""
Ihbar metni -> risk ceza puani (0-100) servisi.

MIMARI (P2 - LLM Entegrasyonu):
- LLM_MODE=live  -> llm_integration.report_analyzer uzerinden gercek LLM
  cagrisi yapilir (birincil saglayici: Gemini, .env: LLM_PROVIDER=gemini).
- LLM_MODE=mock  -> API anahtari gerekmeden kural tabanli skor uretilir.
- HATA DAYANIKLILIGI: Canli cagri sirasinda ag hatasi, kota asimi (429)
  veya baska bir istisna olusursa arka plan gorevi ASLA cokmez; kural
  tabanli guvenli fallback skoruna (10-100 arasi) gecilir.

Bu modul main.py'nin arka plan gorevinden cagrilir ve API'yi bloklamaz.
"""
from config import settings
from llm_integration.schemas.types import UserReport
from llm_integration.services.report_analyzer import analyze_report


def rule_based_risk_score(text: str) -> float:
    """
    Kural tabanli guvenli fallback: kelime eslesmesiyle 10-100 arasi
    ceza puani uretir. LLM erisilemedigi her durumda kullanilir.
    """
    text_lower = text.lower()

    if any(w in text_lower for w in ["silah", "bıçak", "saldırı", "taciz", "çatışma", "cinayet", "gasp"]):
        return 100.0  # Kesinlikle o sokaga sokma
    if any(w in text_lower for w in ["kavga", "tehlike", "şüpheli", "köpek", "hırsız", "kapkaç"]):
        return 50.0   # Mumkunse alternatif rotaya sap
    if any(w in text_lower for w in ["karanlık", "lamba", "ıssız", "aydınlatma"]):
        return 20.0   # Kucuk ceza puani
    return 10.0       # Varsayilan dusuk risk


async def analyze_report_risk_with_llm(text: str, latitude: float = 0.0, longitude: float = 0.0) -> float:
    """
    Ihbar metnini analiz edip 0-100 arasi risk ceza puani doner.

    Akis:
      1. LLM_MODE=mock ise dogrudan kural tabanli skor doner (hizli, ucretsiz).
      2. LLM_MODE=live ise report_analyzer -> llm_client -> Gemini/DeepSeek/OpenAI
         zinciri calisir. report_analyzer'in kendi guardrail dogrulamasi da vardir.
      3. Zincirde HERHANGI bir hata (429 kota, ag, parse...) olursa
         kural tabanli skora guvenli gecis yapilir (Graceful Fallback).
    """
    if settings.llm_mode != "live":
        return rule_based_risk_score(text)

    try:
        report = UserReport(latitude=latitude, longitude=longitude, text=text)
        result = await analyze_report(report)
        score = float(result.risk_score)
        # Emniyet kemeri: 0-100 araligina sabitle
        return max(0.0, min(100.0, score))
    except Exception as e:
        # Kota asimi (HTTP 429), ag hatasi, gecersiz JSON vb. durumlarda
        # arka plan gorevini COKERTMEDEN kural tabanli skora dus.
        print(f"[LLM Fallback] Canli LLM cagrisi basarisiz ({type(e).__name__}: {e}). "
              f"Kural tabanli mock skora geciliyor.")
        return rule_based_risk_score(text)
