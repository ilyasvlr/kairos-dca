"""Tests de core/robustness.py — construction de grille et agrégation (rapide, prix synthétiques)."""

import pytest

from core.backtester import VaultDCAStrategy
from core.robustness import build_grid, build_vault_grid, compute_robustness_map, rank_stability


def test_build_grid_labels_unique():
    configs = build_grid()
    assert len(configs) == len(set(c['label'] for c in configs))
    assert all(c['kind'] == 'dry_powder' for c in configs)


def test_build_vault_grid_covers_requested_indicators():
    configs = build_vault_grid(indicators=('rsi', 'vix', 'fear_greed'))
    assert {c['indicator'] for c in configs} == {'rsi', 'vix', 'fear_greed'}
    assert all(c['kind'] == 'vault' for c in configs)
    assert len(configs) == len(set(c['label'] for c in configs))


def test_combined_grid_labels_unique():
    """Les deux familles combinées (comme dans app.py) ne doivent jamais se chevaucher."""
    combined = build_grid() + build_vault_grid()
    assert len(combined) == len(set(c['label'] for c in combined))


def test_compute_robustness_map_mixed_kinds(long_prices):
    """
    Régression : summarize() plantait (ValueError: cannot insert label, already
    exists) dès qu'on mélangeait des configs 'dry_powder' et 'vault' dans la
    même carte — 'label' était à la fois la clé de groupby ET redemandé comme
    colonne agrégée. Ce test fait tourner exactement ce mélange.
    """
    configs = (
        build_grid(reserves=(0.3, 0.5), thresholds=(-0.2, -0.4))
        + build_vault_grid(indicators=('rsi', 'vix'), thresholds_by_indicator={
            'rsi': (25.0, 35.0), 'vix': (20.0, 30.0),
        })
    )
    summary, rows = compute_robustness_map(
        long_prices, configs, frequency='weekly', window_years=2, step_months=12, warmup_years=1,
    )

    assert len(summary) == len(configs)
    assert set(summary['label']) == {c['label'] for c in configs}
    for col in ('win_rate', 'gap_median', 'gap_worst', 'gap_best', 'cash_share_avg'):
        assert col in summary.columns
        assert summary[col].notna().all()

    # Chaque famille garde ses colonnes propres, NaN pour l'autre famille (pas de plantage)
    dp_rows = summary[summary['kind'] == 'dry_powder']
    vault_rows = summary[summary['kind'] == 'vault']
    assert len(dp_rows) == 4  # 2 réserves x 2 seuils
    assert len(vault_rows) == 4  # 2 indicateurs x 2 seuils
    assert dp_rows['reserve_ratio'].notna().all()
    assert vault_rows['indicator'].notna().all()


def test_rank_stability_filters_by_kind(long_prices):
    configs = (
        build_grid(reserves=(0.3, 0.5), thresholds=(-0.2, -0.4))
        + build_vault_grid(indicators=('rsi',), thresholds_by_indicator={'rsi': (25.0, 35.0)})
    )
    _, rows = compute_robustness_map(
        long_prices, configs, frequency='weekly', window_years=2, step_months=6, warmup_years=1,
    )
    # Assez de fenêtres pour comparer deux moitiés non chevauchantes
    stability_all = rank_stability(rows)
    stability_dp = rank_stability(rows, kind='dry_powder')
    stability_vault = rank_stability(rows, kind='vault')
    for s in (stability_all, stability_dp):
        if s is not None:
            assert -1.0 <= s['spearman'] <= 1.0
    # Trop peu de configs 'vault' distinctes ici (2) pour une corrélation de rang
    # significative -> None est un résultat valide, pas une erreur.
    assert stability_vault is None or -1.0 <= stability_vault['spearman'] <= 1.0
