# backend/llm_service.py
import asyncio

async def analyze_report_risk_with_llm(text: str) -> float:
    """
    Mehmet Ali'nin LLM entegrasyonunu yapacağı asıl fonksiyon burası olacak.
    Şimdilik sistemi bloklamamak için mock (sahte) bir yapı kuruyoruz.
    """
    # TODO: Gerçek LLM API çağrısı buraya gelecek (OpenAI, Gemini, vb.)
    # Örneğin: response = await llm_client.predict(text)
    
    # LLM'in düşünme süresini simüle ediyoruz (Burası API'yi asla bloklamamalı)
    await asyncio.sleep(1.5) 
    
    text_lower = text.lower()
    
    # Basit bir kural tabanlı mock (İleride yerini LLM alacak)
    if any(word in text_lower for word in ["silah", "bıçak", "saldırı", "taciz", "çatışma"]):
        return 100.0  # Kesinlikle o sokağa sokma
    elif any(word in text_lower for word in ["kavga", "tehlike", "şüpheli", "köpek"]):
        return 50.0   # Mümkünse alternatif rotaya sap
    elif any(word in text_lower for word in ["karanlık", "lamba", "ıssız"]):
        return 20.0   # Sadece küçük bir ceza puanı
    else:
        return 10.0   # Varsayılan düşük risk