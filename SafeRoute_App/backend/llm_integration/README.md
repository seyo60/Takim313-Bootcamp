# SafeRoute — LLM Entegrasyon Modülü

Backend'e **dokunmadan** çalışan bağımsız LLM modülü.
Mock verilerle test edilir; veritabanı tabloları hazır olunca bağlantı yapılır.

## Görevler

| # | Görev | Servis | Durum |
|---|-------|--------|-------|
| 1 | Sokakların neden güvensiz olduğunu kısa açıkla | `street_explainer.py` | DeepSeek + guardrails |
| 2a | Kullanıcı ihbarını LLM ile analiz et | `report_analyzer.py` | DeepSeek + guardrails |
| 2b | Yakın kullanıcılara bildirim gönder | `alert_dispatcher.py` | Mock ile çalışıyor |

## Kurulum

```bash
cd SafeRoute_App/llm-integration
pip install -r requirements.txt
cp .env.example .env
```

`.env` dosyasında `LLM_MODE=mock` bırakırsanız API key gerekmez.
`LLM_MODE=live` + `DEEPSEEK_API_KEY` ile gerçek DeepSeek API kullanılır.

## DeepSeek Bağlantısı

1. `.env.example` dosyasını `.env` olarak kopyalayın
2. DeepSeek API key'inizi yazın:

```
LLM_MODE=live
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_MODEL=deepseek-chat
```

3. Bağımlılıkları yükleyin ve demo'yu çalıştırın:

```bash
py -3.11 -m pip install -r requirements.txt
py -3.11 demo.py
```

## Guardrails (Cevap Sınırları)

Tüm LLM prompt'ları ve cevap kuralları `prompts/guardrails.py` dosyasında tanımlıdır.

LLM şunları **yapmaz**:
- Siyaset, din, ırk, cinsiyet gibi konulara girmez
- Veri dışı bilgi uydurmaz (halüsinasyon)
- Korku yaratmaz veya abartmaz
- Kişi/grup suçlaması yapmaz
- JSON dışında cevap vermez

LLM cevabı guardrails ihlal ederse otomatik **fallback** (güvenli varsayılan) cevap döner.

Guardrails dosyasını düzenleyerek yasak konuları ve kuralları güncelleyebilirsiniz.

## Demo Çalıştırma

```bash
cd SafeRoute_App/llm-integration
pip install -r requirements.txt

# Windows'ta Python 3.11 kullanın:
py -3.11 demo.py
```

Bu script:
1. 5 örnek sokak için güvenlik açıklaması üretir (Görev 1)
2. 5 örnek ihbarı analiz eder ve yüksek riskli olanlarda yakın kullanıcılara bildirim gönderir (Görev 2)

## Klasör Yapısı

```
llm-integration/
├── config.py                  # Ayarlar (.env okuma)
├── demo.py                    # Test script'i
├── requirements.txt
├── .env.example
│
├── schemas/
│   └── types.py               # Pydantic veri tipleri (DB değil)
│
├── prompts/
│   └── guardrails.py          # LLM cevap sınırları ve sistem prompt'ları
│
├── services/
│   ├── llm_client.py          # Paylaşılan LLM istemcisi (mock + live)
│   ├── street_explainer.py    # Görev 1
│   ├── report_analyzer.py     # Görev 2 — ihbar analizi
│   └── alert_dispatcher.py    # Görev 2 — bildirim gönderimi
│
└── mocks/
    ├── sample_streets.json    # Örnek sokak risk verileri
    ├── sample_reports.json    # Örnek kullanıcı ihbarları
    ├── sample_users.json      # Örnek yakın kullanıcılar
    └── sample_alerts.json     # Örnek bildirim çıktıları
```

## Backend'e Bağlantı Planı (sonra yapılacak)

Bu modül şu an backend dosyalarına dokunmaz. İleride bağlantı şöyle yapılacak:

| Modül fonksiyonu | Şimdiki veri kaynağı | Sonraki veri kaynağı |
|------------------|---------------------|---------------------|
| `explain_street_risk()` | `sample_streets.json` | `h3_heatmap` tablosu |
| `analyze_report()` | `sample_reports.json` | `reports` tablosu |
| `find_nearby_users()` | `sample_users.json` | `users` + `device_tokens` tabloları |
| `dispatch_alerts()` | Konsola log | `notifications` tablosu + FCM/APNs |

Backend arkadaşınız tabloları ekledikten sonra `repositories/` katmanı yazılacak;
servis fonksiyonlarının imzaları değişmeyecek, sadece veri kaynağı değişecek.

## Gerçek LLM'e Geçiş

Varsayılan sağlayıcı **DeepSeek**. `.env` dosyasında:

```
LLM_MODE=live
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-...
```

Alternatif sağlayıcılar: `openai`, `gemini` (ayrı API key gerekir).

## Önemli Notlar

- `backend/` klasöründeki hiçbir dosyaya dokunulmaz
- `backend/llm_service.py` ayrı bir dosyadır; bu modül ondan bağımsızdır
- Risk formülü (`crud.py`) ve rota hesaplama (`routing.py`) bu modülün dışındadır
- Mock modda tüm testler API key olmadan çalışır
