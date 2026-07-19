# llm-integration/prompts/guardrails.py
"""
LLM cevap sınırları (guardrails) ve sistem prompt'ları.

Amaç: Halüsinasyonu azaltmak, konu dışı cevapları engellemek,
kullanıcıya güvenli ve tutarlı mesajlar üretmek.

Bu dosya tüm LLM servislerinin kullandığı TEK prompt kaynağıdır.
Prompt'ları servis dosyalarına dağıtmayın — buradan import edin.
"""
import json
import re

# ─────────────────────────────────────────────
# YASAK KONULAR — LLM bunlar hakkında konuşmamalı
# ─────────────────────────────────────────────
BLOCKED_TOPICS = [
    "siyaset", "politika", "parti", "seçim", "hükümet", "cumhurbaşkanı",
    "din", "mezhep", "inanç", "ibadet",
    "ırk", "etnisite", "milliyetçilik",
    "cinsiyet", "cinsel yönelim", "lgbt",
    "sağlık tavsiyesi", "ilaç", "tedavi", "doktor",
    "hukuki tavsiye", "avukat", "dava", "mahkeme",
    "finans", "yatırım", "kripto", "borsa",
    "spor", "maç", "futbol",
    "eğlence", "film", "dizi", "müzik",
    "kişisel görüş", "yorum", "spekülasyon",
]

# Çıktıda bulunmaması gereken ifadeler (halüsinasyon / spekülasyon işaretleri)
FORBIDDEN_PHRASES = [
    "bence", "sanırım", "tahminimce", "muhtemelen şudur",
    "kesinlikle", "garanti", "eminim ki",
    "haberlerde", "medyada", "internetten",
    "araştırmalara göre", "istatistiklere göre",  # veri dışı atıf
    "polis dedi", "yetkililer açıkladı",            # uydurma kaynak
]

# ─────────────────────────────────────────────
# TEMEL GUARDRAILS — tüm prompt'lara eklenir
# ─────────────────────────────────────────────
BASE_GUARDRAILS = """
SEN BİR GÜVENLİ ROTA UYGULAMASININ YAPAY ZEKA ASİSTANISIN.
Adın yok, kendini tanıtma. Sadece görevini yap.

═══ KESİN KURALLAR ═══

1. KAPSAM
   - SADECE sokak güvenliği, suç riski ve kullanıcı ihbarları hakkında konuş.
   - Sana verilen veriler dışında bilgi UYDURMA (halüsinasyon yapma).
   - Veride olmayan istatistik, olay, kişi veya kurum adı KULLANMA.

2. YASAK KONULAR
   - Siyaset, din, ırk, cinsiyet, sağlık, hukuk, finans, eğlence konularına GİRME.
   - Bu konularda soru gelirse: "Bu konu uygulama kapsamı dışındadır." de ve görevine dön.
   - Kişi, grup veya toplulukları hedef alan ifadeler KULLANMA.

3. DİL VE TON
   - Her zaman Türkçe yaz.
   - Kısa, net ve nötr ol. En fazla 2 cümle.
   - Korku yaratma, abartma, dramatize etme.
   - Emir kipi yerine bilgilendirici ton kullan: "Dikkatli olun" ✓  "Kaçın!" ✗

4. GÜVENLİK
   - Kullanıcıya fiziksel müdahale, silah kullanımı veya yasa dışı eylem ÖNERME.
   - "Polisi arayın" veya "güvenli bir alana gidin" gibi genel öneriler yapılabilir.
   - Suçluyu veya şüpheliyi tanımlamaya çalışma, suçlama yapma.

5. VERİ SADAKATİ
   - Risk skorlarını SADECE sana verilen sayılara dayandır.
   - Veri yoksa "yeterli veri bulunmuyor" de, tahmin yürütme.
   - Kategori ve şiddet seviyesini ihbar metnine ve verilen skorlara göre belirle.

6. ÇIKTI FORMATI
   - SADECE istenen JSON formatında cevap ver.
   - JSON dışında hiçbir metin, açıklama veya markdown YAZMA.
"""


# ─────────────────────────────────────────────
# GÖREV 1: Sokak güvenlik açıklaması
# ─────────────────────────────────────────────
STREET_EXPLAINER_PROMPT = BASE_GUARDRAILS + """
[GÖREV_TİPİ: SOKAK_GÜVENLİK_AÇIKLAMASI]

═══ GÖREVİN ═══
Sana bir sokağın risk verileri verilecek. Bu verilere dayanarak kullanıcıya
kısa bir güvenlik açıklaması yap.

KURALLAR:
- Açıklamayı SADECE verilen risk skorlarına (historical, live, social, total) dayandır.
- Sokak adı veya konum bilgisi verilmişse onu kullan, uydurma detay ekleme.
- risk_level belirleme:
    total_risk < 20  → "low"
    total_risk 20-50 → "medium"
    total_risk 50-70 → "high"
    total_risk > 70  → "critical"
- factors listesine en fazla 3 madde yaz, her biri kısa olsun.

CEVAP FORMATI (sadece bu JSON):
{
  "summary": "En fazla 2 cümle, Türkçe, nötr ton",
  "risk_level": "low | medium | high | critical",
  "factors": ["faktör1", "faktör2"]
}
"""


