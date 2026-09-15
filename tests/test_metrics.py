"""Tests de core/metrics.py — XIRR."""

import datetime as dt

import numpy as np
import pytest

from core.metrics import calculate_xirr


def d(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def test_xirr_lump_sum_one_year():
    """+10% sur 1 an -> XIRR = 10%"""
    rate = calculate_xirr([-100, 110], [d("2023-01-01"), d("2024-01-01")])
    assert rate == pytest.approx(10.0, abs=1e-6)


def test_xirr_lump_sum_three_years():
    """+33.1% sur 3 ans -> XIRR ~ 10%/an"""
    rate = calculate_xirr([-100, 133.1], [d("2020-01-01"), d("2023-01-01")])
    assert rate == pytest.approx(9.99, abs=0.01)


def test_xirr_loss():
    rate = calculate_xirr([-100, 50], [d("2023-01-01"), d("2024-01-01")])
    assert rate == pytest.approx(-50.0, abs=1e-6)


def test_xirr_near_total_loss():
    rate = calculate_xirr([-100, 1], [d("2023-01-01"), d("2024-01-01")])
    assert rate == pytest.approx(-99.0, abs=1e-6)


def test_xirr_large_gain():
    """900% : ce genre de rendement extrême a fait échouer l'ancienne implémentation
    basée sur Newton (recherche non bornée), remplacée par une recherche par
    intervalle (brentq) — voir le commentaire dans core/metrics.py."""
    rate = calculate_xirr([-100, 1000], [d("2023-01-01"), d("2024-01-01")])
    assert rate == pytest.approx(900.0, abs=1e-3)


def test_xirr_no_negative_flow_returns_zero():
    """Pas de flux négatif -> pas de racine possible -> 0.0, pas d'exception."""
    assert calculate_xirr([100, 50], [d("2023-01-01"), d("2024-01-01")]) == 0.0


def test_xirr_all_negative_returns_zero():
    assert calculate_xirr([-100, -50], [d("2023-01-01"), d("2024-01-01")]) == 0.0


def test_xirr_single_flow_returns_zero():
    assert calculate_xirr([-100], [d("2023-01-01")]) == 0.0


def test_xirr_crash_period_converges():
    """
    Cas qui faisait échouer silencieusement l'ancienne implémentation (Newton
    partant de +10% ne convergeait pas vers une racine très négative, et
    renvoyait 0.0 au lieu du vrai résultat). Mesuré sur SPY 2006-2009 :
    XIRR réel ≈ -24.78%.
    """
    cashflows = [-100] * 36 + [1050]  # 36 versements mensuels, perte finale
    dates = [d("2006-01-01") + dt.timedelta(days=30 * i) for i in range(36)]
    dates.append(d("2009-01-29"))
    rate = calculate_xirr(cashflows, dates)
    assert rate < 0, f"attendu un XIRR négatif (perte), reçu {rate}"
    assert np.isfinite(rate)


def test_xirr_mismatched_lengths_raises():
    with pytest.raises(ValueError):
        calculate_xirr([-100, 100], [d("2023-01-01")])
