"""Rota LLM açıklamasının neden deterministik fallback'e düştüğünü gösterir.

llm_service içindeki geniş except bloğu üretimde fail-closed davranış için
gereklidir; bu script aynı isteği tekrarlayıp hatanın kaynağını yazdırır.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from config import settings  # noqa: E402
from llm_service import RiskExplanation  # noqa: E402


DETERMINISTIC_LEVEL = "low_medium"


async def main() -> int:
    print(f"llm_mode={settings.llm_mode} provider={settings.llm_provider}")
    print(f"model={settings.deepseek_model} key_var={bool(settings.deepseek_api_key)}")

    system_prompt = (
        "You explain aggregate pedestrian risk signals for a walking route. "
        "Return only one valid JSON object. Use exactly this JSON shape: "
        '{"risk_level":"low|low_medium|medium|high|very_high",'
        '"explanation":"Turkish explanation","factors":["factor"]}. '
        "Describe the route as a whole, not a single spot. Do not claim certainty, "
        "safety, or danger-free conditions, and never tell the user a route is safe. "
        "Do not invent facts or street names."
    )
    user_prompt = (
        "Return JSON in Turkish describing this walking route's aggregate risk. "
        "Route-averaged canonical inputs (0..1): crime=0.2800, "
        "lighting=0.1500, community=0.0000, weighted_total=0.2465.\n"
        "Profile requested: safer. Route length: 6812 meters, "
        "10.5% longer than the shortest route, and the estimated risk "
        "is 55.0% lower than the shortest route. About 19.6% of the route length "
        "falls in higher-risk cells.\n"
        f"The deterministic level that must not change is: {DETERMINISTIC_LEVEL}."
    )

    body = {
        "model": settings.deepseek_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled"},
        "temperature": settings.llm_temperature,
        "max_tokens": min(settings.llm_max_tokens, 512),
        "stream": False,
    }
    url = f"{settings.deepseek_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.deepseek_api_key}",
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0)) as client:
        response = await client.post(url, headers=headers, json=body)
        print(f"\nHTTP {response.status_code}")
        if response.status_code != 200:
            print(response.text[:800])
            return 1
        payload = response.json()

    choice = payload["choices"][0]
    print(f"finish_reason={choice.get('finish_reason')}")
    raw = choice["message"]["content"]
    print(f"\nHAM YANIT:\n{raw}\n")

    try:
        parsed = RiskExplanation.model_validate_json(raw)
    except Exception as exc:  # teşhis amaçlı geniş yakalama
        print(f"DOĞRULAMA HATASI: {type(exc).__name__}")
        print(str(exc)[:1200])
        try:
            as_dict = json.loads(raw)
            print(f"\nrisk_level='{as_dict.get('risk_level')}' "
                  f"(beklenen '{DETERMINISTIC_LEVEL}')")
            print(f"explanation uzunluk={len(str(as_dict.get('explanation', '')))}")
            print(f"factors sayısı={len(as_dict.get('factors') or [])}")
        except Exception:
            print("Yanıt JSON olarak ayrıştırılamadı.")
        return 1

    print(f"DOĞRULAMA BAŞARILI: level={parsed.risk_level}")
    if parsed.risk_level != DETERMINISTIC_LEVEL:
        print("ANCAK: risk_level deterministik seviyeden farklı -> fallback tetiklenir")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
