# backend/measure_standalone_csr_ram.py
"""
Sadece CompactCSREngine yüklendiğindeki temiz süreç RSS RAM tüketimini ölçen doğrulama betiği.
"""

import os
import psutil
import time
from routing_engine import CompactCSREngine


def measure_standalone():
    process = psutil.Process(os.getpid())
    ram_start = process.memory_info().rss / (1024 * 1024)

    t0 = time.time()
    engine = CompactCSREngine()
    engine.load_graph("../data-science/compact_graph.npz")

    # Örnek 5.336 H3 hücresi riskini yükleme simülasyonu
    fake_risk_lookup = {f"cell_{i}": 0.5 for i in range(5336)}
    engine.apply_risk_weights(fake_risk_lookup, alpha=2.0)
    t1 = time.time()

    ram_end = process.memory_info().rss / (1024 * 1024)
    ram_net = ram_end - ram_start

    print("=" * 60)
    print("STANDALONE COMPACT CSR ENGINE PROCESS RSS RAM MESURMENT")
    print("=" * 60)
    print(f"Başlangıç Python Taban RSS RAM : {ram_start:.2f} MB")
    print(f"CompactCSREngine Sonrası RSS RAM : {ram_end:.2f} MB")
    print(f"CompactCSREngine Net Bellek Yükü: {ram_net:.2f} MB")
    print(f"Toplam Başlatma Süresi         : {t1 - t0:.3f} saniye")
    print(f"512 MB Container Limit Kontrolü : {'BAŞARILI (< 400 MB)' if ram_end < 400.0 else 'UYARI'}")
    print("=" * 60)


if __name__ == "__main__":
    measure_standalone()
