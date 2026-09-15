"""
Metrics Module
Calcule les métriques de performance
"""

import pandas as pd
import numpy as np
from scipy.optimize import brentq

# Taux testés pour encadrer la racine : de -99.99% à +100 000% par an
_XIRR_BRACKETS = (-0.9999, -0.99, -0.9, -0.75, -0.5, -0.25, 0.0, 0.25, 0.5,
                  1.0, 2.0, 5.0, 10.0, 100.0, 1000.0)


def calculate_xirr(cashflows: list, dates: list, guess: float = 0.1) -> float:
    """
    Calcule le XIRR (taux de rendement interne pour flux irréguliers)
    cashflows: list de montants (négatif = investissement, positif = valeur finale)
    dates: list de dates correspondantes
    Retourne un pourcentage annualisé.

    On encadre la racine par un changement de signe de la VAN puis on la résout
    par dichotomie (brentq, convergence garantie). Newton, utilisé auparavant,
    partait de +10% et échouait sur les fenêtres de krach (ex. SPY 2006-2009 :
    XIRR réel -24.78%, renvoyé 0.00%). `guess` est conservé pour compatibilité.
    """
    if len(cashflows) != len(dates):
        raise ValueError("cashflows et dates doivent avoir la même longueur")

    if len(cashflows) < 2:
        return 0.0

    # Il faut au moins un flux négatif et un positif pour qu'une racine existe
    if not (min(cashflows) < 0 < max(cashflows)):
        return 0.0

    values = np.asarray(cashflows, dtype=float)
    years = np.array([(d - dates[0]).days / 365.0 for d in dates])

    def xnpv(rate: float) -> float:
        return float(np.sum(values / (1.0 + rate) ** years))

    with np.errstate(over='ignore', divide='ignore', invalid='ignore'):
        npvs = [xnpv(r) for r in _XIRR_BRACKETS]
        for (low, f_low), (high, f_high) in zip(
            zip(_XIRR_BRACKETS, npvs), zip(_XIRR_BRACKETS[1:], npvs[1:])
        ):
            if not (np.isfinite(f_low) and np.isfinite(f_high)):
                continue
            if f_low == 0.0:
                return low * 100
            if f_low * f_high < 0:
                return brentq(xnpv, low, high, xtol=1e-12, maxiter=200) * 100

    return 0.0


def calculate_roi(total_invested: float, final_value: float) -> float:
    """Calcule le ROI en pourcentage"""
    if total_invested == 0:
        return 0.0
    return ((final_value - total_invested) / total_invested) * 100


def calculate_cagr(start_value: float, end_value: float, years: float) -> float:
    """Calcule le CAGR (Compound Annual Growth Rate)"""
    if start_value <= 0 or years <= 0:
        return 0.0
    return ((end_value / start_value) ** (1 / years) - 1) * 100


def calculate_max_drawdown(portfolio_values: pd.Series) -> float:
    """Calcule le drawdown maximum"""
    if portfolio_values.empty:
        return 0.0

    cumulative_max = portfolio_values.cummax()
    drawdown = (portfolio_values - cumulative_max) / cumulative_max
    return drawdown.min() * 100


def calculate_sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.02) -> float:
    """Calcule le Sharpe Ratio (annualisé)"""
    if returns.empty or returns.std() == 0:
        return 0.0

    excess_returns = returns - risk_free_rate / 252  # Daily risk-free rate
    sharpe = excess_returns.mean() / returns.std() * np.sqrt(252)
    return sharpe


def calculate_sortino_ratio(returns: pd.Series, risk_free_rate: float = 0.02) -> float:
    """Calcule le Sortino Ratio (prend en compte seulement la downside volatility)"""
    if returns.empty:
        return 0.0

    excess_returns = returns - risk_free_rate / 252
    downside_returns = returns[returns < 0]

    if downside_returns.empty or downside_returns.std() == 0:
        return 0.0

    sortino = excess_returns.mean() / downside_returns.std() * np.sqrt(252)
    return sortino


def calculate_win_rate(trades: pd.DataFrame) -> float:
    """Calcule le pourcentage d'achats rentables"""
    if trades.empty:
        return 0.0

    profitable = trades[trades['pnl'] > 0]
    return (len(profitable) / len(trades)) * 100


def calculate_time_in_profit(portfolio_values: pd.Series, total_invested_series: pd.Series) -> float:
    """Calcule le pourcentage de temps dans le vert"""
    if portfolio_values.empty:
        return 0.0

    in_profit = portfolio_values > total_invested_series
    return (in_profit.sum() / len(portfolio_values)) * 100


def calculate_all_metrics(
    portfolio_values: pd.Series,
    total_invested: float,
    final_value: float,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
    daily_returns: pd.Series = None
) -> dict:
    """Calcule toutes les métriques et retourne un dictionnaire"""

    years = (end_date - start_date).days / 365.25

    metrics = {
        'total_invested': total_invested,
        'final_value': final_value,
        'roi': calculate_roi(total_invested, final_value),
        'cagr': calculate_cagr(total_invested, final_value, years),
        'max_drawdown': calculate_max_drawdown(portfolio_values),
    }

    if daily_returns is not None and not daily_returns.empty:
        metrics['sharpe_ratio'] = calculate_sharpe_ratio(daily_returns)
        metrics['sortino_ratio'] = calculate_sortino_ratio(daily_returns)
    else:
        metrics['sharpe_ratio'] = 0.0
        metrics['sortino_ratio'] = 0.0

    return metrics
