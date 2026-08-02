# backend/services/report_nlp.py
"""
SafeRoute NLP Analiz Servisi.

Kullanıcı ihbarlarının metin analizi, kategoriye dönüştürülmesi, ciddiyet
ağırlığı (severity_weight), kategori güveni (category_confidence) ve metinsel
benzerlik (text_similarity) hesaplamalarını yürütür.

Desteklenen Modlar (REPORT_NLP_MODE):
- deterministic: Varsayılan güvenli fallback (MiniLM yüklenmez/import edilmez).
- shadow: Fallback ve MiniLM birlikte hesaplanır, ancak üretim kararları (kümeleme,
  doğrulama skoru V, accepted kararı, risk_live) yalnızca güvenli fallback ile çalışır.
- minilm: Yalnızca model kurulu ve kalibre edildikten sonra kullanılacak mod.
"""
from dataclasses import dataclass, field
import math
import re
from typing import Optional

from config import settings
from errors import ConfigurationError

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# --- TEK DOĞRULUK KAYNAĞI: KATEGORİ CİDDİYET AĞIRLIKLARI ---
CATEGORY_SEVERITY_WEIGHTS = {
    "armed_violence": 1.00,
    "assault": 0.90,
    "robbery": 0.85,
    "harassment": 0.65,
    "traffic_accident": 0.60,
    "suspicious_activity": 0.50,
    "infrastructure_hazard": 0.45,
    "general_safety": 0.35,
    "lighting_failure": 0.30,
}

# İhbar değeri taşımayan / konu dışı metinler (bildirim ve onay akışına girmez).
OFF_TOPIC_KEYWORDS = [
    "siyaset", "siyasi", "seçim", "secim", "parti", "milletvekili", "cumhurbaşkan",
    "cumhurbaskan", "oy ver", "propaganda", "reklam", "kupon", "bahis", "iddaa",
    "maç skoru", "mac skoru", "bitcoin", "kripto", "nft", "follow me", "subscribe",
    "onlyfans", "porno", "sex", "nudes",
]

# Deterministik Anahtar Kelime Haritası (Türkçe ve İngilizce)
KEYWORD_CATEGORY_MAP = {
    # Türkçe ekli varyantlar açıkça listelenir: "silahlı" gibi biçimler kelime
    # sınırı araması ("silah") ile tam puan almaz ve ciddiyeti yüksek kategori
    # zayıf genel kelimelere yenilebilir.
    "armed_violence": ["silah", "silahlı", "silahli", "çatışma", "catisma", "saldırı", "ateş", "bıçak", "bıçaklı", "pompali", "kurşun", "vuruldu", "gun", "gunshot", "weapon", "shooting", "armed", "shooter"],
    "assault": ["darp", "kavga", "dayak", "saldırdı", "fiziksel", "fight", "fighting", "assault", "attack", "beaten", "altercation", "brawl", "brawling", "punched"],
    "robbery": ["gasp", "hırsız", "soygun", "çaldı", "kapkaç", "robbery", "stole", "mugging", "thief", "robbed", "burglary"],
    "harassment": ["taciz", "takip", "lafa tuttu", "sözlü", "harassment", "stalking", "following", "followed", "verbal abuse"],
    "traffic_accident": ["kaza", "çarpışma", "araç", "devrildi", "accident", "crash", "car crash", "collision", "hit and run"],
    "suspicious_activity": ["şüpheli", "tehlikeli", "garip", "şahıs", "suspicious", "weird", "danger", "loitering", "prowler"],
    "infrastructure_hazard": ["çukur", "kablo", "yıkık", "duvar", "hazard", "hole", "danger zone", "debris", "pothole", "broken sidewalk"],
    "lighting_failure": ["karanlık", "lamba", "ışık", "sönük", "zifiri", "dark", "darkness", "light out", "no light", "lights out", "unlit", "street lights not working"],
}


