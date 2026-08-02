import type { RiskLevel, StreetRiskExplanation } from "./types";

export function riskLevelFromScore(score: number): RiskLevel {
  if (score <= 20) return "low";
  if (score <= 40) return "low_medium";
  if (score <= 60) return "medium";
  if (score <= 80) return "high";
  return "very_high";
}

const CONTENT: Record<
  RiskLevel,
  { explanation: string; factors: string[] }
> = {
  no_data: {
    explanation: "Bu bölge için yeterli risk verisi bulunmuyor.",
    factors: ["Tarihsel suç verisi yok", "Aydınlatma arıza bildirimi yok"],
  },
  low: {
    explanation:
      "Bu bölgede gözlemlenen risk verileri düşük seviyededir. Rutin güvenlik önlemlerinize devam edin.",
    factors: ["İyi sokak aydınlatması", "Yoğun yaya trafiği"],
  },
  low_medium: {
    explanation:
      "Bu bölgede düşük-orta seviyede risk kaydedilmiştir. Çevrenize karşı dikkatli olmanız önerilir.",
    factors: ["Kısmi suç geçmişi", "Kısmen zayıf aydınlatma"],
  },
  medium: {
    explanation:
      "Bu bölgede orta seviyede risk kaydedilmiştir. Çevrenize karşı dikkatli olmanız önerilir.",
    factors: ["Kısmen zayıf aydınlatma", "Akşam saatlerinde tenhalaşan sokaklar"],
  },
  high: {
    explanation:
      "Bu bölgede yüksek suç yoğunluğu veya aydınlatma yetersizliği gözlemlenmiştir. Alternatif güvenli rotayı tercih edin.",
    factors: ["Yüksek suç geçmişi", "Zayıf aydınlatma", "Tenha ara sokaklar"],
  },
  very_high: {
    explanation:
      "Bu bölge çok yüksek derecede risklidir. Gece yalnız yürümekten kaçının ve kalabalık güzergahları kullanın.",
    factors: ["Yüksek suç yoğunluğu", "Çok zayıf aydınlatma", "Canlı bildirimler"],
  },
};

export function buildMockStreetRisk(totalRisk: number): StreetRiskExplanation {
  const total = Math.max(0, Math.min(100, Math.round(totalRisk)));
  const level = riskLevelFromScore(total);
  const { explanation, factors } = CONTENT[level];

  const crime = Math.round(total * 0.65);
  const lighting = Math.round(total * 0.20);
  const live = Math.round(total * 0.15);

  return {
    risk_level: level,
    explanation,
    factors,
    channels: { crime, lighting, live, total },
    total_risk: total / 100.0,
    crime_risk: crime / 100.0,
    lighting_risk: lighting / 100.0,
    live_risk: live / 100.0,
    data_available: true,
    observed_risk_level: level === "low_medium" ? "Düşük-Orta Gözlemlenen Risk" : "Gözlemlenen Risk",
    disclaimer: "Güvenlik skoru kesin güvenlik garantisi değildir.",
  };
}
