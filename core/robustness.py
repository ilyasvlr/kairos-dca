"""
Robustness Module
Carte de robustesse des stratégies à réserve de cash (Dry Powder + Coffre).

Chaque configuration d'une grille FIXÉE À L'AVANCE est évaluée sur toutes les
fenêtres glissantes de l'historique, contre le DCA classique sur la même fenêtre.
Rien n'est ajusté sur les données : chaque fenêtre complète est hors échantillon
pour la grille, d'où l'absence de découpage IS/OOS.

Deux familles de configurations, toutes évaluées de la même façon :
  - 'dry_powder' : réserve partielle déclenchée par le drawdown (DryPowderDCAStrategy)
  - 'vault'       : réserve totale déclenchée par RSI, VIX ou Fear & Greed (VaultDCAStrategy)

Métrique principale : l'écart de valeur finale (%) contre le classique. Les deux
stratégies versent exactement les mêmes montants aux mêmes dates, donc cet écart
classe comme le XIRR, sans l'annualisation qui fait exploser les écarts en pp
pendant les bull runs.
"""

from itertools import product
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .backtester import Backtester, ClassicDCAStrategy, DryPowderDCAStrategy, VaultDCAStrategy

DEFAULT_RESERVES = (0.2, 0.3, 0.4, 0.5, 0.6)
DEFAULT_THRESHOLDS = (-0.15, -0.25, -0.35, -0.45)

# Seuils testés par indicateur pour la famille 'vault'. rearm=False fixé : déjà
# montré systématiquement meilleur que rearm=True sur Drawdown (voir historique
# du projet) — doubler la grille pour re-tester ce point sur chaque indicateur
# n'apporterait rien et alourdirait le calcul.
VAULT_THRESHOLDS = {
    'rsi': (20.0, 25.0, 30.0, 35.0, 40.0),
    'vix': (20.0, 25.0, 30.0, 35.0, 40.0),
    'fear_greed': (15.0, 20.0, 25.0, 30.0, 35.0),
}


def build_grid(
    reserves: Sequence[float] = DEFAULT_RESERVES,
    thresholds: Sequence[float] = DEFAULT_THRESHOLDS,
    multipliers: Sequence[float] = (1.0,),
    rearm: bool = False,
) -> List[Dict]:
    """
    Grille cartésienne de configurations Dry Powder (déclencheur : drawdown).
    Réserve 0% exclue : c'est le DCA classique, la référence (écart nul par construction).
    """
    return [
        dict(kind='dry_powder', reserve_ratio=r, dip_threshold=t, deployment_multiplier=m, rearm=rearm,
            label=f"Drawdown r={r:.0%} seuil={t:.0%}")
        for r, t in product(reserves, thresholds)
        for m in multipliers
    ]


def build_vault_grid(
    indicators: Sequence[str] = ('rsi', 'vix', 'fear_greed'),
    thresholds_by_indicator: Dict[str, Sequence[float]] = VAULT_THRESHOLDS,
    rearm: bool = False,
) -> List[Dict]:
    """
    Grille de configurations Coffre (réserve totale) : un déclencheur autre que
    le drawdown, à plusieurs seuils chacun. 'fear_greed' n'a de sens que sur
    crypto — filtré en amont par l'appelant si l'actif est une action/ETF.
    """
    configs = []
    for indicator in indicators:
        for threshold in thresholds_by_indicator[indicator]:
            label_name = VaultDCAStrategy.INDICATORS[indicator]['label']
            configs.append(dict(
                kind='vault', indicator=indicator, threshold=threshold, rearm=rearm,
                label=f"Coffre [{label_name}] seuil={threshold:g}",
            ))
    return configs


