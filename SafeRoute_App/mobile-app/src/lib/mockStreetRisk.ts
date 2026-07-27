/**
 * Local mock for the backend LLM endpoint
 * `POST /api/v1/street-risk-explanation` (item 2). Shapes match
 * src/lib/types.ts, so swapping to the real backend only means flipping
 * USE_MOCK_STREET_RISK in src/lib/api.ts — the UI never changes.
 *
 * The real endpoint runs an LLM over the risk channels (historical / live /
 * social) and returns a short Turkish rationale. Here we synthesize a
 * plausible response from the selected route's risk score so the toggle
 * (safe ⇄ shortest) visibly changes the explanation during the demo.
 *
 * TODO(osman): remove once Seymen's street-risk-explanation endpoint is live
 * (flip USE_MOCK_STREET_RISK in api.ts).
 */

import type { RiskLevel, StreetRiskExplanation } from "./types";

/**
 * The exact safe answer the backend's guardrails return when the LLM output
 * violates the rules or there is not enough data (guardrails.py →
 * get_fallback_street_response). Mirrored verbatim so the UI's
 * insufficient-data detection works identically in mock and live modes.
 */
export function buildGuardrailFallback(): StreetRiskExplanation {
  return {
    summary:
      "Bu bölge için yeterli güvenlik verisi bulunmuyor. Çevrenize dikkat edin.",
    risk_level: "medium",
    factors: ["sınırlı veri"],
  };
}

/**
 * True when the explanation is the guardrails' safe fallback rather than a
 * real analysis (item 6): the "sınırlı veri" factor is the backend's marker.
 * Shown as a neutral info card instead of a confident risk badge.
 */
export function isInsufficientData(
  explanation: StreetRiskExplanation
): boolean {
  return explanation.factors.some(
    (factor) => factor.trim().toLowerCase() === "sınırlı veri"
  );
}

/** Maps a 0-100 total risk score to the badge level (thresholds are a UI choice). */
export function riskLevelFromScore(score: number): RiskLevel {
  if (score <= 25) return "low";
  if (score <= 50) return "medium";
  if (score <= 75) return "high";
  return "critical";
}

/**
 * Pre-written explanation + factors per level. Text is kept to ≤2 sentences
 * (AC #2) and factors to ≤3 items (AC #3) — the real LLM output is expected to
 * respect the same limits (or the UI clamps them; see clampExplanation).
 */
const CONTENT: Record<
  RiskLevel,
  { summary: string; factors: string[] }
> = {
  low: {
    summary:
      "Bu rota büyük ölçüde güvenli. Aydınlatma iyi ve son dönemde kayda değer bir olay bildirilmemiş.",
    factors: ["İyi sokak aydınlatması", "Yoğun yaya trafiği"],
  },
  medium: {
    summary:
      "Bu rotada orta düzeyde risk var. Bazı kesimlerde aydınlatma zayıf ve akşam saatlerinde tenhalaşıyor.",
    factors: [
      "Kısmen zayıf aydınlatma",
      "Akşam saatlerinde az yaya",
      "Son ayda 1 küçük olay",
    ],
  },
  high: {
    summary:
      "Bu rota riskli sayılıyor. Son 3 ayda birden fazla olay bildirilmiş ve bazı sokaklar loş.",
    factors: [
      "Zayıf aydınlatma",
      "Son 3 ayda 2 hırsızlık",
      "Tenha ara sokaklar",
    ],
  },
  critical: {
    summary:
      "Bu rota yüksek riskli. Yakın zamanda ciddi olaylar bildirilmiş; mümkünse güvenli rotayı tercih edin.",
    factors: [
      "Yakın zamanda saldırı bildirimi",
      "Çok zayıf aydınlatma",
      "Yüksek suç yoğunluğu",
    ],
  },
};

/**
 * Builds a fake StreetRiskExplanation from a route's total risk score. Splits
 * the total into plausible historical/live/social channels so the breakdown
 * row has real numbers to show.
 */
export function buildMockStreetRisk(totalRisk: number): StreetRiskExplanation {
  const total = Math.max(0, Math.min(100, Math.round(totalRisk)));
  const level = riskLevelFromScore(total);
  const { summary, factors } = CONTENT[level];

  // Distribute the total across channels (weights are illustrative only).
  const historical = Math.round(total * 0.6);
  const live = Math.round(total * 0.25);
  const social = Math.max(0, total - historical - live);

  return {
    risk_level: level,
    summary,
    factors,
    channels: { historical, live, social, total },
  };
}
