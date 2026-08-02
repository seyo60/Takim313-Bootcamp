"""SafeRoute rota maliyeti için tek ve motor-bağımsız doğruluk kaynağı.

Dahili risk ölçeği daima 0.0–1.0 aralığındadır. Temel risk cezasına ek
olarak kırmızı eşikten sonraki risk, karesel bir bariyerle cezalandırılır.
Bu sayede rota motoru küçük bir mesafe kazancı uğruna uzun bir yüksek-risk
koridorunda kalmaz.
"""

from __future__ import annotations

import math
from typing import TypeVar

import numpy as np


DEFAULT_RISK_ALPHA = 2.0
DEFAULT_RED_RISK_THRESHOLD = 0.60
DEFAULT_RED_RISK_PENALTY = 6.0
DEFAULT_UNKNOWN_RISK = 0.25

ArrayLike = TypeVar("ArrayLike", float, np.ndarray)


def normalize_risk(risk: float) -> float:
    """Sonlu bir risk değerini kanonik 0.0–1.0 aralığına getirir."""
    value = float(risk)
    if not math.isfinite(value):
        raise ValueError(f"Risk sonlu olmalıdır: {risk!r}")
    return max(0.0, min(1.0, value))


def risk_cost_multiplier(
    risk: float,
    *,
    alpha: float = DEFAULT_RISK_ALPHA,
    red_threshold: float = DEFAULT_RED_RISK_THRESHOLD,
    red_penalty: float = DEFAULT_RED_RISK_PENALTY,
) -> float:
    """Bir kenarın fiziksel uzunluğuna uygulanacak güvenlik çarpanını döndürür.

    Formül:

        multiplier = 1 + alpha*r
                     + red_penalty * max(0, (r-T)/(1-T))^2

    ``T`` kırmızı risk eşiğidir. Eşiğin altında maliyet mevcut doğrusal
    davranışı korur; eşiğin üstünde ceza kademeli fakat güçlü biçimde artar.
    """
    if alpha < 0.0:
        raise ValueError("alpha negatif olamaz")
    if red_penalty < 0.0:
        raise ValueError("red_penalty negatif olamaz")
    if not 0.0 <= red_threshold < 1.0:
        raise ValueError("red_threshold 0.0 <= T < 1.0 olmalıdır")

    normalized = normalize_risk(risk)
    red_excess = max(0.0, (normalized - red_threshold) / (1.0 - red_threshold))
    return 1.0 + alpha * normalized + red_penalty * red_excess * red_excess


def risk_adjusted_length(
    length: float,
    risk: float,
    *,
    alpha: float = DEFAULT_RISK_ALPHA,
    red_threshold: float = DEFAULT_RED_RISK_THRESHOLD,
    red_penalty: float = DEFAULT_RED_RISK_PENALTY,
) -> float:
    """Tek bir kenarın risk ayarlı maliyetini metre eşdeğerinde hesaplar."""
    physical_length = max(0.0, float(length))
    return physical_length * risk_cost_multiplier(
        risk,
        alpha=alpha,
        red_threshold=red_threshold,
        red_penalty=red_penalty,
    )


def risk_adjusted_lengths(
    lengths: np.ndarray,
    risks: np.ndarray,
    *,
    alpha: float = DEFAULT_RISK_ALPHA,
    red_threshold: float = DEFAULT_RED_RISK_THRESHOLD,
    red_penalty: float = DEFAULT_RED_RISK_PENALTY,
) -> np.ndarray:
    """Compact CSR motoru için vektörleştirilmiş risk maliyeti hesabı."""
    if alpha < 0.0:
        raise ValueError("alpha negatif olamaz")
    if red_penalty < 0.0:
        raise ValueError("red_penalty negatif olamaz")
    if not 0.0 <= red_threshold < 1.0:
        raise ValueError("red_threshold 0.0 <= T < 1.0 olmalıdır")

    safe_lengths = np.maximum(np.asarray(lengths, dtype=np.float64), 0.0)
    raw_risks = np.asarray(risks, dtype=np.float64)
    if not np.all(np.isfinite(raw_risks)):
        raise ValueError("Tüm risk değerleri sonlu olmalıdır")
    safe_risks = np.clip(raw_risks, 0.0, 1.0)
    red_excess = np.maximum(0.0, (safe_risks - red_threshold) / (1.0 - red_threshold))
    multiplier = 1.0 + alpha * safe_risks + red_penalty * np.square(red_excess)
    return safe_lengths * multiplier