@dataclass
class ReportNLPResult:
    normalized_category: str
    severity_weight: float
    category_confidence: float
    is_actionable: bool = True
    rejection_reason: Optional[str] = None
    analysis_method: str = "deterministic_fallback"
    text_similarity: float = 0.0
    embedding_available: bool = False
    model_status: str = "disabled"
    embedding: Optional[list[float]] = field(default=None, repr=False)
    shadow_minilm_result: Optional[dict] = field(default=None, repr=False)

    @property
    def model_confidence(self) -> float:
        """Geriye dönük uyumluluk için alias."""
        return self.category_confidence


class ReportNLPAnalyzer:
    _instance: Optional["ReportNLPAnalyzer"] = None

    def __init__(self):
        self._model = None
        self._model_status: str = "disabled"  # disabled, not_installed, loading, ready, load_failed
        self._load_attempted = False

    @classmethod
    def get_instance(cls) -> "ReportNLPAnalyzer":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _lazy_load_model(self, mode: str = "deterministic") -> bool:
        norm_mode = (mode or "deterministic").lower().strip()
        if norm_mode == "deterministic":
            # Deterministic mode must not discard the state of an already loaded
            # model.  The public result/health contract still reports
            # ``disabled`` for deterministic mode, while preserving a ready
            # model if the process is switched back to shadow mode.
            return False

        if self._load_attempted:
            return self._model_status == "ready"

        self._load_attempted = True
        self._model_status = "loading"

        try:
            from sentence_transformers import SentenceTransformer
        except (ImportError, ModuleNotFoundError):
            self._model = None
            self._model_status = "not_installed"
            print("[SafeRoute NLP] sentence-transformers paketi yüklü değil. NLP deterministik fallback kullanıyor.")
            return False

        try:
            self._model = SentenceTransformer(MODEL_NAME)
            self._model_status = "ready"
            print(f"[SafeRoute NLP] MiniLM modeli başarıyla yüklendi ({MODEL_NAME}).")
            return True
        except Exception as e:
            self._model = None
            self._model_status = "load_failed"
            print(f"[SafeRoute NLP] MiniLM model yükleme hatası ({type(e).__name__}). NLP deterministik fallback'e geçiyor.")
            return False

    def analyze(self, text: str) -> ReportNLPResult:
        clean_text = (text or "").strip()
        mode = str(getattr(settings, "report_nlp_mode", "deterministic")).lower().strip()

        if not clean_text or len(clean_text) < 3:
            return ReportNLPResult(
                normalized_category="general_safety",
                severity_weight=CATEGORY_SEVERITY_WEIGHTS["general_safety"],
                category_confidence=0.10,
                is_actionable=False,
                rejection_reason="Metin çok kısa veya geçersiz.",
                analysis_method="deterministic_fallback",
                embedding_available=False,
                model_status="disabled" if mode == "deterministic" else self._model_status,
                embedding=None,
            )

        category, confidence, had_keyword = self._categorize_text(clean_text)
        severity = CATEGORY_SEVERITY_WEIGHTS.get(category, 0.35)
        actionable, reject_reason = self._assess_actionable(
            clean_text, category=category, confidence=confidence, had_keyword=had_keyword
        )

        if mode == "deterministic":
            self._lazy_load_model("deterministic")
            return ReportNLPResult(
                normalized_category=category,
                severity_weight=severity,
                category_confidence=confidence,
                is_actionable=actionable,
                rejection_reason=reject_reason,
                analysis_method="deterministic_fallback",
                embedding_available=False,
                model_status="disabled",
                embedding=None,
                shadow_minilm_result=None,
            )

        elif mode == "shadow":
            has_model = self._lazy_load_model("shadow")
            shadow_res = None
            if has_model and self._model is not None:
                try:
                    emb = self._model.encode([clean_text], convert_to_numpy=True)[0]
                    shadow_res = {
                        "embedding_available": True,
                        "analysis_method": "multilingual_embedding",
                        "category": category,
                        "confidence": confidence,
                        "embedding_dim": len(emb.tolist()),
                    }
                except Exception:
                    shadow_res = {
                        "embedding_available": False,
                        "analysis_method": "deterministic_fallback",
                        "error": "embedding_encode_failed"
                    }

            # Shadow modunda birincil alanlar KESİNLİKLE deterministik fallback değerlerini korur
            return ReportNLPResult(
                normalized_category=category,
                severity_weight=severity,
                category_confidence=confidence,
                is_actionable=actionable,
                rejection_reason=reject_reason,
                analysis_method="deterministic_fallback",
                embedding_available=False,
                model_status=self._model_status,
                embedding=None,
                shadow_minilm_result=shadow_res,
            )

        elif mode == "minilm":
            has_model = self._lazy_load_model("minilm")
            embedding = None
            analysis_method = "deterministic_fallback"
            embedding_available = False

            if has_model and self._model is not None:
                try:
                    emb = self._model.encode([clean_text], convert_to_numpy=True)[0]
                    embedding = emb.tolist()
                    analysis_method = "multilingual_embedding"
                    embedding_available = True
                except Exception:
                    analysis_method = "deterministic_fallback"

            return ReportNLPResult(
                normalized_category=category,
                severity_weight=severity,
                category_confidence=confidence,
                is_actionable=actionable,
                rejection_reason=reject_reason,
                analysis_method=analysis_method,
                embedding_available=embedding_available,
                model_status=self._model_status,
                embedding=embedding,
            )

        else:
            raise ConfigurationError(
                "Unsupported REPORT_NLP_MODE; expected deterministic, shadow, or minilm"
            )

    def similarity(self, text_a: str, text_b: str) -> float:
        a = (text_a or "").strip()
        b = (text_b or "").strip()

        if not a or not b:
            return 0.0
        if a.lower() == b.lower():
            return 1.0

        mode = str(getattr(settings, "report_nlp_mode", "deterministic")).lower().strip()
        fallback_sim = self._fallback_similarity(a, b)

        if mode == "deterministic":
            return fallback_sim

        elif mode == "shadow":
            has_model = self._lazy_load_model("shadow")
            # Shadow modunda MiniLM skoru hesaplanabilir fakat üretim kararlarını değiştirmemek için
            # birincil olarak fallback_sim döndürülür
            if has_model and self._model is not None:
                try:
                    embeddings = self._model.encode([a, b], convert_to_numpy=True)
                    vec_a, vec_b = embeddings[0], embeddings[1]
                    dot = float(sum(x * y for x, y in zip(vec_a, vec_b)))
                    norm_a = math.sqrt(float(sum(x * x for x in vec_a)))
                    norm_b = math.sqrt(float(sum(x * x for x in vec_b)))
                    if norm_a > 0 and norm_b > 0:
                        _shadow_sim = max(0.0, min(1.0, float(dot / (norm_a * norm_b))))
                except Exception:
                    pass
            return fallback_sim

        elif mode == "minilm":
            has_model = self._lazy_load_model("minilm")
            if has_model and self._model is not None:
                try:
                    embeddings = self._model.encode([a, b], convert_to_numpy=True)
                    vec_a, vec_b = embeddings[0], embeddings[1]
                    dot = float(sum(x * y for x, y in zip(vec_a, vec_b)))
                    norm_a = math.sqrt(float(sum(x * x for x in vec_a)))
                    norm_b = math.sqrt(float(sum(x * x for x in vec_b)))
                    if norm_a > 0 and norm_b > 0:
                        return max(0.0, min(1.0, float(dot / (norm_a * norm_b))))
                except Exception:
                    pass
            return fallback_sim

        return fallback_sim

    def get_health(self) -> dict:
        mode = str(getattr(settings, "report_nlp_mode", "deterministic")).lower().strip()
        if mode == "deterministic":
            status = "disabled"
        else:
            self._lazy_load_model(mode)
            status = self._model_status

        active_method = "deterministic_fallback"
        if mode == "minilm" and status == "ready":
            active_method = "multilingual_embedding"

        return {
            "configured_mode": mode,
            "model_status": status,
            "model_name": MODEL_NAME,
            "active_analysis_method": active_method,
            "fallback_available": True
        }

    def _assess_actionable(
        self,
        text: str,
        *,
        category: str,
        confidence: float,
        had_keyword: bool,
    ) -> tuple[bool, Optional[str]]:
        """Güvenlik ihbarı değeri taşımayan metinleri elemez (siyaset, spam, boş vs.)."""
        lower = text.lower()
        for kw in OFF_TOPIC_KEYWORDS:
            if kw in lower:
                return False, (
                    "Bu metin güvenlik ihbarı olarak değerlendirilmedi "
                    "(konu dışı içerik). Bildirim gönderilmedi."
                )

        # Placeholder / anlamsız kısa şablonlar
        placeholders = {
            "durum bildirimi (detay girilmedi)",
            "acil durum bildirimi (detay girilmedi)",
            "test",
            "asdf",
            "qwerty",
        }
        if lower.strip() in placeholders:
            return False, (
                "İhbar metni güvenlik sinyali taşımıyor. "
                "Ne olduğunu kısaca yazarak tekrar dene."
            )

        if not had_keyword:
            return False, (
                "Metinde tanınabilir bir güvenlik/tehlike sinyali bulunamadı. "
                "İhbar kaydedilmedi ve yakındakilere bildirim gitmedi."
            )

        if confidence < 0.35:
            return False, "İhbar güven skoru çok düşük; bildirim gönderilmedi."

        return True, None

    def _categorize_text(self, text: str) -> tuple[str, float, bool]:
        lower_text = text.lower()
        matched_scores: dict[str, float] = {}

        for cat, keywords in KEYWORD_CATEGORY_MAP.items():
            for kw in keywords:
                if re.search(r'\b' + re.escape(kw) + r'\b', lower_text):
                    matched_scores[cat] = matched_scores.get(cat, 0.0) + 1.0
                elif kw in lower_text:
                    matched_scores[cat] = matched_scores.get(cat, 0.0) + 0.5

        if matched_scores:
            # Eşit sinyal gücünde ciddiyeti yüksek kategori tercih edilir; aksi
            # halde "silahlı çatışma" içeren bir ihbar, genel bir kelime yüzünden
            # daha düşük ciddiyetli bir kategoriye düşebilir.
            best_cat = max(
                matched_scores,
                key=lambda cat: (
                    matched_scores[cat],
                    CATEGORY_SEVERITY_WEIGHTS.get(cat, 0.35),
                ),
            )
            score = matched_scores[best_cat]
            confidence = min(0.95, 0.60 + (score * 0.15))
            return best_cat, round(confidence, 2), True

        return "general_safety", 0.20, False

    def _fallback_similarity(self, text_a: str, text_b: str) -> float:
        words_a = set(re.findall(r'\w+', text_a.lower()))
        words_b = set(re.findall(r'\w+', text_b.lower()))

        word_jaccard = 0.0
        if words_a or words_b:
            word_jaccard = len(words_a & words_b) / float(len(words_a | words_b))

        def get_ngrams(s: str, n: int = 3) -> set[str]:
            s_clean = f" {s.lower().strip()} "
            return {s_clean[i:i+n] for i in range(len(s_clean) - n + 1)}

        ngrams_a = get_ngrams(text_a)
        ngrams_b = get_ngrams(text_b)

        ngram_jaccard = 0.0
        if ngrams_a or ngrams_b:
            ngram_jaccard = len(ngrams_a & ngrams_b) / float(len(ngrams_a | ngrams_b))

        hybrid_sim = (0.4 * word_jaccard) + (0.6 * ngram_jaccard)
        return max(0.0, min(1.0, round(hybrid_sim, 4)))


def get_nlp_analyzer() -> ReportNLPAnalyzer:
    return ReportNLPAnalyzer.get_instance()
