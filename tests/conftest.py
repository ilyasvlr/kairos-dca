"""
Fixtures partagées.

Les tests utilisent des prix SYNTHÉTIQUES (générés ici, aucun appel réseau) :
rapides, déterministes, et fiables en CI (pas de dépendance à Yahoo Finance
ou FRED qui pourraient être indisponibles/limités depuis les serveurs GitHub).
"""

import numpy as np
import pandas as pd
import pytest


def make_prices(seed: int = 0, n_days: int = 1460, start: str = "2020-01-01",
                mu: float = 0.0006, sigma: float = 0.03) -> pd.DataFrame:
    """OHLCV synthétique (marche aléatoire géométrique) avec un vrai drawdown."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(mu, sigma, n_days)
    close = 100 * np.cumprod(1 + returns)
    idx = pd.date_range(start, periods=n_days, freq="D", tz="UTC")
    return pd.DataFrame(
        {"Open": close, "High": close * 1.001, "Low": close * 0.999, "Close": close, "Volume": 1.0},
        index=idx,
    )


@pytest.fixture
def long_prices():
    """
    8 ans de prix synthétiques. `prices` en est un SOUS-ENSEMBLE (mêmes 4
    dernières années) : sans ça, deux séries générées séparément n'auraient
    aucune relation, ce qui fausserait les tests d'amorçage causal (drawdown,
    200WMA) qui reposent sur long_prices étant la VRAIE histoire antérieure.
    """
    return make_prices(seed=1, n_days=2920, start="2016-01-01")


@pytest.fixture
def prices(long_prices):
    """Les 4 dernières années de `long_prices` — c'est la fenêtre réellement testée."""
    return long_prices.loc["2020-01-01":]
