# llm-integration/services/llm_client.py
"""
Paylaşılan LLM istemcisi.
mock modda kural tabanlı cevap döner, live modda gerçek API çağrısı yapar.
Backend'deki llm_service.py'ye DOKUNULMAZ — bu tamamen ayrı bir modüldür.
"""
import asyncio
import json
import re
from config import settings  # backend/config.py (tek Settings kaynagi)


async def generate_text(prompt: str, system_prompt: str = "") -> str:
    """
    LLM'den metin üretir.
    llm_mode=mock ise API key gerekmez.
    """
    if settings.llm_mode == "mock":
        return await _mock_generate(prompt, system_prompt)
    return await _live_generate(prompt, system_prompt)


async def _mock_generate(prompt: str, system_prompt: str) -> str:
    """API key olmadan test için sahte cevap üretir."""
    await asyncio.sleep(0.3)
    prompt_lower = prompt.lower()
    system_lower = system_prompt.lower()

    if "İHBAR_ANALİZİ" in system_prompt or "ihbarını analiz" in system_lower:
        return _mock_report_response(prompt_lower)

    if "SOKAK_GÜVENLİK_AÇIKLAMASI" in system_prompt or "güvenlik açıklaması" in system_lower:
        return _mock_street_response(prompt_lower)

    return '{"summary": "Mock LLM cevabı", "risk_score": 50, "category": "other", "severity": "medium"}'


def _mock_street_response(prompt_lower: str) -> str:
    # Prompt'taki "Toplam risk: X/100" degerini kullan
    match = re.search(r"toplam risk:\s*([\d.]+)", prompt_lower)
    total_risk = float(match.group(1)) if match else 50.0

    if "englewood" in prompt_lower or total_risk >= 70:
        return json.dumps({
            "summary": "Bu bolgede yuksek suc orani ve sik anlik ihbarlar var. Gece saatlerinde ozellikle dikkatli olun.",
            "risk_level": "critical",
            "factors": ["yuksek gecmis suc orani", "yogun anlik ihbarlar", "sosyal medya uyarilari"]
        }, ensure_ascii=False)

    if total_risk >= 40:
        return json.dumps({
            "summary": "Son donemde artan anlik ihbarlar dikkat cekiyor. Aydinlatma yetersiz olabilir.",
            "risk_level": "medium",
            "factors": ["artmis anlik ihbarlar", "gece aydinlatma sorunu"]
        }, ensure_ascii=False)

    if "lincoln" in prompt_lower or total_risk < 20:
        return json.dumps({
            "summary": "Genel olarak guvenli bir bolge. Dusuk risk seviyesi.",
            "risk_level": "low",
            "factors": ["dusuk suc orani", "az ihbar"]
        }, ensure_ascii=False)

    return json.dumps({
        "summary": "Bu bolgede orta duzeyde risk tespit edildi. Cevrenize dikkat edin.",
        "risk_level": "medium",
        "factors": ["gecmis suc verileri", "bolgesel risk profili"]
    }, ensure_ascii=False)


def _mock_report_response(prompt_lower: str) -> str:
    if any(w in prompt_lower for w in ["silah", "kavga", "cinayet", "saldırı"]):
        return json.dumps({
            "risk_score": 95,
            "summary": "Silahlı şiddet olayı bildirildi.",
            "category": "violent",
            "severity": "critical"
        }, ensure_ascii=False)

    if any(w in prompt_lower for w in ["taciz", "tacizde"]):
        return json.dumps({
            "risk_score": 90,
            "summary": "Taciz vakası bildirildi.",
            "category": "harassment",
            "severity": "critical"
        }, ensure_ascii=False)

    if any(w in prompt_lower for w in ["şüpheli", "araç"]):
        return json.dumps({
            "risk_score": 60,
            "summary": "Şüpheli aktivite rapor edildi.",
            "category": "suspicious",
            "severity": "medium"
        }, ensure_ascii=False)

    if any(w in prompt_lower for w in ["karanlık", "lamba", "ışık"]):
        return json.dumps({
            "risk_score": 30,
            "summary": "Aydınlatma ve çevre güvenliği sorunu bildirildi.",
            "category": "environmental",
            "severity": "low"
        }, ensure_ascii=False)

    if any(w in prompt_lower for w in ["köpek"]):
        return json.dumps({
            "risk_score": 25,
            "summary": "Sokakta tehlikeli hayvan bildirimi.",
            "category": "other",
            "severity": "low"
        }, ensure_ascii=False)

    return json.dumps({
        "risk_score": 40,
        "summary": "Genel güvenlik bildirimi.",
        "category": "other",
        "severity": "medium"
    }, ensure_ascii=False)