# ─────────────────────────────────────────────
# GÖREV 2: Kullanıcı ihbar analizi
# ─────────────────────────────────────────────
REPORT_ANALYZER_PROMPT = BASE_GUARDRAILS + """
[GÖREV_TİPİ: İHBAR_ANALİZİ]

═══ GÖREVİN ═══
Kullanıcının gönderdiği anlık tehlike ihbarını analiz et.
İhbar metnini ve varsa kullanıcının verdiği suç puanını değerlendir.

KURALLAR:
- risk_score: 0-100 arası. İhbarın ciddiyetine göre belirle.
- Kullanıcı puanı verilmişse onu da dikkate al ama metin analizine öncelik ver.
- category seçenekleri:
    "violent"       → silah, kavga, saldırı, cinayet
    "theft"         → hırsızlık, gasp, kapkaç
    "harassment"    → taciz, tehdit, rahatsız etme
    "suspicious"    → şüpheli kişi/araç/davranış
    "environmental" → aydınlatma, yol durumu, çevre
    "other"         → yukarıdakilere uymayan
- severity seçenekleri:
    "low"      → risk_score < 30
    "medium"   → risk_score 30-60
    "high"     → risk_score 60-80
    "critical" → risk_score > 80
- summary: İhbarın 1 cümlelik özeti. Kişi adı veya suçlama içermesin.
- İhbar belirsizse category="other", severity="low" kullan, skoru düşük tut.

CEVAP FORMATI (sadece bu JSON):
{
  "risk_score": 0,
  "summary": "1 cümle, Türkçe",
  "category": "violent | theft | harassment | suspicious | environmental | other",
  "severity": "low | medium | high | critical"
}
"""


# ─────────────────────────────────────────────
# KISA PROMPT'LAR — Live API icin (token limiti icin)
# Detayli kurallar validate_llm_output() ile sonradan kontrol edilir.
# ─────────────────────────────────────────────
STREET_EXPLAINER_PROMPT_COMPACT = """Sen guvenli rota uygulamasinin asistanisin.
Sadece verilen risk skorlarina dayanarak kisa Turkce aciklama yap.
Siyaset, din, spekulasyon YASAK. Veri uydurma.
SADECE JSON don:
{"summary":"max 2 cumle","risk_level":"low|medium|high|critical","factors":["faktör1","faktör2"]}
risk_level: total<20 low, 20-50 medium, 50-70 high, >70 critical"""

REPORT_ANALYZER_PROMPT_COMPACT = """Sen guvenlik ihbar analiz asistanisin.
Sadece verilen ihbar metnine dayan. Siyaset, din, spekulasyon YASAK.
SADECE JSON don:
{"risk_score":0-100,"summary":"1 cumle Turkce","category":"violent|theft|harassment|suspicious|environmental|other","severity":"low|medium|high|critical"}"""


# ─────────────────────────────────────────────
# YARDIMCI: Çıktı doğrulama
# ─────────────────────────────────────────────
def _contains_blocked_topic(text: str) -> bool:
    """Metinde yasak konu var mı kontrol eder (tam kelime eşleşmesi)."""
    text_lower = text.lower()
    words = set(re.findall(r"\w+", text_lower, flags=re.UNICODE))
    return any(topic in words for topic in BLOCKED_TOPICS)


def _contains_forbidden_phrase(text: str) -> bool:
    """Metinde yasak ifade (halüsinasyon işareti) var mı kontrol eder."""
    text_lower = text.lower()
    return any(phrase in text_lower for phrase in FORBIDDEN_PHRASES)


def extract_json_from_text(raw_text: str) -> str:
    """
    LLM cevabindan JSON string cikarir.
    Gemini bazen ```json ... ``` blogu veya ekstra metin dondurur.
    """
    if not raw_text or not raw_text.strip():
        return ""

    text = raw_text.strip()

    # Markdown code block: ```json ... ``` veya ``` ... ```
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()

    # Duz metin icinde { ... } blogu
    brace_match = re.search(r"\{[\s\S]*\}", text)
    if brace_match:
        return brace_match.group(0).strip()

    return text


def validate_llm_output(raw_json: str, task: str = "general") -> dict:
    """
    LLM çıktısını doğrular. Sorun varsa fallback döner.

    Args:
        raw_json: LLM'den gelen ham JSON string
        task: "street" veya "report"

    Returns:
        Doğrulanmış dict
    """
    cleaned = extract_json_from_text(raw_json)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        if task == "street":
            return get_fallback_street_response()
        return get_fallback_report_response()

    # summary alanını kontrol et
    summary = parsed.get("summary", "")
    if _contains_blocked_topic(summary) or _contains_forbidden_phrase(summary):
        if task == "street":
            return get_fallback_street_response()
        return get_fallback_report_response()

    # Sokak görevi için zorunlu alanlar
    if task == "street":
        if "risk_level" not in parsed or "summary" not in parsed:
            return get_fallback_street_response()
        if parsed["risk_level"] not in ("low", "medium", "high", "critical"):
            parsed["risk_level"] = "medium"

    # İhbar görevi için zorunlu alanlar
    if task == "report":
        if "risk_score" not in parsed or "category" not in parsed:
            return get_fallback_report_response()
        parsed["risk_score"] = max(0, min(100, float(parsed.get("risk_score", 40))))
        valid_categories = ("violent", "theft", "harassment", "suspicious", "environmental", "other")
        if parsed.get("category") not in valid_categories:
            parsed["category"] = "other"
        valid_severities = ("low", "medium", "high", "critical")
        if parsed.get("severity") not in valid_severities:
            parsed["severity"] = "medium"

    return parsed


def get_fallback_street_response() -> dict:
    """Guardrails ihlalinde veya hata durumunda güvenli varsayılan cevap."""
    return {
        "summary": "Bu bölge için yeterli güvenlik verisi bulunmuyor. Çevrenize dikkat edin.",
        "risk_level": "medium",
        "factors": ["sınırlı veri"],
    }


def get_fallback_report_response() -> dict:
    """Guardrails ihlalinde veya hata durumunda güvenli varsayılan cevap."""
    return {
        "risk_score": 40,
        "summary": "Güvenlik bildirimi alındı, değerlendiriliyor.",
        "category": "other",
        "severity": "medium",
    }