def generate_windows(
    index: pd.DatetimeIndex,
    window_years: int = 3,
    step_months: int = 6,
    warmup_years: int = 1,
) -> List[Tuple[pd.Timestamp, pd.Timestamp]]:
    """
    Fenêtres glissantes définies par DATES (et non par nombre de lignes : 1095
    lignes font 3 ans en crypto mais 4.3 ans en actions).

    warmup_years : les premières années de l'historique ne servent qu'à amorcer
    l'ATH du drawdown, aucune fenêtre n'y commence.
    """
    windows = []
    start = index[0] + pd.DateOffset(years=warmup_years)
    while start + pd.DateOffset(years=window_years) <= index[-1]:
        windows.append((start, start + pd.DateOffset(years=window_years)))
        start += pd.DateOffset(months=step_months)
    return windows


def _build_strategy(config: Dict, base_budget: float, frequency: str):
    """Instancie la bonne classe de stratégie selon `config['kind']`."""
    params = {k: v for k, v in config.items() if k not in ('kind', 'label')}
    if config['kind'] == 'dry_powder':
        return DryPowderDCAStrategy(base_budget=base_budget, frequency=frequency, **params)
    elif config['kind'] == 'vault':
        return VaultDCAStrategy(base_budget=base_budget, frequency=frequency, **params)
    raise ValueError(f"kind inconnu: {config['kind']!r}")


def evaluate_window(
    history: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    configs: List[Dict],
    frequency: str = 'weekly',
    fees: float = 0.001,
    base_budget: float = 100.0,
    fear_greed_history: Optional[pd.DataFrame] = None,
    vix_history: Optional[pd.DataFrame] = None,
) -> List[Dict]:
    """
    Évalue toutes les configurations sur une fenêtre.

    L'historique complet sert à amorcer l'ATH : c'est causal (vérifié par le test
    de troncature), les données postérieures à chaque jour ne sont jamais lues.
    Le budget n'influence pas les écarts relatifs (tout est linéaire, frais inclus).
    fear_greed_history / vix_history : nécessaires pour évaluer les configs
    'vault' dont l'indicateur est 'fear_greed' / 'vix' ; sans eux, ces indicateurs
    restent NaN et la stratégie n'achète jamais que via la réserve jamais
    déclenchée (voir VaultDCAStrategy._is_triggered) — pas d'erreur, mais un
    résultat qui ne reflète pas le vrai indicateur.
    """
    window = history.loc[start:end]
    classic_bt = Backtester(window, ClassicDCAStrategy(base_budget, frequency), fees, fear_greed_history, history, vix_history)
    market_state = classic_bt.build_market_state()
    classic = classic_bt.run(market_state=market_state)['metrics']

    rows = []
    for config in configs:
        strategy = _build_strategy(config, base_budget, frequency)
        result = Backtester(window, strategy, fees, fear_greed_history, history, vix_history).run(market_state=market_state)
        m = result['metrics']

        pv = result['portfolio_values']
        invested_days = pv > 0
        cash_share = (result['cash_reserve_series'][invested_days] / pv[invested_days]).mean()

        rows.append({
            **config,
            'window_start': start,
            'window_end': end,
            'value_gap_pct': (m['total_portfolio_value'] / classic['total_portfolio_value'] - 1) * 100,
            'xirr_excess': m['xirr'] - classic['xirr'],
            'xirr': m['xirr'],
            'classic_xirr': classic['xirr'],
            'cash_share_avg': cash_share * 100,  # % moyen du portefeuille dormant en cash
        })
    return rows


