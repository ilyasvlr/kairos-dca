"""
Tests de core/backtester.py — les invariants qui comptent le plus :
  1. Conservation du capital (versé == budget × périodes)
  2. Absence de biais d'anticipation (causalité stricte)
  3. Déterminisme
  4. Validation des paramètres

Prix synthétiques (fixtures `prices`/`long_prices` de conftest.py) : aucun appel
réseau, résultats reproductibles, adapté à la CI.
"""

import pytest

from core.backtester import (
    Backtester,
    ClassicDCAStrategy,
    DrawdownDCAStrategy,
    RSIDCAStrategy,
    KairosScoreDCAStrategy,
    DryPowderDCAStrategy,
    VaultDCAStrategy,
)


def count_periods(strategy, index):
    strategy.reset()
    return sum(strategy._check_frequency(d) for d in index)


# ==============================================================================
# Conservation du capital
# ==============================================================================

@pytest.mark.parametrize("reserve,threshold,rearm", [
    (0.3, -0.20, False), (0.8, -0.60, True), (1.0, -0.30, False), (0.0, -0.20, False),
])
def test_drypowder_conserves_capital(prices, long_prices, reserve, threshold, rearm):
    strategy = DryPowderDCAStrategy(100, reserve, threshold, frequency='weekly', rearm=rearm)
    result = Backtester(prices, strategy, 0.001, None, long_prices).run()
    m = result['metrics']

    budget = 100 * count_periods(DryPowderDCAStrategy(100, reserve, threshold, frequency='weekly'), prices.index)
    assert m['total_invested'] == pytest.approx(budget, abs=1e-6)
    assert m['total_invested'] == pytest.approx(m['total_deployed'] + m['cash_reserve'], abs=1e-6)
    if not result['trades'].empty:
        assert result['trades']['cash_reserve'].min() >= -1e-9


@pytest.mark.parametrize("indicator", ['drawdown', 'rsi', 'vix', 'fear_greed'])
@pytest.mark.parametrize("rearm", [False, True])
def test_vault_conserves_capital(prices, long_prices, indicator, rearm):
    """Le Coffre : le budget entier est versé, achat ou réserve, jamais dépassé."""
    strategy = VaultDCAStrategy(100, indicator, frequency='weekly', rearm=rearm)
    result = Backtester(prices, strategy, 0.001, None, long_prices).run()  # pas de vix_history -> vix toujours NaN
    m = result['metrics']

    budget = 100 * count_periods(VaultDCAStrategy(100, indicator, frequency='weekly'), prices.index)
    assert m['total_invested'] == pytest.approx(budget, abs=1e-6)
    assert m['total_invested'] == pytest.approx(m['total_deployed'] + m['cash_reserve'], abs=1e-6)


def test_vault_reserve_ratio_zero_equals_classic(prices, long_prices):
    """reserve_ratio=0 (implicite pour Classic) doit donner un résultat identique
    à DryPowder avec reserve_ratio=0 : aucune réserve, aucun déclencheur actif."""
    classic = Backtester(prices, ClassicDCAStrategy(100, 'weekly'), 0.001).run()['metrics']
    dp = Backtester(
        prices, DryPowderDCAStrategy(100, 0.0, -0.2, frequency='weekly'), 0.001, None, long_prices
    ).run()['metrics']
    assert classic['xirr'] == pytest.approx(dp['xirr'], abs=1e-9)


# ==============================================================================
# Causalité (zéro biais d'anticipation)
# ==============================================================================

STRATEGY_FACTORIES = [
    lambda: ClassicDCAStrategy(100, 'weekly'),
    lambda: DrawdownDCAStrategy(100, 'weekly'),
    lambda: RSIDCAStrategy(100, 'weekly'),
    lambda: KairosScoreDCAStrategy(100, 'weekly'),
    lambda: DryPowderDCAStrategy(100, 0.5, -0.3, frequency='weekly'),
    lambda: VaultDCAStrategy(100, 'rsi', frequency='weekly'),
    lambda: VaultDCAStrategy(100, 'drawdown', frequency='weekly'),
]


@pytest.mark.parametrize("make_strategy", STRATEGY_FACTORIES, ids=lambda f: f().__class__.__name__)
def test_causality_via_truncation(prices, long_prices, make_strategy):
    """
    Test décisif : si une stratégie utilise des données FUTURES pour décider d'un
    achat, tronquer la série après ce point changera les achats déjà passés.
    Une stratégie strictement causale doit produire EXACTEMENT les mêmes achats
    (montant et date) avant le point de troncature, qu'on lui donne la série
    complète ou tronquée à cet endroit.
    """
    cut = prices.index[len(prices) // 2]
    prices_truncated = prices.loc[:cut]
    long_truncated = long_prices.loc[:cut]

    full = Backtester(prices, make_strategy(), 0.001, None, long_prices).run()['trades']
    part = Backtester(prices_truncated, make_strategy(), 0.001, None, long_truncated).run()['trades']

    cols = ['date', 'amount', 'cash_reserve']
    full_before_cut = full[full['date'] <= cut][cols].reset_index(drop=True)
    part_before_cut = part[part['date'] <= cut][cols].reset_index(drop=True)

    assert full_before_cut.equals(part_before_cut), (
        f"Achats différents avant la troncature : la stratégie regarde le futur.\n"
        f"Complet:\n{full_before_cut}\nTronqué:\n{part_before_cut}"
    )


# ==============================================================================
# Déterminisme
# ==============================================================================

def test_vault_deterministic(prices, long_prices):
    """Deux runs de la même instance doivent produire des résultats identiques
    (le Coffre garde un état interne — reset() doit vraiment tout remettre à zéro)."""
    strategy = VaultDCAStrategy(100, 'drawdown', threshold=-0.3, frequency='weekly')
    backtester = Backtester(prices, strategy, 0.001, None, long_prices)

    r1 = backtester.run()['metrics']
    r2 = backtester.run()['metrics']

    for key in ('total_invested', 'xirr', 'cash_reserve', 'num_trades'):
        assert r1[key] == pytest.approx(r2[key], abs=1e-9), f"{key} diffère entre deux runs"


# ==============================================================================
# Validation des paramètres
# ==============================================================================

@pytest.mark.parametrize("kwargs", [
    dict(reserve_ratio=1.2, dip_threshold=-0.2),
    dict(reserve_ratio=0.3, dip_threshold=0.1),
    dict(reserve_ratio=0.3, dip_threshold=-0.2, deployment_multiplier=1.5),
    dict(reserve_ratio=0.3, dip_threshold=-0.2, deployment_multiplier=0.0),
])
def test_drypowder_rejects_invalid_params(kwargs):
    with pytest.raises(ValueError):
        DryPowderDCAStrategy(100, **kwargs)


@pytest.mark.parametrize("kwargs", [
    dict(indicator='not_a_real_indicator'),
    dict(indicator='rsi', threshold=150),
    dict(indicator='drawdown', threshold=0.1),
    dict(indicator='vix', threshold=-5),
])
def test_vault_rejects_invalid_params(kwargs):
    with pytest.raises(ValueError):
        VaultDCAStrategy(100, **kwargs)


def test_base_strategy_rejects_unknown_frequency():
    with pytest.raises(ValueError):
        ClassicDCAStrategy(100, frequency='hourly')
