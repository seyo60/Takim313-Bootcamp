"""Kırmızı koridor yerine makul yeşil/sarı sapmayı seçme regresyon testleri."""

import numpy as np

from routing_cost import risk_adjusted_length, risk_adjusted_lengths


def test_red_corridor_penalty_beats_reasonable_green_detour():
    """Eski doğrusal formülün seçtiği kırmızı kestirme artık seçilmemelidir.

    Kırmızı doğrudan yol: 100 m, risk=0.95
    Yeşil sapma: 2 x 130 m, risk=0.10

    Eski formülde kırmızı maliyet 290, yeşil maliyet 312 idi. Bu nedenle
    kullanıcı kırmızı koridorda kalıyordu. Yeni bariyer kırmızıyı caydırır.
    """
    red_direct = risk_adjusted_length(100.0, 0.95)
    green_detour = 2.0 * risk_adjusted_length(130.0, 0.10)

    assert red_direct > green_detour
    assert green_detour == 312.0


def test_below_red_threshold_preserves_linear_calibration():
    assert abs(risk_adjusted_length(100.0, 0.10) - 120.0) < 1e-9
    assert abs(risk_adjusted_length(100.0, 0.60) - 220.0) < 1e-9


def test_red_penalty_is_monotonic_and_strong():
    costs = [risk_adjusted_length(100.0, risk) for risk in (0.1, 0.4, 0.6, 0.8, 1.0)]
    assert costs == sorted(costs)
    assert costs[-1] >= 4.0 * costs[0]


def test_vectorized_compact_cost_matches_scalar_networkx_cost():
    lengths = np.array([80.0, 100.0, 250.0], dtype=np.float32)
    risks = np.array([0.10, 0.65, 0.95], dtype=np.float32)

    vectorized = risk_adjusted_lengths(lengths, risks)
    scalar = np.array(
        [risk_adjusted_length(float(length), float(risk)) for length, risk in zip(lengths, risks)]
    )

    np.testing.assert_allclose(vectorized, scalar, rtol=1e-7, atol=1e-7)


def test_unknown_risk_is_not_treated_as_perfectly_safe():
    unknown_cost = risk_adjusted_length(100.0, 0.25)
    known_green_cost = risk_adjusted_length(100.0, 0.05)
    assert unknown_cost > known_green_cost