def summarize(rows: pd.DataFrame) -> pd.DataFrame:
    """
    Une ligne par configuration : distribution des écarts sur toutes les fenêtres.

    Regroupé par `label` (identifiant humainement lisible et unique par config) :
    marche pour les deux familles ('dry_powder' a reserve_ratio/dip_threshold,
    'vault' a indicator/threshold — pas de colonnes communes à grouper dessus).
    Les colonnes spécifiques (reserve_ratio, indicator, ...) sont réattachées via
    `first()` : identiques pour toutes les lignes d'un même label par construction.
    """
    other_cols = [c for c in rows.columns if c not in (
        'label', 'window_start', 'window_end', 'value_gap_pct', 'xirr_excess', 'xirr', 'classic_xirr', 'cash_share_avg'
    )]
    summary = rows.groupby('label', sort=False).agg(
        n_windows=('value_gap_pct', 'size'),
        win_rate=('value_gap_pct', lambda s: (s > 0).mean() * 100),
        gap_median=('value_gap_pct', 'median'),
        gap_worst=('value_gap_pct', 'min'),
        gap_best=('value_gap_pct', 'max'),
        gap_std=('value_gap_pct', 'std'),
        xirr_excess_median=('xirr_excess', 'median'),
        cash_share_avg=('cash_share_avg', 'mean'),
        **{c: (c, 'first') for c in other_cols},
    ).reset_index()
    return summary.sort_values('gap_median', ascending=False).reset_index(drop=True)


def rank_stability(rows: pd.DataFrame, kind: Optional[str] = None) -> Optional[Dict]:
    """
    Le classement de la carte est-il stable dans le temps ?

    Coupe les fenêtres en deux groupes qui ne se chevauchent pas (fin avant le
    milieu de l'historique / début après), classe les configurations par écart
    médian dans chaque groupe et renvoie la corrélation de rang entre les deux.
    Proche de 1 : le classement passé a prédit le classement futur.
    Proche de 0 ou négatif : choisir « la meilleure ligne » revient à tirer au sort.

    kind : restreint la comparaison à une famille ('dry_powder' ou 'vault') si
    fourni — mélanger des familles aux échelles différentes n'a pas de sens ici.
    """
    if kind is not None:
        rows = rows[rows['kind'] == kind]
        if rows.empty:
            return None

    first, last = rows['window_start'].min(), rows['window_end'].max()
    mid = first + (last - first) / 2
    early = rows[rows['window_end'] <= mid]
    late = rows[rows['window_start'] >= mid]
    if early['window_start'].nunique() < 2 or late['window_start'].nunique() < 2:
        return None

    med_early = early.groupby('label')['value_gap_pct'].median()
    med_late = late.groupby('label')['value_gap_pct'].median()
    both = pd.concat([med_early.rename('early'), med_late.rename('late')], axis=1).dropna()
    if len(both) < 3:
        return None

    return {
        'spearman': both['early'].corr(both['late'], method='spearman'),
        'split_date': mid,
        'n_early': early['window_start'].nunique(),
        'n_late': late['window_start'].nunique(),
        'best_early_rank_late': int(both['late'].rank(ascending=False)[both['early'].idxmax()]),
        'n_configs': len(both),
    }


def compute_robustness_map(
    history: pd.DataFrame,
    configs: Optional[List[Dict]] = None,
    frequency: str = 'weekly',
    fees: float = 0.001,
    window_years: int = 3,
    step_months: int = 6,
    warmup_years: int = 1,
    fear_greed_history: Optional[pd.DataFrame] = None,
    vix_history: Optional[pd.DataFrame] = None,
    progress: Optional[Callable[[int, int], None]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Calcule la carte de robustesse sur tout l'historique fourni.

    Returns:
        (summary, rows) — summary : une ligne par configuration, triée par écart
        médian ; rows : le détail configuration × fenêtre.
    """
    configs = configs if configs is not None else build_grid()
    windows = generate_windows(history.index, window_years, step_months, warmup_years)
    if not windows:
        raise ValueError(
            f"Historique trop court : il faut au moins {warmup_years + window_years} ans de données"
        )

    all_rows = []
    for i, (start, end) in enumerate(windows):
        all_rows.extend(evaluate_window(
            history, start, end, configs, frequency, fees,
            fear_greed_history=fear_greed_history, vix_history=vix_history,
        ))
        if progress is not None:
            progress(i + 1, len(windows))

    rows = pd.DataFrame(all_rows)
    return summarize(rows), rows
