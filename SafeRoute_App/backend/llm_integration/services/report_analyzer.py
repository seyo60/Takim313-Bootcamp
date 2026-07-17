# llm-integration/services/report_analyzer.py
"""
Görev 2 (1. kısım): Kullanıcı ihbarını LLM ile analiz eder.
Metinden risk skoru, kategori ve kısa özet üretir.

Şimdilik: mock JSON'dan UserReport alır.
Sonra:    reports tablosuna yazılır (repository katmanı eklenecek).
"""
import h3
from ..schemas.types import UserReport, ReportAnalysisResult
from .llm_client import generate_text
from config import settings  # backend/config.py (tek Settings kaynagi)
from ..prompts.guardrails import (
    REPORT_ANALYZER_PROMPT,
    REPORT_ANALYZER_PROMPT_COMPACT,
    validate_llm_output,
)

H3_RESOLUTION = 9


async def analyze_report(report: UserReport) -> ReportAnalysisResult:
    """
    Kullanıcı ihbarını analiz eder.

    Args:
        report: Kullanıcının gönderdiği ihbar (metin + konum + opsiyonel puan)

    Returns:
        ReportAnalysisResult: LLM analiz sonucu
    """
    prompt = _build_prompt(report)
    system_prompt = REPORT_ANALYZER_PROMPT_COMPACT if settings.llm_mode == "live" else REPORT_ANALYZER_PROMPT
    raw_response = await generate_text(prompt, system_prompt)
    parsed = validate_llm_output(raw_response, task="report")

    h3_index = h3.latlng_to_cell(report.latitude, report.longitude, H3_RESOLUTION)

    llm_score = float(parsed["risk_score"])

    # Kullanıcı puan verdiyse LLM skoru ile ortalama al
    if report.user_score is not None:
        final_score = (llm_score + report.user_score) / 2
    else:
        final_score = llm_score

    return ReportAnalysisResult(
        risk_score=round(final_score, 1),
        summary=parsed["summary"],
        category=parsed["category"],
        severity=parsed["severity"],
        h3_index=h3_index,
    )


def _build_prompt(report: UserReport) -> str:
    parts = [
        f"Konum: ({report.latitude}, {report.longitude})",
        f"İhbar metni: {report.text}",
    ]
    if report.user_score is not None:
        parts.append(f"Kullanıcının verdiği suç puanı: {report.user_score}/100")
    parts.append("Bu ihbarı analiz et. Sadece verilen bilgilere dayan.")
    return "\n".join(parts)