async def _live_generate(prompt: str, system_prompt: str) -> str:
    """Gerçek LLM API çağrısı — API key .env'den okunur."""
    if settings.llm_provider == "deepseek":
        return await _call_deepseek(prompt, system_prompt)
    if settings.llm_provider == "openai":
        return await _call_openai(prompt, system_prompt)
    if settings.llm_provider == "gemini":
        return await _call_gemini(prompt, system_prompt)
    raise ValueError(f"Bilinmeyen LLM sağlayıcı: {settings.llm_provider}")


async def _call_deepseek(prompt: str, system_prompt: str) -> str:
    """
    DeepSeek API çağrısı.
    DeepSeek, OpenAI uyumlu API kullanır (base_url farklı).
    """
    try:
        from openai import AsyncOpenAI
    except ImportError:
        raise ImportError("openai paketi yüklü değil: pip install openai")

    if not settings.deepseek_api_key:
        raise ValueError("DEEPSEEK_API_KEY .env dosyasında tanımlı değil")

    client = AsyncOpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
    )
    response = await client.chat.completions.create(
        model=settings.deepseek_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content


async def _call_openai(prompt: str, system_prompt: str) -> str:
    try:
        from openai import AsyncOpenAI
    except ImportError:
        raise ImportError("openai paketi yüklü değil: pip install openai")

    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY .env dosyasında tanımlı değil")

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content


async def _call_gemini(prompt: str, system_prompt: str) -> str:
    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError:
        raise ImportError("google-genai paketi yüklü değil: pip install google-genai")

    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY .env dosyasında tanımlı değil")

    client = genai.Client(api_key=settings.gemini_api_key)

    full_prompt = (
        f"{system_prompt}\n\n{prompt}\n\n"
        "ONEMLI: Yanitin SADECE gecerli JSON olsun. Markdown veya aciklama ekleme."
    )

    def _generate():
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=full_prompt,
            config=genai_types.GenerateContentConfig(
                temperature=settings.llm_temperature,
                max_output_tokens=settings.llm_max_tokens,
                response_mime_type="application/json",
            ),
        )
        return response

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = await asyncio.to_thread(_generate)
            text = _extract_gemini_text(response)
            if not text:
                raise ValueError("Gemini bos cevap dondurdu")
            return text
        except Exception as e:
            error_msg = str(e).lower()
            is_rate_limit = "429" in error_msg or "quota" in error_msg or "resource_exhausted" in error_msg
            is_daily_quota = "perday" in error_msg or "per_day" in error_msg
            if is_rate_limit and attempt < max_retries - 1 and not is_daily_quota:
                retry_match = re.search(r"retry in ([\d.]+)s", error_msg)
                wait_seconds = int(float(retry_match.group(1))) + 2 if retry_match else 15 * (attempt + 1)
                print(f"[Gemini] Kota limiti, {wait_seconds}s bekleniyor... (deneme {attempt + 2}/{max_retries})")
                await asyncio.sleep(wait_seconds)
                continue
            if is_daily_quota:
                raise RuntimeError(
                    "Gemini gunluk ucretsiz kota doldu. "
                    "Yarin tekrar deneyin veya .env dosyasinda LLM_MODE=mock yapin."
                ) from e
            raise


def _extract_gemini_text(response) -> str:
    """Gemini response nesnesinden metin cikarir."""
    try:
        if response.text:
            return response.text
    except Exception:
        pass

    if hasattr(response, "candidates") and response.candidates:
        candidate = response.candidates[0]
        if hasattr(candidate, "content") and candidate.content and candidate.content.parts:
            return "".join(part.text for part in candidate.content.parts if hasattr(part, "text"))

    return ""
